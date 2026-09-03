"""Cotal mesh connection and agent lifecycle.

Thin client over nats.py that handles:
- Connecting to the local Cotal mesh (NATS broker)
- Agent registration via heartbeat
- Channel pub/sub for inter-agent messaging
- Graceful shutdown
"""

import asyncio
import json
import os
import time
from typing import Callable, Optional

NATS_URL = os.environ.get("COTAL_NATS_URL", "nats://127.0.0.1:4222")
HEARTBEAT_INTERVAL = 10.0

# Channel names for our pipeline
CH_CRAWL_REQUEST = "aeo.crawl.request"
CH_CRAWL_COMPLETE = "aeo.crawl.complete"
CH_MEMORY_ENRICHED = "aeo.memory.enriched"
CH_ANALYSIS_COMPLETE = "aeo.analysis.complete"


class AgentCard:
    """Identity card broadcast on the presence KV bucket."""

    def __init__(self, agent_id: str, role: str, capabilities: list = None):
        self.agent_id = agent_id
        self.role = role
        self.capabilities = capabilities or []

    def to_dict(self):
        return {
            "id": self.agent_id,
            "role": self.role,
            "capabilities": self.capabilities,
            "protocolVersion": "0.4",
            "ts": time.time(),
        }


class MeshConnection:
    """Manages a single agent's connection to the Cotal mesh."""

    def __init__(self, card: AgentCard, creds_path: str = None):
        self.card = card
        self.creds_path = creds_path or os.environ.get("COTAL_CREDS")
        self._nc = None
        self._js = None
        self._subs = []
        self._heartbeat_task = None
        self._running = False

    async def connect(self):
        try:
            import nats
        except ImportError:
            raise ImportError("nats-py required: pip install nats-py")

        connect_opts = {"servers": [NATS_URL]}
        if self.creds_path:
            connect_opts["user_credentials"] = self.creds_path

        self._nc = await nats.connect(**connect_opts)
        self._js = self._nc.jetstream()
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self):
        """Broadcast presence on the KV bucket."""
        try:
            kv = await self._js.key_value(bucket="presence")
        except Exception:
            # Bucket may not exist yet in dev -- create it
            kv = await self._js.create_key_value(config={"bucket": "presence", "ttl": 30})

        while self._running:
            try:
                await kv.put(self.card.agent_id, json.dumps(self.card.to_dict()).encode())
            except Exception:
                pass
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def publish(self, channel: str, data: bytes):
        """Publish a message to a channel."""
        if self._nc:
            await self._nc.publish(channel, data)

    async def subscribe(self, channel: str, handler: Callable):
        """Subscribe to a channel with an async handler."""
        if self._nc:
            sub = await self._nc.subscribe(channel, cb=handler)
            self._subs.append(sub)
            return sub

    async def request(self, channel: str, data: bytes, timeout: float = 60.0) -> bytes:
        """Request-reply pattern for synchronous workflows."""
        if self._nc:
            resp = await self._nc.request(channel, data, timeout=timeout)
            return resp.data

    async def get_peers(self) -> list:
        """List all agents currently on the mesh."""
        try:
            kv = await self._js.key_value(bucket="presence")
            keys = await kv.keys()
            peers = []
            for key in keys:
                entry = await kv.get(key)
                if entry and entry.value:
                    peers.append(json.loads(entry.value.decode()))
            return peers
        except Exception:
            return []

    async def shutdown(self):
        """Clean disconnect from the mesh."""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        for sub in self._subs:
            await sub.unsubscribe()
        if self._nc:
            await self._nc.close()


class LocalBus:
    """In-process message bus for when Cotal mesh isn't available.

    Same interface as MeshConnection but routes messages in-memory.
    Lets the full agent pipeline run without a NATS broker -- useful for
    development, testing, and the hackathon demo.
    """

    def __init__(self, card: AgentCard):
        self.card = card
        self._handlers: dict[str, list[Callable]] = {}

    async def connect(self):
        pass

    async def publish(self, channel: str, data: bytes):
        for handler in self._handlers.get(channel, []):
            await handler(type("Msg", (), {"data": data, "subject": channel})())

    async def subscribe(self, channel: str, handler: Callable):
        self._handlers.setdefault(channel, []).append(handler)

    async def request(self, channel: str, data: bytes, timeout: float = 60.0) -> bytes:
        return b"{}"

    async def get_peers(self) -> list:
        return [self.card.to_dict()]

    async def shutdown(self):
        self._handlers.clear()
