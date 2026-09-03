"""Tests for the MCP server protocol handling."""

import json
import subprocess
import sys
import os

import pytest

MCP_SERVER = os.path.join(os.path.dirname(__file__), "..", "mcp_server.py")


def _send(messages):
    """Send JSON-RPC messages to the MCP server, return parsed responses."""
    input_text = "\n".join(json.dumps(m) for m in messages) + "\n"
    result = subprocess.run(
        [sys.executable, MCP_SERVER],
        input=input_text,
        capture_output=True,
        text=True,
        timeout=5,
    )
    responses = []
    for line in result.stdout.strip().split("\n"):
        if line.strip():
            responses.append(json.loads(line))
    return responses


def _init_then(*calls):
    """Prepend initialize + initialized, then add caller's messages."""
    msgs = [
        {"jsonrpc": "2.0", "id": 0, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    ]
    msgs.extend(calls)
    responses = _send(msgs)
    return [r for r in responses if r.get("id") != 0]


class TestProtocol:
    def test_initialize(self):
        responses = _send([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1.0"}}},
        ])
        assert len(responses) == 1
        r = responses[0]
        assert r["id"] == 1
        assert r["result"]["serverInfo"]["name"] == "aeo-toolkit"
        assert "tools" in r["result"]["capabilities"]

    def test_tools_list(self):
        responses = _init_then(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert len(responses) == 1
        tools = responses[0]["result"]["tools"]
        names = {t["name"] for t in tools}
        assert names == {"audit_url", "analyze_content", "full_pipeline"}

    def test_tool_schemas(self):
        responses = _init_then(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        tools = {t["name"]: t for t in responses[0]["result"]["tools"]}

        assert "url" in tools["audit_url"]["inputSchema"]["properties"]
        assert tools["audit_url"]["inputSchema"]["required"] == ["url"]

        assert "text" in tools["analyze_content"]["inputSchema"]["properties"]
        assert "url" in tools["analyze_content"]["inputSchema"]["properties"]

        assert "url" in tools["full_pipeline"]["inputSchema"]["properties"]
        assert tools["full_pipeline"]["inputSchema"]["required"] == ["url"]

    def test_ping(self):
        responses = _init_then(
            {"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
        assert responses[0]["result"] == {}

    def test_unknown_method(self):
        responses = _init_then(
            {"jsonrpc": "2.0", "id": 1, "method": "nonexistent/method"},
        )
        assert "error" in responses[0]
        assert responses[0]["error"]["code"] == -32601

    def test_unknown_tool(self):
        responses = _init_then(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "no_such_tool", "arguments": {}}},
        )
        assert "error" in responses[0]


class TestAnalyzeContent:
    def test_inline_text(self):
        text = (
            "In 2024, Boxford Partners shipped 12 production systems across "
            "industries including real estate, insurance, and legal tech. "
            "The firm charges fixed prices between $5K and $25K. "
            "Their embed-observe-build methodology starts with direct observation. "
            "About a third of conversations do not result in a project."
        )
        responses = _init_then(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "analyze_content", "arguments": {"text": text}}},
        )
        content = responses[0]["result"]["content"]
        result = json.loads(content[0]["text"])
        assert "quality_score" in result
        assert "signal_scores" in result
        assert "burstiness" in result["signal_scores"]
        assert 0 <= result["quality_score"] <= 100

    def test_empty_text(self):
        responses = _init_then(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "analyze_content", "arguments": {"text": "too short"}}},
        )
        content = responses[0]["result"]["content"]
        assert "Error" in content[0]["text"]
