#!/usr/bin/env python3
"""AEO Toolkit MCP Server — exposes AI visibility tools via Model Context Protocol.

Zero external dependencies. Runs over stdin/stdout using JSON-RPC 2.0.
Add to claude_desktop_config.json or .claude.json:

  "mcpServers": {
    "aeo-toolkit": {
      "command": "python3",
      "args": ["/path/to/rote-playoffs/mcp_server.py"]
    }
  }
"""

import json
import sys
import traceback
from dataclasses import asdict

# Ensure project root is importable
sys.path.insert(0, __file__.rsplit("/", 1)[0] if "/" in __file__ else ".")

TOOLS = [
    {
        "name": "audit_url",
        "description": (
            "Run an AI visibility audit on a URL. Returns a 0-100 score across "
            "four dimensions: AI crawler access, structured data, content citability, "
            "and entity/authority signals. Includes prioritized fix recommendations "
            "with copy-paste code snippets. No API keys required."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to audit (e.g. 'example.com' or 'https://example.com')",
                }
            },
            "required": ["url"],
        },
    },
    {
        "name": "analyze_content",
        "description": (
            "Analyze text content for citability using 5 heuristic signals: "
            "burstiness (sentence length variation), vocabulary (generic filler words), "
            "hedging (weak qualifiers), structural monotony (repetitive patterns), and "
            "specificity (concrete details vs vague claims). Returns per-signal scores "
            "and an overall quality rating. Useful for checking whether AI assistants "
            "are likely to cite this content."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text content to analyze",
                },
                "url": {
                    "type": "string",
                    "description": "Optional URL to fetch and analyze instead of providing text directly",
                },
            },
        },
    },
    {
        "name": "full_pipeline",
        "description": (
            "Run the complete AEO pipeline on a URL: technical visibility audit + "
            "content quality analysis + agent readiness check. Returns a combined "
            "AI Readiness Score (0-100) with letter grade, dimensional breakdowns, "
            "and actionable recommendations. This is the most comprehensive analysis."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to analyze (e.g. 'example.com' or 'https://example.com')",
                }
            },
            "required": ["url"],
        },
    },
]


def _normalize_url(url):
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def _handle_audit_url(args):
    from score import (
        PageExtractor, fetch_all, score_crawler_access,
        score_structured_data, score_content_citability,
        score_entity_authority, generate_recommendations,
    )

    url = _normalize_url(args["url"])
    fetched = fetch_all(url)

    if fetched["html"][0] == 0:
        return [{"type": "text", "text": f"Error: could not reach {url}"}]

    ext = PageExtractor()
    ext.feed(fetched["html"][1])
    ext.close()

    crawler_score, crawler_signals = score_crawler_access(fetched)
    structured_score, structured_signals = score_structured_data(ext)
    citability_score, citability_signals = score_content_citability(ext)
    authority_score, authority_signals = score_entity_authority(ext)

    scores = {
        "crawler_access": {"score": crawler_score, "max": 25},
        "structured_data": {"score": structured_score, "max": 30},
        "content_citability": {"score": citability_score, "max": 25},
        "entity_authority": {"score": authority_score, "max": 20},
    }
    total = crawler_score + structured_score + citability_score + authority_score

    all_signals = {}
    all_signals.update(crawler_signals)
    all_signals.update(structured_signals)
    all_signals.update(citability_signals)
    all_signals.update(authority_signals)

    recs = generate_recommendations(ext, fetched, all_signals, input_url=url)

    grade = (
        "A" if total >= 80 else
        "B" if total >= 60 else
        "C" if total >= 40 else
        "D" if total >= 20 else "F"
    )

    result = {
        "url": url,
        "total_score": total,
        "grade": grade,
        "dimensions": scores,
        "recommendations": recs[:5],
    }

    return [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]


