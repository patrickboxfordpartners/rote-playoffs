"""Tests for the dashboard data serialization."""

import json
from unittest.mock import MagicMock
from aeo_pipeline.dashboard import _serialize_data, _build_actions, _script_safe


def _make_content_result(score=0.3, risk="MODERATE"):
    cr = MagicMock()
    cr.risk_level = risk
    cr.signal_scores = {
        "burstiness": 0.2,
        "vocabulary": 0.4,
        "hedging": 0.1,
        "monotony": 0.3,
        "specificity": 0.5,
    }
    cr.overall_score = score
    cr.flags = []
    cr.text = "Some sample text for testing."
    return cr


def _make_data(content_result=None, **overrides):
    data = {
        "url": "https://example.com",
        "combined_score": 72,
        "visibility_total": 65,
        "visibility_scores": {"crawler": 25, "structured": 20, "citability": 10, "authority": 10},
        "signals": {"robots_txt": True, "llms_txt": False},
        "recommendations": [{"title": "Add llms.txt", "points": 5, "why": "Helps AI", "code": "# llms.txt"}],
        "content_pct": 80,
        "content_result": content_result or _make_content_result(),
    }
    data.update(overrides)
    return data


def test_serialize_data_returns_valid_json():
    data = _make_data()
    raw = _serialize_data(data)
    parsed = json.loads(raw)
    assert parsed["url"] == "https://example.com"
    assert parsed["combined_score"] == 72
    assert parsed["visibility_total"] == 65
    assert parsed["domain"] == "example.com"


def test_serialize_data_includes_llm_fields():
    data = _make_data(
        executive_summary="Your site scores well.",
        delta_narrative="Visibility improved by 10 points.",
        rewritten_meta=[{"url": "/about", "current": "old", "suggested": "new"}],
        content_suggestions=["Add FAQ sections."],
        priority_actions=[{"action": "Fix schema", "impact": "High", "difficulty": "easy"}],
    )
    raw = _serialize_data(data)
    parsed = json.loads(raw)
    assert parsed["executive_summary"] == "Your site scores well."
    assert parsed["delta_narrative"] == "Visibility improved by 10 points."
    assert len(parsed["rewritten_meta"]) == 1
    assert len(parsed["content_suggestions"]) == 1
    assert len(parsed["priority_actions"]) == 1


def test_serialize_data_defaults_llm_fields_to_empty():
    data = _make_data()
    raw = _serialize_data(data)
    parsed = json.loads(raw)
    assert parsed["executive_summary"] == ""
    assert parsed["delta_narrative"] == ""
    assert parsed["rewritten_meta"] == []
    assert parsed["content_suggestions"] == []
    assert parsed["priority_actions"] == []


def test_serialize_data_null_content():
    data = _make_data()
    data["content_result"] = None
    data["content_pct"] = None
    raw = _serialize_data(data)
    parsed = json.loads(raw)
    assert parsed["content_risk_level"] is None
    assert parsed["content_signal_scores"] is None
    assert parsed["content_flags"] == []


def test_serialize_data_includes_agent_readiness():
    ar = {"ora": {"score": 44, "maxScore": 100, "grade": "D"}, "cloudflare": {"level": 1}}
    data = _make_data(agent_readiness=ar)
    raw = _serialize_data(data)
    parsed = json.loads(raw)
    assert parsed["agent_readiness"]["ora"]["score"] == 44


def test_build_actions_includes_content_advice():
    data = _make_data()
    actions = _build_actions(data)
    categories = [a[0] for a in actions]
    assert "TECHNICAL" in categories
    assert "CONTENT" in categories


def test_build_actions_limits_count():
    recs = [{"title": f"Fix {i}", "points": i, "why": "t", "code": "c"} for i in range(10)]
    data = _make_data(recommendations=recs)
    actions = _build_actions(data)
    assert len(actions) <= 7


def test_script_safe_escapes_closing_script_tag():
    # A JSON-LD recommendation snippet contains a literal </script>, which would
    # otherwise close the dashboard's inline <script> early and break rendering.
    code = '<script type="application/ld+json">{"@type":"Organization"}</script>'
    raw = _serialize_data(_make_data(
        recommendations=[{"title": "Add schema", "points": 5, "why": "AI", "code": code}]
    ))
    safe = _script_safe(raw)
    assert "</script>" not in safe
    assert "\\u003c/script>" in safe
    # Still decodes back to the original JSON payload.
    assert json.loads(safe.replace("\\u003c", "<"))["recommendations"][0]["code"] == code
