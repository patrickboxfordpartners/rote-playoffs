"""Crawl Agent — Firecrawl-powered site intake.

Single Firecrawl pass: maps the domain for page inventory, scrapes the root
page for pipeline scoring, and extracts per-page signals -- no double-fetch.
"""

import asyncio
import json
import os
from urllib.parse import urlparse

from .schema import CrawlComplete, PageResult, envelope, to_json, from_json
from .mesh import CH_CRAWL_REQUEST, CH_CRAWL_COMPLETE


AGENT_ID = "aeo-crawl"
AGENT_ROLE = "crawler"


def _extract_page_data(url: str, html: str) -> dict:
    """Extract structured signals from a page's HTML."""
    from html.parser import HTMLParser

    class Extractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.title = ""
            self.meta_desc = ""
            self.text_parts = []
            self.schema_types = []
            self._in_title = False
            self._in_script = False
            self._skip = {"script", "style", "noscript"}
            self._stack = []

        def handle_starttag(self, tag, attrs):
            self._stack.append(tag)
            if tag == "title":
                self._in_title = True
            if tag == "meta":
                d = dict(attrs)
                if d.get("name", "").lower() == "description":
                    self.meta_desc = d.get("content", "")
            if tag == "script":
                d = dict(attrs)
                if d.get("type") == "application/ld+json":
                    self._in_script = True

        def handle_endtag(self, tag):
            if self._stack and self._stack[-1] == tag:
                self._stack.pop()
            if tag == "title":
                self._in_title = False
            if tag == "script":
                self._in_script = False

        def handle_data(self, data):
            if self._in_title:
                self.title += data
            elif self._in_script:
                try:
                    ld = json.loads(data)
                    t = ld.get("@type", "")
                    if t:
                        self.schema_types.append(t)
                except Exception:
                    pass
            elif not any(t in self._skip for t in self._stack):
                self.text_parts.append(data.strip())

    ext = Extractor()
    try:
        ext.feed(html)
    except Exception:
        pass

    text = " ".join(p for p in ext.text_parts if p)
    words = text.split()

    return PageResult(
        url=url,
        title=ext.title.strip(),
        word_count=len(words),
        has_schema=bool(ext.schema_types),
        has_meta_desc=bool(ext.meta_desc),
        schema_types=ext.schema_types,
        text_preview=" ".join(words[:50]),
    ).__dict__


def _firecrawl_app():
    """Return a FirecrawlApp if API key is set, else None."""
    fc_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not fc_key:
        return None
    try:
        from firecrawl import FirecrawlApp
        return FirecrawlApp(api_key=fc_key)
    except ImportError:
        return None


def _scrape_page(app, url: str) -> str:
    """Scrape one page with Firecrawl, return HTML."""
    try:
        result = app.scrape(url, formats=["html"])
        return getattr(result, "html", "") or ""
    except Exception:
        return ""


def _stdlib_fetch(url: str) -> str:
    """Fallback fetch with stdlib."""
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AEO-Toolkit/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


async def handle_crawl_request(msg, bus):
    """Single-pass crawl: map domain, score root, extract page signals."""
    data = from_json(msg.data)
    payload = data.get("payload", data)
    url = payload.get("url", "")
    job_id = payload.get("job_id", "unknown")
    depth = payload.get("depth", 0)

    if not url:
        return

    app = _firecrawl_app()

    # Step 1: Get root page HTML (one fetch, used for both scoring and page data)
    if app:
        root_html = _scrape_page(app, url)
    else:
        root_html = _stdlib_fetch(url)

    # Step 2: Run pipeline scoring on the root HTML we already have
    pipeline_data = await asyncio.to_thread(_run_pipeline_with_html, url, root_html)

    # Step 3: Build page inventory
    pages = [_extract_page_data(url, root_html)]

    if depth != 0 and app:
        # Map the domain for additional pages (no re-scrape of root)
        try:
            map_result = app.map(url)
            other_urls = [u for u in (map_result if isinstance(map_result, list) else [])
                          if u != url][:19]  # cap at 19 + root = 20
            for page_url in other_urls:
                html = _scrape_page(app, page_url)
                if html:
                    pages.append(_extract_page_data(page_url, html))
                else:
                    pages.append(PageResult(url=page_url).__dict__)
        except Exception:
            pass

    result = CrawlComplete(
        job_id=job_id,
        root_url=url,
        pages=pages,
        visibility_scores=pipeline_data.get("visibility_scores", {}),
        signals=pipeline_data.get("signals", {}),
        agent_readiness=pipeline_data.get("agent_readiness"),
        recommendations=pipeline_data.get("recommendations", []),
        content_results=_format_content(pipeline_data),
    )

    out = envelope(AGENT_ID, CH_CRAWL_COMPLETE, result)
    await bus.publish(CH_CRAWL_COMPLETE, to_json(out))


