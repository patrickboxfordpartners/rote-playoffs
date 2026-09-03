"""Orchestrator — the entrypoint for multi-agent scans.

Bootstraps the mesh (Cotal or local bus), starts all agents, submits
a crawl request, and collects the final analysis. Returns a result dict
compatible with the existing dashboard.
"""

import asyncio
import os

from .schema import CrawlRequest, envelope, to_json, from_json
from .mesh import (
    AgentCard, MeshConnection, LocalBus,
    CH_CRAWL_REQUEST, CH_ANALYSIS_COMPLETE,
)
from . import crawl_agent, memory_agent, reasoning_agent


AGENT_ID = "aeo-orchestrator"


async def run_agent_pipeline(url: str, mcp_tools=None) -> dict:
    """Run the full multi-agent scan pipeline.

    Returns a dict with:
        - All fields from the standard pipeline (for dashboard compat)
        - Additional fields: executive_summary, delta_narrative,
          rewritten_meta, content_suggestions, priority_actions
    """
    # Decide: real Cotal mesh or local in-process bus
    use_mesh = os.environ.get("COTAL_NATS_URL") or os.environ.get("COTAL_CREDS")

    if use_mesh:
        card = AgentCard(AGENT_ID, "orchestrator", ["coordinate", "dispatch"])
        bus = MeshConnection(card)
    else:
        card = AgentCard(AGENT_ID, "orchestrator", ["coordinate", "dispatch"])
        bus = LocalBus(card)

    await bus.connect()

    # Result collector
    result_future = asyncio.get_event_loop().create_future()

    async def on_analysis_complete(msg):
        data = from_json(msg.data)
        payload = data.get("payload", data)
        if not result_future.done():
            result_future.set_result(payload)

    # Start all agents
    await crawl_agent.start(bus)
    await memory_agent.start(bus, mcp_tools=mcp_tools)
    await reasoning_agent.start(bus)
    await bus.subscribe(CH_ANALYSIS_COMPLETE, on_analysis_complete)

    # Submit the crawl request
    request = CrawlRequest(url=url)
    out = envelope(AGENT_ID, CH_CRAWL_REQUEST, request)
    await bus.publish(CH_CRAWL_REQUEST, to_json(out))

    # Wait for the analysis to complete (timeout 5 min)
    try:
        result = await asyncio.wait_for(result_future, timeout=300)
    except asyncio.TimeoutError:
        result = {"error": "Pipeline timed out after 5 minutes"}

    await bus.shutdown()
    return result


def run_sync(url: str, mcp_tools=None) -> dict:
    """Synchronous wrapper for CLI usage."""
    return asyncio.run(run_agent_pipeline(url, mcp_tools=mcp_tools))
