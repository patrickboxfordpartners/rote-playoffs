"""Reasoning Agent — LLM-powered analysis and content generation.

Subscribes to memory-enriched data, uses OpenAI (or Claude) to produce:
- Executive summary in plain language
- Delta narrative ("what changed since last scan")
- Rewritten meta descriptions and schema markup
- Prioritized action plan with business context
"""

import asyncio
import json
import os

from .schema import AnalysisComplete, envelope, to_json, from_json
from .mesh import CH_MEMORY_ENRICHED, CH_ANALYSIS_COMPLETE


AGENT_ID = "aeo-reasoning"
AGENT_ROLE = "analyst"


SYSTEM_PROMPT = """You are an AI readiness consultant writing for small business owners
who may not understand technical SEO or AI concepts. Your job is to translate scan
results into clear, actionable advice.

Rules:
- Use plain language. No jargon without explanation.
- Lead with what matters most to their business.
- Be specific: "Add a LocalBusiness schema" not "improve structured data."
- When there's a delta from a prior scan, highlight what improved and what declined.
- Frame everything in terms of business impact: visibility to AI assistants means
  more potential customers finding them through ChatGPT, Perplexity, Google AI, etc.
"""


def _build_analysis_prompt(enriched: dict) -> str:
    """Construct the LLM prompt from enriched scan data."""
    crawl = enriched.get("crawl_data", {})
    deltas = enriched.get("deltas", [])
    client_ctx = enriched.get("client_context", "")
    scan_count = enriched.get("scan_count", 1)
    domain = enriched.get("root_url", "unknown")

    sections = [f"# AI Readiness Scan: {domain}\n"]

    # Scores
    vis = crawl.get("visibility_scores", {})
    vis_total = sum(vis.values())
    sections.append(f"## Scores\n- Visibility: {vis_total}/100")

    content = crawl.get("content_results", [])
    if content:
        sections.append(f"- Content Quality: {content[0].get('score_pct', '?')}/100 ({content[0].get('risk_level', '')})")

    ar = crawl.get("agent_readiness")
    if ar:
        sections.append(f"- Agent Readiness: {ar.get('agent_score', '?')}/100 ({ar.get('agent_grade', '')})")

    # Pages crawled
    pages = crawl.get("pages", [])
    if pages:
        sections.append(f"\n## Site Structure\n- {len(pages)} pages crawled")
        no_schema = [p for p in pages if not p.get("has_schema")]
        no_meta = [p for p in pages if not p.get("has_meta_desc")]
        thin = [p for p in pages if p.get("word_count", 0) < 100]
        if no_schema:
            sections.append(f"- {len(no_schema)} pages missing structured data")
        if no_meta:
            sections.append(f"- {len(no_meta)} pages missing meta descriptions")
        if thin:
            sections.append(f"- {len(thin)} thin pages (<100 words)")

    # Deltas
    if deltas:
        sections.append("\n## Changes Since Last Scan")
        for d in deltas:
            arrow = "+" if d["direction"] == "improved" else "-" if d["direction"] == "declined" else "="
            sections.append(f"- {d['metric']}: {d['previous']} -> {d['current']} ({arrow})")

    # Client context
    if client_ctx:
        sections.append(f"\n## Client Context\n{client_ctx}")

    # Recommendations from the scan
    recs = crawl.get("recommendations", [])
    if recs:
        sections.append("\n## Technical Recommendations")
        for r in recs[:5]:
            sections.append(f"- [{r.get('points', '?')}pts] {r.get('title', '')}: {r.get('why', '')}")

    sections.append(f"\n## Scan History\nThis is scan #{scan_count} for this domain.")

    sections.append("""
## Your Task
Produce a JSON response with these fields:
1. "executive_summary": 2-3 sentences a business owner would understand.
2. "delta_narrative": What changed since last scan (empty string if first scan).
3. "rewritten_meta": Array of {url, current, suggested} for pages with weak/missing meta descriptions.
4. "content_suggestions": Array of specific, actionable content improvements.
5. "priority_actions": Array of {action, impact, difficulty} ranked by ROI, max 5 items.
""")

    return "\n".join(sections)


async def _call_llm(prompt: str) -> dict:
    """Call OpenAI or Claude for analysis. Runs HTTP in a thread to avoid blocking."""
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        result = await asyncio.to_thread(_call_openai_sync, prompt, openai_key)
        if not result.get("error"):
            return result

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        result = await asyncio.to_thread(_call_anthropic_sync, prompt, anthropic_key)
        if not result.get("error"):
            return result

    return _fallback_analysis(prompt)


def _call_openai_sync(prompt: str, api_key: str) -> dict:
    """Synchronous OpenAI call -- runs in a thread."""
    import urllib.request

    body = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
    }).encode()

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as e:
        return {"error": str(e)}