def _run_pipeline_with_html(url: str, firecrawl_html: str) -> dict:
    """Run pipeline scoring.

    Uses fetch_all()'s raw HTML for visibility scoring (preserves meta tags,
    ld+json, etc. that Firecrawl strips). Falls back to Firecrawl HTML only
    for content text extraction on JS-heavy pages where raw HTML is thin.
    """
    from score import (
        fetch_all, PageExtractor,
        score_crawler_access, score_structured_data,
        score_content_citability, score_entity_authority,
        generate_recommendations,
    )
    from aeo_writer.detector import analyze

    fetched = fetch_all(url)

    if fetched["html"][0] == 0:
        return {"error": f"Could not reach {url}"}

    # Score visibility from raw HTML (has meta tags, ld+json, etc.)
    html_body = fetched["html"][1]
    ext = PageExtractor()
    ext.feed(html_body)
    ext.close()

    crawler_score, crawler_signals = score_crawler_access(fetched)
    structured_score, structured_signals = score_structured_data(ext)
    citability_score, citability_signals = score_content_citability(ext)
    authority_score, authority_signals = score_entity_authority(ext)

    visibility_scores = {
        "crawler": crawler_score,
        "structured": structured_score,
        "citability": citability_score,
        "authority": authority_score,
    }
    all_signals = {}
    all_signals.update(crawler_signals)
    all_signals.update(structured_signals)
    all_signals.update(citability_signals)
    all_signals.update(authority_signals)

    visibility_total = sum(visibility_scores.values())
    recs = generate_recommendations(ext, fetched, all_signals, input_url=url)

    # Content analysis: use raw HTML text, fall back to Firecrawl for JS-heavy pages
    from aeo_pipeline.__main__ import _extract_text
    text = _extract_text(html_body)
    if len(text.split()) < 20 and firecrawl_html:
        fc_text = _extract_text(firecrawl_html)
        if len(fc_text.split()) > len(text.split()):
            text = fc_text

    content_result = analyze(text) if len(text.split()) >= 20 else None
    content_pct = round((1 - content_result.overall_score) * 100) if content_result else None

    agent_data = None
    try:
        from aeo_pipeline.agent_readiness import scan_agent_readiness
        agent_data, _ = scan_agent_readiness(url)
    except Exception:
        pass

    return {
        "visibility_scores": visibility_scores,
        "visibility_total": visibility_total,
        "signals": all_signals,
        "recommendations": recs,
        "content_result": content_result,
        "content_pct": content_pct,
        "agent_readiness": agent_data,
    }


def _format_content(pipeline_data: dict) -> list:
    """Format content result for the CrawlComplete schema."""
    cr = pipeline_data.get("content_result")
    if not cr:
        return []
    return [{
        "score_pct": pipeline_data["content_pct"],
        "risk_level": cr.risk_level,
        "signal_scores": {k: round(v, 3) for k, v in cr.signal_scores.items()},
    }]


async def start(bus):
    """Register this agent on the mesh and start listening."""
    await bus.subscribe(CH_CRAWL_REQUEST, lambda msg: handle_crawl_request(msg, bus))
