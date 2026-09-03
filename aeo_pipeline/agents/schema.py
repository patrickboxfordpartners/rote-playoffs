"""Domain-specific message schemas for the AEO agent mesh.

Every message on the Cotal mesh is a CotalMessage envelope. These dataclasses
define the payloads our agents exchange -- typed, serializable, and validated.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
import json
import time
import uuid


@dataclass
class CrawlRequest:
    """Orchestrator -> Crawl Agent: scan this domain."""
    url: str
    depth: int = 0  # 0 = single page, -1 = full domain
    job_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)


@dataclass
class PageResult:
    """One page's extracted data from the crawl."""
    url: str
    title: str = ""
    word_count: int = 0
    has_schema: bool = False
    has_meta_desc: bool = False
    schema_types: list = field(default_factory=list)
    text_preview: str = ""


@dataclass
class CrawlComplete:
    """Crawl Agent -> Memory Agent: here's what we found."""
    job_id: str
    root_url: str
    pages: list = field(default_factory=list)  # list of PageResult dicts
    visibility_scores: dict = field(default_factory=dict)
    signals: dict = field(default_factory=dict)
    agent_readiness: Optional[dict] = None
    recommendations: list = field(default_factory=list)
    content_results: list = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ScanDelta:
    """A single metric that changed between scans."""
    metric: str
    previous: float
    current: float
    direction: str = ""  # "improved", "declined", "unchanged"

    def __post_init__(self):
        if not self.direction:
            if self.current > self.previous:
                self.direction = "improved"
            elif self.current < self.previous:
                self.direction = "declined"
            else:
                self.direction = "unchanged"


@dataclass
class MemoryEnriched:
    """Memory Agent -> Reasoning Agent: crawl data + historical context."""
    job_id: str
    root_url: str
    crawl_data: dict = field(default_factory=dict)
    prior_scan: Optional[dict] = None
    deltas: list = field(default_factory=list)  # list of ScanDelta dicts
    client_context: Optional[str] = None
    scan_count: int = 1
    timestamp: float = field(default_factory=time.time)


@dataclass
class AnalysisComplete:
    """Reasoning Agent -> Orchestrator: the final intelligence product."""
    job_id: str
    root_url: str
    executive_summary: str = ""
    delta_narrative: str = ""
    rewritten_meta: list = field(default_factory=list)
    content_suggestions: list = field(default_factory=list)
    priority_actions: list = field(default_factory=list)
    raw_scores: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


def envelope(sender: str, channel: str, payload) -> dict:
    """Wrap a payload in a CotalMessage envelope."""
    return {
        "v": "0.4",
        "id": str(uuid.uuid4()),
        "sender": sender,
        "channel": channel,
        "payload": asdict(payload) if hasattr(payload, "__dataclass_fields__") else payload,
        "ts": time.time(),
    }


def to_json(msg: dict) -> bytes:
    return json.dumps(msg, default=str).encode()


def from_json(data: bytes) -> dict:
    return json.loads(data.decode())