def _call_anthropic_sync(prompt: str, api_key: str) -> dict:
    """Synchronous Anthropic call -- runs in a thread. Tries multiple model IDs."""
    import urllib.request

    models = ["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"]
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID", "")
    if workspace_id:
        headers["anthropic-workspace-id"] = workspace_id

    last_error = None
    for model in models:
        body = json.dumps({
            "model": model,
            "max_tokens": 2000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
            content = data["content"][0]["text"]
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"executive_summary": content}
        except Exception as e:
            last_error = e
            continue

    return {"error": str(last_error) if last_error else "All Anthropic models failed"}


def _fallback_analysis(prompt: str) -> dict:
    """When no LLM is available, produce structured insights from the scan data."""
    import re

    vis_match = re.search(r"Visibility:\s*(\d+)/100", prompt)
    vis = int(vis_match.group(1)) if vis_match else None
    content_match = re.search(r"Content Quality:\s*(\d+)/100", prompt)
    content = int(content_match.group(1)) if content_match else None

    missing_schema = re.search(r"(\d+) pages missing structured data", prompt)
    missing_meta = re.search(r"(\d+) pages missing meta descriptions", prompt)
    thin_pages = re.search(r"(\d+) thin pages", prompt)

    parts = []
    if vis is not None:
        if vis >= 80:
            parts.append(f"Your site scores {vis}/100 on AI visibility — that's excellent.")
        elif vis >= 60:
            parts.append(f"Your site scores {vis}/100 on AI visibility — solid, but there's room to grow.")
        elif vis >= 40:
            parts.append(f"Your site scores {vis}/100 on AI visibility — AI assistants can find you, but you're missing key signals.")
        else:
            parts.append(f"Your site scores {vis}/100 on AI visibility — most AI assistants will struggle to understand your business.")

    if content is not None:
        if content >= 85:
            parts.append(f"Content quality is strong at {content}/100 — it reads naturally and is likely to be cited.")
        elif content >= 60:
            parts.append(f"Content scores {content}/100 — good, but some sections could sound more natural.")
        else:
            parts.append(f"Content quality at {content}/100 needs attention — it may not be cited by AI assistants.")

    if not parts:
        parts.append("This scan assessed how well AI assistants can discover and cite your business.")

    summary = " ".join(parts) + " When AI tools like ChatGPT, Perplexity, or Google AI recommend businesses, they look for these exact signals."

    actions = []
    if missing_schema:
        n = missing_schema.group(1)
        actions.append({"action": f"Add structured data (schema markup) to {n} pages missing it", "impact": "High — this is how AI assistants understand what your business does", "difficulty": "medium"})
    if missing_meta:
        n = missing_meta.group(1)
        actions.append({"action": f"Write meta descriptions for {n} pages that don't have them", "impact": "Medium — meta descriptions give AI assistants a ready-made summary to quote", "difficulty": "easy"})
    if thin_pages:
        n = thin_pages.group(1)
        actions.append({"action": f"Add more content to {n} thin pages (under 100 words each)", "impact": "Medium — AI assistants need substance to cite your expertise", "difficulty": "medium"})
    if vis is not None and vis < 70:
        actions.append({"action": "Ensure your robots.txt allows AI crawlers (GPTBot, ClaudeBot, PerplexityBot)", "impact": "High — if AI crawlers are blocked, you're invisible to AI assistants", "difficulty": "easy"})
    if content is not None and content < 70:
        actions.append({"action": "Vary sentence lengths and add specific details (numbers, names, data)", "impact": "Medium — natural-sounding content is more likely to be quoted", "difficulty": "medium"})

    if not actions:
        actions.append({"action": "Review the detailed scores to identify your biggest opportunity areas", "impact": "Varies by finding", "difficulty": "easy"})

    suggestions = []
    if content is not None and content < 80:
        suggestions.append("Add concrete statistics and specific examples to key pages — AI assistants prefer citing definitive statements over vague claims.")
    if vis is not None and vis < 70:
        suggestions.append("Add FAQ sections with clear question-and-answer formatting — this is the exact structure AI assistants look for when building responses.")

    return {
        "executive_summary": summary,
        "delta_narrative": "",
        "rewritten_meta": [],
        "content_suggestions": suggestions,
        "priority_actions": actions[:5],
    }


async def handle_memory_enriched(msg, bus):
    """Receive enriched data, run LLM analysis, publish results."""
    data = from_json(msg.data)
    payload = data.get("payload", data)
    job_id = payload.get("job_id", "unknown")
    root_url = payload.get("root_url", "")

    prompt = _build_analysis_prompt(payload)
    analysis = await _call_llm(prompt)

    crawl_data = payload.get("crawl_data", {})
    result = AnalysisComplete(
        job_id=job_id,
        root_url=root_url,
        executive_summary=analysis.get("executive_summary", ""),
        delta_narrative=analysis.get("delta_narrative", ""),
        rewritten_meta=analysis.get("rewritten_meta", []),
        content_suggestions=analysis.get("content_suggestions", []),
        priority_actions=analysis.get("priority_actions", []),
        raw_scores=crawl_data,
    )

    out = envelope(AGENT_ID, CH_ANALYSIS_COMPLETE, result)
    await bus.publish(CH_ANALYSIS_COMPLETE, to_json(out))


async def start(bus):
    """Register this agent on the mesh and start listening."""
    await bus.subscribe(
        CH_MEMORY_ENRICHED,
        lambda msg: handle_memory_enriched(msg, bus),
    )
