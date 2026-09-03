"""AEO Pipeline — unified AI readiness assessment.

Combines ai-visibility-audit (technical) and aeo-writer (content quality)
into a single scan. One URL in, complete diagnosis out.
"""

import argparse
import json
import sys
from urllib.parse import urlparse

from score import (
    fetch_all,
    PageExtractor,
    score_crawler_access,
    score_structured_data,
    score_content_citability,
    score_entity_authority,
    generate_recommendations,
)
from aeo_writer.detector import analyze


def _extract_text(html_body):
    """Extract readable text from HTML, skipping scripts and styles."""
    from html.parser import HTMLParser

    class Strip(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
            self._skip = {"script", "style"}
            self._stack = []

        def handle_starttag(self, tag, attrs):
            self._stack.append(tag)

        def handle_endtag(self, tag):
            if self._stack and self._stack[-1] == tag:
                self._stack.pop()

        def handle_data(self, data):
            if not any(t in self._skip for t in self._stack):
                self.parts.append(data)

    s = Strip()
    s.feed(html_body)
    return "\n\n".join(p.strip() for p in " ".join(s.parts).split("\n\n") if p.strip())


def _bar(filled, total, width=10):
    n = round((filled / total) * width) if total else 0
    return "█" * n + "░" * (width - n)


def _grade(score):
    if score >= 80:
        return "A", "Excellent"
    if score >= 60:
        return "B", "Good"
    if score >= 40:
        return "C", "Fair"
    if score >= 20:
        return "D", "Poor"
    return "F", "Critical"


def run_pipeline(url):
    """Run both audits on a URL. Returns (data_dict, error_string)."""
    fetched = fetch_all(url)

    if fetched["html"][0] == 0:
        return None, f"Could not reach {url}"

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

    text = _extract_text(html_body)

    # JS-heavy pages yield little text from raw HTML — try enhanced fetching
    if len(text.split()) < 20:
        try:
            from .fetcher import fetch_rendered_html
            rendered_html, _, method = fetch_rendered_html(url)
            if method == "firecrawl" and rendered_html:
                rendered_text = _extract_text(rendered_html)
                if len(rendered_text.split()) > len(text.split()):
                    text = rendered_text
        except Exception:
            pass
        if len(text.split()) < 20:
            try:
                from .fetcher import extract_content
                tavily_text, _, method = extract_content(url)
                if method == "tavily" and len(tavily_text.split()) > len(text.split()):
                    text = tavily_text
            except Exception:
                pass

    content_result = analyze(text) if len(text.split()) >= 20 else None

    content_pct = round((1 - content_result.overall_score) * 100) if content_result else None

    # Agent readiness scan (ora.ai + Cloudflare)
    agent_data = None
    try:
        from .agent_readiness import scan_agent_readiness
        agent_data, agent_errors = scan_agent_readiness(url)
    except Exception:
        pass

    if content_pct is not None:
        combined = round(visibility_total * 0.5 + content_pct * 0.5)
    else:
        combined = visibility_total

    return {
        "url": url,
        "combined_score": combined,
        "visibility_total": visibility_total,
        "visibility_scores": visibility_scores,
        "signals": all_signals,
        "recommendations": recs,
        "content_pct": content_pct,
        "content_result": content_result,
        "agent_readiness": agent_data,
    }, None


def format_report(data):
    """Format the unified report as terminal text."""
    domain = urlparse(data["url"]).netloc or data["url"]
    combined = data["combined_score"]
    letter, desc = _grade(combined)

    lines = []
    lines.append("=" * 64)
    lines.append(f"  AI READINESS REPORT: {domain}")
    lines.append("=" * 64)
    lines.append(f"\n  AI Readiness Score: {combined}/100  ({letter} — {desc})")

    lines.append(f"\n  TECHNICAL VISIBILITY  [{data['visibility_total']}/100]")
    lines.append("  " + "─" * 44)
    dims = [
        ("AI Crawler Access", data["visibility_scores"]["crawler"], 25),
        ("Structured Data", data["visibility_scores"]["structured"], 30),
        ("Content Citability", data["visibility_scores"]["citability"], 25),
        ("Entity & Authority", data["visibility_scores"]["authority"], 20),
    ]
    for name, sc, mx in dims:
        bar = _bar(sc, mx)
        lines.append(f"    {name:<22} {bar}  {sc}/{mx}")

    cr = data["content_result"]
    if cr:
        pct = data["content_pct"]
        lines.append(f"\n  CONTENT QUALITY  [{pct}/100 — {cr.risk_level}]")
        lines.append("  " + "─" * 44)
        for signal, score in cr.signal_scores.items():
            spct = round((1 - score) * 100)
            bar = _bar(1 - score, 1)
            lines.append(f"    {signal:<22} {bar}  {spct}%")

        if cr.flags:
            lines.append(f"\n    {len(cr.flags)} content issues detected")
    else:
        lines.append(f"\n  CONTENT QUALITY")
        lines.append("  " + "─" * 44)
        lines.append("    Insufficient text for analysis (< 20 words)")

    agent = data.get("agent_readiness")
    if agent and (agent.get("ora") or agent.get("cloudflare")):
        lines.append(f"\n  AGENT READINESS")
        lines.append("  " + "─" * 44)
        if agent.get("ora"):
            ora = agent["ora"]
            lines.append(f"    Score: {ora['score']}/{ora['maxScore']}  ({ora['grade']})")
            if ora.get("summary"):
                lines.append(f"    {ora['summary'][:80]}")
            for layer in ora.get("layers", []):
                bar = _bar(layer["score"], layer["maxScore"])
                lines.append(f"    {layer['name']:<22} {bar}  {layer['score']}/{layer['maxScore']}")
        if agent.get("cloudflare"):
            cf = agent["cloudflare"]
            lines.append(f"    Cloudflare: Level {cf['level']} — {cf['levelName']}")

    actions = _build_action_plan(data)
    if actions:
        lines.append(f"\n  PRIORITY ACTION PLAN")
        lines.append("  " + "─" * 44)
        for i, (category, action, impact) in enumerate(actions, 1):
            lines.append(f"    {i}. [{category}] {action}")
            lines.append(f"       ({impact})")

    lines.append("")
    return "\n".join(lines)


def _build_action_plan(data):
    """Merge visibility recommendations and content fixes into a ranked list."""
    actions = []

    for rec in data["recommendations"][:4]:
        actions.append(("TECHNICAL", rec["title"], f"+{rec['points']}pts visibility"))

    cr = data["content_result"]
    if cr:
        signal_advice = {
            "burstiness": "Vary sentence lengths — mix short punchy sentences with longer ones",
            "vocabulary": "Replace generic filler words with specific, concrete terms",
            "hedging": "Replace hedging phrases with definitive, citable statements",
            "monotony": "Vary paragraph structure — start with questions, numbers, or quotes",
            "specificity": "Add concrete details: numbers, names, examples, data points",
        }
        worst = sorted(cr.signal_scores.items(), key=lambda x: x[1], reverse=True)
        for signal, score in worst:
            if score > 0.3:
                actions.append((
                    "CONTENT",
                    signal_advice.get(signal, f"Improve {signal}"),
                    f"{signal} at {round((1 - score) * 100)}%",
                ))

    return actions[:7]


def format_json(data):
    """Format as JSON for machine consumption."""
    out = {
        "url": data["url"],
        "combined_score": data["combined_score"],
        "visibility": {
            "total": data["visibility_total"],
            "scores": data["visibility_scores"],
            "recommendations": data["recommendations"],
        },
    }

    cr = data["content_result"]
    if cr:
        out["content"] = {
            "score_pct": data["content_pct"],
            "risk_level": cr.risk_level,
            "signal_scores": {k: round(v, 3) for k, v in cr.signal_scores.items()},
            "flag_count": len(cr.flags),
        }
    else:
        out["content"] = None

    out["action_plan"] = [
        {"category": c, "action": a, "impact": i}
        for c, a, i in _build_action_plan(data)
    ]

    out["agent_readiness"] = data.get("agent_readiness")

    return json.dumps(out, indent=2)


def _bridge_agent_result(agent_result: dict, url: str) -> dict:
    """Convert agent pipeline output into the shape the dashboard expects.

    The agent pipeline returns an AnalysisComplete with crawl_data nested
    inside. The dashboard expects the flat dict that run_pipeline() returns.
    This bridges between the two, preserving LLM-generated fields as extras.
    """
    # raw_scores carries the full crawl_data dict from the reasoning agent
    crawl = agent_result.get("raw_scores", {})
    if not crawl:
        crawl = agent_result.get("crawl_data", {})

    visibility_scores = crawl.get("visibility_scores", {})
    visibility_total = sum(visibility_scores.values())
    content_results = crawl.get("content_results", [])

    # Reconstruct content_result as a simple namespace for .risk_level etc.
    content_result = None
    content_pct = None
    if content_results:
        cr = content_results[0]
        content_pct = cr.get("score_pct")

        class ContentProxy:
            pass
        content_result = ContentProxy()
        content_result.risk_level = cr.get("risk_level", "UNKNOWN")
        content_result.signal_scores = cr.get("signal_scores", {})
        content_result.overall_score = (1 - content_pct / 100) if content_pct else 0.5
        content_result.flags = []
        content_result.text = ""

    if content_pct is not None:
        combined = round(visibility_total * 0.5 + content_pct * 0.5)
    else:
        combined = visibility_total

    data = {
        "url": url,
        "combined_score": combined,
        "visibility_total": visibility_total,
        "visibility_scores": visibility_scores,
        "signals": crawl.get("signals", {}),
        "recommendations": crawl.get("recommendations", []),
        "content_pct": content_pct,
        "content_result": content_result,
        "agent_readiness": crawl.get("agent_readiness"),
        # LLM-generated extras from the reasoning agent
        "executive_summary": agent_result.get("executive_summary", ""),
        "delta_narrative": agent_result.get("delta_narrative", ""),
        "rewritten_meta": agent_result.get("rewritten_meta", []),
        "content_suggestions": agent_result.get("content_suggestions", []),
        "priority_actions": agent_result.get("priority_actions", []),
    }
    return data


def main():
    parser = argparse.ArgumentParser(
        prog="aeo-pipeline",
        description="AI Readiness Assessment — visibility + content quality in one scan",
    )
    parser.add_argument("url", help="Public URL to audit")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--no-browser", action="store_true", help="Print to terminal instead of opening dashboard")
    parser.add_argument("--agents", action="store_true", help="Use multi-agent pipeline (Firecrawl + Mitosis + LLM)")
    args = parser.parse_args()

    url = args.url
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    parsed = urlparse(url)
    if not parsed.netloc:
        print(f"Error: invalid URL '{args.url}'", file=sys.stderr)
        sys.exit(1)

    if args.agents:
        print(f"Scanning {url} (multi-agent mode) ...\n", file=sys.stderr)
        from .agents.orchestrator import run_sync
        agent_result = run_sync(url)
        if agent_result.get("error"):
            print(f"Error: {agent_result['error']}", file=sys.stderr)
            sys.exit(1)
        data = _bridge_agent_result(agent_result, url)
    else:
        print(f"Scanning {url} ...\n", file=sys.stderr)
        data, error = run_pipeline(url)
        if error:
            print(f"Error: {error}", file=sys.stderr)
            sys.exit(1)

    if args.json:
        print(format_json(data))
    elif args.no_browser:
        print(format_report(data))
    else:
        print(format_report(data))
        from .dashboard import start_dashboard
        start_dashboard(data)


if __name__ == "__main__":
    main()
