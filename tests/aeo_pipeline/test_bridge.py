"""Tests for _bridge_agent_result — converts agent output to dashboard shape."""

from aeo_pipeline.__main__ import _bridge_agent_result


def test_bridge_basic_shape():
    agent_result = {
        "raw_scores": {
            "visibility_scores": {"crawler": 25, "structured": 20, "citability": 10, "authority": 10},
            "signals": {"robots_txt": True},
            "recommendations": [{"title": "Fix X", "points": 3, "why": "Y"}],
            "content_results": [{"score_pct": 80, "risk_level": "MODERATE", "signal_scores": {"burstiness": 0.2}}],
            "agent_readiness": None,
        },
        "executive_summary": "Test summary",
        "delta_narrative": "",
        "rewritten_meta": [],
        "content_suggestions": ["Add FAQ"],
        "priority_actions": [{"action": "Do X", "impact": "High", "difficulty": "easy"}],
    }
    data = _bridge_agent_result(agent_result, "https://example.com")

    assert data["url"] == "https://example.com"
    assert data["visibility_total"] == 65
    assert data["content_pct"] == 80
    assert data["combined_score"] == round(65 * 0.5 + 80 * 0.5)
    assert data["executive_summary"] == "Test summary"
    assert len(data["content_suggestions"]) == 1
    assert len(data["priority_actions"]) == 1


def test_bridge_content_proxy_has_attributes():
    agent_result = {
        "raw_scores": {
            "visibility_scores": {"crawler": 20, "structured": 15, "citability": 5, "authority": 5},
            "content_results": [{"score_pct": 70, "risk_level": "MODERATE", "signal_scores": {"burstiness": 0.3}}],
        },
    }
    data = _bridge_agent_result(agent_result, "https://test.com")
    cr = data["content_result"]
    assert cr is not None
    assert cr.risk_level == "MODERATE"
    assert cr.signal_scores == {"burstiness": 0.3}
    assert hasattr(cr, "flags")
    assert hasattr(cr, "text")


def test_bridge_no_content():
    agent_result = {
        "raw_scores": {
            "visibility_scores": {"crawler": 25, "structured": 25, "citability": 10, "authority": 10},
            "content_results": [],
        },
    }
    data = _bridge_agent_result(agent_result, "https://test.com")
    assert data["content_result"] is None
    assert data["content_pct"] is None
    assert data["combined_score"] == 70  # visibility only


def test_bridge_falls_back_to_crawl_data_key():
    agent_result = {
        "crawl_data": {
            "visibility_scores": {"crawler": 10, "structured": 10, "citability": 5, "authority": 5},
            "content_results": [],
        },
    }
    data = _bridge_agent_result(agent_result, "https://test.com")
    assert data["visibility_total"] == 30


def test_bridge_empty_agent_result():
    data = _bridge_agent_result({}, "https://test.com")
    assert data["visibility_total"] == 0
    assert data["content_result"] is None
    assert data["combined_score"] == 0
    assert data["executive_summary"] == ""
