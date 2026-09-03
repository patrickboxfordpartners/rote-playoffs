"""Tests for the multi-agent intelligence layer."""

import asyncio
import json

from aeo_pipeline.agents.schema import (
    CrawlRequest, PageResult, CrawlComplete, ScanDelta,
    MemoryEnriched, AnalysisComplete, envelope, to_json, from_json,
)
from aeo_pipeline.agents.mesh import AgentCard, LocalBus, CH_CRAWL_REQUEST, CH_ANALYSIS_COMPLETE
from aeo_pipeline.agents.reasoning_agent import _fallback_analysis, _build_analysis_prompt


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

def test_crawl_request_defaults():
    req = CrawlRequest(url="https://example.com")
    assert req.url == "https://example.com"
    assert req.depth == 0
    assert len(req.job_id) == 8
    assert req.timestamp > 0


def test_page_result_defaults():
    pr = PageResult(url="https://example.com/about")
    assert pr.word_count == 0
    assert pr.has_schema is False
    assert pr.schema_types == []


def test_crawl_complete_defaults():
    cc = CrawlComplete(job_id="abc", root_url="https://example.com")
    assert cc.pages == []
    assert cc.visibility_scores == {}
    assert cc.content_results == []


def test_scan_delta_direction():
    improved = ScanDelta(metric="Visibility", previous=50.0, current=70.0)
    assert improved.direction == "improved"

    declined = ScanDelta(metric="Content", previous=80.0, current=60.0)
    assert declined.direction == "declined"

    unchanged = ScanDelta(metric="Agent", previous=50.0, current=50.0)
    assert unchanged.direction == "unchanged"


def test_envelope_wraps_payload():
    req = CrawlRequest(url="https://test.com")
    msg = envelope("agent-1", "test.channel", req)
    assert msg["sender"] == "agent-1"
    assert msg["channel"] == "test.channel"
    assert msg["payload"]["url"] == "https://test.com"
    assert "id" in msg
    assert "ts" in msg


def test_to_json_and_from_json_roundtrip():
    req = CrawlRequest(url="https://test.com")
    msg = envelope("a", "ch", req)
    data = to_json(msg)
    assert isinstance(data, bytes)
    parsed = from_json(data)
    assert parsed["payload"]["url"] == "https://test.com"


# ---------------------------------------------------------------------------
# LocalBus tests
# ---------------------------------------------------------------------------

def test_local_bus_pub_sub():
    async def _test():
        card = AgentCard("test", "tester", [])
        bus = LocalBus(card)
        await bus.connect()

        received = []

        async def handler(msg):
            received.append(from_json(msg.data))

        await bus.subscribe("test.channel", handler)
        await bus.publish("test.channel", to_json({"hello": "world"}))

        assert len(received) == 1
        assert received[0]["hello"] == "world"

        await bus.shutdown()

    asyncio.run(_test())


def test_local_bus_multiple_subscribers():
    async def _test():
        card = AgentCard("test", "tester", [])
        bus = LocalBus(card)
        await bus.connect()

        count = [0]

        async def handler1(msg):
            count[0] += 1

        async def handler2(msg):
            count[0] += 10

        await bus.subscribe("ch", handler1)
        await bus.subscribe("ch", handler2)
        await bus.publish("ch", to_json({"x": 1}))

        assert count[0] == 11

        await bus.shutdown()

    asyncio.run(_test())


def test_local_bus_no_crosstalk():
    async def _test():
        card = AgentCard("test", "tester", [])
        bus = LocalBus(card)
        await bus.connect()

        received = []

        async def handler(msg):
            received.append(True)

        await bus.subscribe("channel.a", handler)
        await bus.publish("channel.b", to_json({"x": 1}))

        assert len(received) == 0

        await bus.shutdown()

    asyncio.run(_test())


def test_local_bus_get_peers():
    async def _test():
        card = AgentCard("my-agent", "worker", ["scan"])
        bus = LocalBus(card)
        peers = await bus.get_peers()
        assert len(peers) == 1
        assert peers[0]["id"] == "my-agent"

    asyncio.run(_test())


def test_agent_card_to_dict():
    card = AgentCard("crawl-1", "crawler", ["scrape", "extract"])
    d = card.to_dict()
    assert d["id"] == "crawl-1"
    assert d["role"] == "crawler"
    assert d["capabilities"] == ["scrape", "extract"]
    assert d["protocolVersion"] == "0.4"


# ---------------------------------------------------------------------------
# Reasoning agent fallback tests
# ---------------------------------------------------------------------------

def test_fallback_analysis_extracts_visibility():
    prompt = "## Scores\n- Visibility: 65/100\n- Content Quality: 80/100"
    result = _fallback_analysis(prompt)
    assert "65/100" in result["executive_summary"]
    assert "80/100" in result["executive_summary"]
    assert result["delta_narrative"] == ""


def test_fallback_analysis_generates_actions_for_missing_schema():
    prompt = "## Scores\n- Visibility: 45/100\n## Site Structure\n- 3 pages missing structured data\n- 2 pages missing meta descriptions"
    result = _fallback_analysis(prompt)
    actions = result["priority_actions"]
    assert len(actions) >= 2
    action_texts = [a["action"] for a in actions]
    assert any("structured data" in a for a in action_texts)
    assert any("meta descriptions" in a for a in action_texts)


def test_fallback_analysis_empty_prompt():
    result = _fallback_analysis("")
    assert "executive_summary" in result
    assert isinstance(result["priority_actions"], list)
    assert isinstance(result["content_suggestions"], list)


def test_fallback_analysis_high_scores():
    prompt = "## Scores\n- Visibility: 85/100\n- Content Quality: 92/100"
    result = _fallback_analysis(prompt)
    assert "excellent" in result["executive_summary"].lower()


def test_build_analysis_prompt_includes_scores():
    enriched = {
        "root_url": "https://example.com",
        "crawl_data": {
            "visibility_scores": {"crawler": 25, "structured": 20, "citability": 10, "authority": 10},
            "content_results": [{"score_pct": 80, "risk_level": "MODERATE"}],
            "pages": [{"url": "https://example.com", "has_schema": True, "has_meta_desc": True, "word_count": 500}],
            "recommendations": [{"title": "Add llms.txt", "points": 5, "why": "Helps AI"}],
        },
        "deltas": [],
        "client_context": "",
        "scan_count": 1,
    }
    prompt = _build_analysis_prompt(enriched)
    assert "Visibility: 65/100" in prompt
    assert "Content Quality: 80/100" in prompt
    assert "1 pages crawled" in prompt
    assert "Add llms.txt" in prompt


def test_build_analysis_prompt_includes_deltas():
    enriched = {
        "root_url": "https://example.com",
        "crawl_data": {"visibility_scores": {"crawler": 25}, "pages": []},
        "deltas": [{"metric": "Visibility Score", "previous": 50, "current": 65, "direction": "improved"}],
        "client_context": "Enterprise client, Q4 priority.",
        "scan_count": 3,
    }
    prompt = _build_analysis_prompt(enriched)
    assert "Changes Since Last Scan" in prompt
    assert "50 -> 65" in prompt
    assert "Enterprise client" in prompt
    assert "scan #3" in prompt
