"""Memory Agent — Mitosis-backed persistent scan history.

Subscribes to crawl completions, queries Mitosis for prior scans of the
same domain, computes deltas, enriches with client context, and publishes
the enriched bundle for the reasoning agent.

Stores scan facts as JSON-tagged text so recall parsing is reliable:
  [AEO_SCAN:{"domain":"...","date":"...","scores":{...}}]
"""

import asyncio
import json
import os
import re
import time
from urllib.parse import urlparse

from .schema import MemoryEnriched, ScanDelta, envelope, to_json, from_json
from .mesh import CH_CRAWL_COMPLETE, CH_MEMORY_ENRICHED


AGENT_ID = "aeo-memory"
AGENT_ROLE = "memory"

_SCAN_TAG = "AEO_SCAN"
_SCAN_PATTERN = re.compile(r"\[AEO_SCAN:(.*?)\]")


class MitosisClient:
    """Interface to Mitosis for scan memory."""

    def __init__(self, mcp_tools=None):
        self._mcp = mcp_tools

    async def remember_scan(self, domain: str, scan_data: dict):
        """Persist a scan result as a tagged JSON fact in Mitosis."""
        record = {
            "domain": domain,
            "date": time.strftime("%Y-%m-%d"),
            "ts": time.time(),
            "scores": {
                "visibility": scan_data.get("visibility_total"),
                "content": scan_data.get("content_pct"),
                "agent_readiness": scan_data.get("agent_score"),
            },
            "pages_crawled": len(scan_data.get("pages", [])),
        }

        # Human-readable prefix + machine-parseable tag
        fact = (
            f"AEO scan of {domain} on {record['date']}: "
            f"visibility {record['scores']['visibility']}/100, "
            f"content {record['scores']['content']}/100, "
            f"agent readiness {record['scores']['agent_readiness']}/100. "
            f"[{_SCAN_TAG}:{json.dumps(record)}]"
        )

        if self._mcp and hasattr(self._mcp, "cortex_remember"):
            await self._mcp.cortex_remember(text=fact, kind="observation")
        else:
            await self._rest_remember(fact)

    async def recall_prior_scans(self, domain: str) -> list:
        """Find prior scan results for this domain."""
        query = f"AEO scan of {domain}"

        if self._mcp and hasattr(self._mcp, "cortex_ask"):
            results = await self._mcp.cortex_ask(question=query, limit=5)
            return self._parse_scan_results(results)
        else:
            return await self._rest_recall(query)

    async def get_client_context(self, domain: str) -> str:
        """Ask Mitosis what we know about this domain's owner."""
        query = f"What do I know about {domain}? Client details, relationship, goals."

        if self._mcp and hasattr(self._mcp, "cortex_ask"):
            results = await self._mcp.cortex_ask(question=query, limit=3)
            return self._extract_context(results)
        else:
            return await self._rest_ask(query)

    def _parse_scan_results(self, results) -> list:
        """Extract structured scan data from the JSON tag in Mitosis results."""
        scans = []
        if not results:
            return scans

        for r in (results if isinstance(results, list) else [results]):
            text = r.get("text", "") if isinstance(r, dict) else str(r)

            # Try to extract the JSON tag first (reliable)
            match = _SCAN_PATTERN.search(text)
            if match:
                try:
                    record = json.loads(match.group(1))
                    scans.append({
                        "domain": record.get("domain", ""),
                        "date": record.get("date", ""),
                        "visibility": record.get("scores", {}).get("visibility"),
                        "content": record.get("scores", {}).get("content"),
                        "agent_readiness": record.get("scores", {}).get("agent_readiness"),
                        "pages_crawled": record.get("pages_crawled", 0),
                    })
                    continue
                except (json.JSONDecodeError, KeyError):
                    pass

            # Fallback: older facts without the JSON tag
            scan = self._parse_legacy_fact(text)
            if scan:
                scans.append(scan)

        return scans

    def _parse_legacy_fact(self, text: str) -> dict:
        """Best-effort parse of older free-text scan facts."""
        scan = {}
        for key in ("visibility", "content", "agent_readiness"):
            pattern = key + r"[= ]+(\d+)"
            m = re.search(pattern, text)
            if m:
                scan[key] = int(m.group(1))
        return scan if scan else None

    def _extract_context(self, results) -> str:
        if not results:
            return ""
        texts = []
        for r in (results if isinstance(results, list) else [results]):
            t = r.get("text", "") if isinstance(r, dict) else str(r)
            # Skip our own scan facts -- we want client context, not scan data
            if _SCAN_TAG in t:
                continue
            if t:
                texts.append(t)
        return " ".join(texts)[:500]

    async def _rest_remember(self, fact: str):
        pass

    async def _rest_recall(self, query: str) -> list:
        return []

    async def _rest_ask(self, query: str) -> str:
        return ""


def _compute_deltas(current: dict, prior: dict) -> list:
    """Compare current scan to most recent prior scan."""
    deltas = []
    metrics = [
        ("visibility", "Visibility Score"),
        ("content", "Content Quality"),
        ("agent_readiness", "Agent Readiness"),
    ]
    for key, label in metrics:
        cur_val = current.get(key)
        prev_val = prior.get(key)
        if cur_val is not None and prev_val is not None:
            deltas.append(ScanDelta(
                metric=label,
                previous=float(prev_val),
                current=float(cur_val),
            ).__dict__)
    return deltas


async def handle_crawl_complete(msg, bus, mitosis: MitosisClient):
    """Receive crawl results, enrich with memory, publish."""
    data = from_json(msg.data)
    payload = data.get("payload", data)
    job_id = payload.get("job_id", "unknown")
    root_url = payload.get("root_url", "")
    domain = urlparse(root_url).netloc if root_url else ""

    # Query Mitosis for prior scans
    prior_scans = await mitosis.recall_prior_scans(domain)
    prior_scan = prior_scans[0] if prior_scans else None

    # Build current scores in the same shape as stored scans
    content_results = payload.get("content_results") or [{}]
    current_summary = {
        "visibility": sum(payload.get("visibility_scores", {}).values()),
        "content": content_results[0].get("score_pct") if content_results else None,
        "agent_readiness": (payload.get("agent_readiness") or {}).get("agent_score"),
    }
    deltas = _compute_deltas(current_summary, prior_scan) if prior_scan else []

    # Get client context
    client_context = await mitosis.get_client_context(domain) if domain else ""

    # Persist this scan
    await mitosis.remember_scan(domain, {
        "visibility_total": current_summary["visibility"],
        "content_pct": current_summary["content"],
        "agent_score": current_summary["agent_readiness"],
        "pages": payload.get("pages", []),
    })

    result = MemoryEnriched(
        job_id=job_id,
        root_url=root_url,
        crawl_data=payload,
        prior_scan=prior_scan,
        deltas=deltas,
        client_context=client_context,
        scan_count=len(prior_scans) + 1,
    )

    out = envelope(AGENT_ID, CH_MEMORY_ENRICHED, result)
    await bus.publish(CH_MEMORY_ENRICHED, to_json(out))


async def start(bus, mcp_tools=None):
    """Register this agent on the mesh and start listening."""
    mitosis = MitosisClient(mcp_tools=mcp_tools)
    await bus.subscribe(
        CH_CRAWL_COMPLETE,
        lambda msg: handle_crawl_complete(msg, bus, mitosis),
    )