def _handle_analyze_content(args):
    from aeo_writer.detector import analyze

    text = args.get("text", "")

    if not text and args.get("url"):
        from score import fetch_url
        from aeo_pipeline.__main__ import _extract_text
        url = _normalize_url(args["url"])
        status, html = fetch_url(url)
        if status == 0:
            return [{"type": "text", "text": f"Error: could not reach {url}"}]
        text = _extract_text(html)

    if not text or len(text.split()) < 20:
        return [{"type": "text", "text": "Error: not enough text to analyze (need at least 20 words)"}]

    result = analyze(text)

    quality_pct = round((1 - result.overall_score) * 100)

    output = {
        "quality_score": quality_pct,
        "risk_level": result.risk_level,
        "signal_scores": {
            k: {
                "raw": v,
                "quality": round((1 - v) * 100),
                "interpretation": (
                    "strong" if v < 0.3 else
                    "needs work" if v < 0.6 else
                    "weak"
                ),
            }
            for k, v in result.signal_scores.items()
        },
        "flags_count": len(result.flags),
        "top_flags": [
            {
                "signal": f.signal,
                "annotation": f.annotation,
                "suggestion": f.suggestion,
                "text_excerpt": result.text[f.start:f.end][:100],
            }
            for f in sorted(result.flags, key=lambda f: f.score, reverse=True)[:10]
        ],
    }

    return [{"type": "text", "text": json.dumps(output, indent=2, default=str)}]


def _handle_full_pipeline(args):
    from aeo_pipeline.__main__ import run_pipeline

    url = _normalize_url(args["url"])
    data, err = run_pipeline(url)

    if err:
        return [{"type": "text", "text": f"Error: {err}"}]

    grade = (
        "A" if data["combined_score"] >= 80 else
        "B" if data["combined_score"] >= 60 else
        "C" if data["combined_score"] >= 40 else
        "D" if data["combined_score"] >= 20 else "F"
    )

    content_signals = None
    if data.get("content_result"):
        cr = data["content_result"]
        content_signals = {
            k: {"quality": round((1 - v) * 100)}
            for k, v in cr.signal_scores.items()
        }

    agent_summary = None
    if data.get("agent_readiness"):
        ar = data["agent_readiness"]
        agent_summary = {
            "score": ar.get("score"),
            "grade": ar.get("grade"),
            "discovery": ar.get("discovery"),
            "access": ar.get("access"),
        }

    result = {
        "url": data["url"],
        "ai_readiness_score": data["combined_score"],
        "grade": grade,
        "technical_visibility": {
            "total": data["visibility_total"],
            "dimensions": data["visibility_scores"],
        },
        "content_quality": {
            "score": data.get("content_pct"),
            "signals": content_signals,
        },
        "agent_readiness": agent_summary,
        "recommendations": data["recommendations"][:5],
    }

    return [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]


HANDLERS = {
    "audit_url": _handle_audit_url,
    "analyze_content": _handle_analyze_content,
    "full_pipeline": _handle_full_pipeline,
}


def _respond(id, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": id}
    if error:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _notify(method, params=None):
    msg = {"jsonrpc": "2.0", "method": method}
    if params:
        msg["params"] = params
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method", "")
        id = msg.get("id")
        params = msg.get("params", {})

        if method == "initialize":
            _respond(id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                },
                "serverInfo": {
                    "name": "aeo-toolkit",
                    "version": "2.0.0",
                },
            })

        elif method == "notifications/initialized":
            pass

        elif method == "tools/list":
            _respond(id, {"tools": TOOLS})

        elif method == "tools/call":
            name = params.get("name", "")
            arguments = params.get("arguments", {})

            handler = HANDLERS.get(name)
            if not handler:
                _respond(id, error={
                    "code": -32601,
                    "message": f"Unknown tool: {name}",
                })
                continue

            try:
                content = handler(arguments)
                _respond(id, {"content": content})
            except Exception as e:
                _respond(id, {"content": [
                    {"type": "text", "text": f"Error running {name}: {e}"},
                ], "isError": True})

        elif method == "ping":
            _respond(id, {})

        elif id is not None:
            _respond(id, error={
                "code": -32601,
                "message": f"Method not found: {method}",
            })


if __name__ == "__main__":
    main()
