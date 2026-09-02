# AI Visibility Audit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Rote Play that scores any public URL's discoverability to AI assistants (0-100) and outputs ranked fix recommendations with copy-pasteable code.

**Architecture:** Single Python3 script (`score.py`) using only stdlib. Fetches 5 URLs in parallel (HTML, robots.txt, llms.txt, llms-full.txt, sitemap.xml), scores 4 dimensions (Crawler Access, Structured Data, Content Citability, Entity & Authority), generates personalized fix recommendations, and outputs a formatted report. Captured as a Rote Play via `/play` for community publishing.

**Tech Stack:** Python 3.14 (stdlib only: html.parser, json, re, urllib, xml.etree, concurrent.futures, statistics, textwrap), pytest (dev only), Rote CLI

**Spec:** `docs/superpowers/specs/2026-09-01-ai-visibility-audit-design.md`

## Global Constraints

- Python3 stdlib only. Zero pip dependencies in production code.
- pytest for tests (dev dependency only, not needed to run the Play).
- Single file: `score.py` at project root.
- All HTTP requests use 10-second timeout.
- Output to stdout only. No files written. Read-only Play.
- No curly/smart quotes in any string literal.

---

### Task 1: Project scaffold + HTML parser

**Files:**
- Create: `score.py`
- Create: `tests/__init__.py`
- Create: `tests/test_parsers.py`
- Create: `.gitignore`

**Interfaces:**
- Consumes: nothing
- Produces: `PageExtractor` class with attributes: `title: str`, `meta: dict[str, str]`, `json_ld: list[dict]`, `headings: list[tuple[int, str]]`, `paragraphs: list[str]`, `links: list[str]`, `images: list[dict]`, `has_lists: bool`, `has_tables: bool`. Usage: `p = PageExtractor(); p.feed(html); p.close()`

- [ ] **Step 1: Initialize git repo and create .gitignore**

```bash
cd /Users/patrickmitchell/rote-playoffs
git init
```

`.gitignore`:
```
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 2: Write failing tests for PageExtractor**

`tests/__init__.py`: empty file.

`tests/test_parsers.py`:
```python
from score import PageExtractor


FULL_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Acme Corp - Cloud Platform</title>
    <meta name="description" content="Acme Corp provides cloud infrastructure for startups.">
    <meta property="og:title" content="Acme Corp">
    <meta property="og:description" content="Cloud infrastructure for startups">
    <meta property="og:image" content="https://acme.example.com/og.png">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Acme Corp">
    <meta name="twitter:description" content="Cloud infrastructure for startups">
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "name": "Acme Corp",
                "url": "https://acme.example.com",
                "logo": "https://acme.example.com/logo.png",
                "description": "Cloud infrastructure for startups",
                "sameAs": [
                    "https://twitter.com/acme",
                    "https://linkedin.com/company/acme",
                    "https://github.com/acme"
                ]
            },
            {
                "@type": "WebSite",
                "name": "Acme Corp",
                "url": "https://acme.example.com"
            }
        ]
    }
    </script>
</head>
<body>
    <h1>Cloud Platform for Startups</h1>
    <p>Acme Corp builds reliable cloud infrastructure that scales with your team.</p>
    <h2>Features</h2>
    <p>Deploy in seconds. Scale without limits.</p>
    <ul><li>Auto-scaling</li><li>Global CDN</li></ul>
    <h3>Pricing</h3>
    <p>Simple, transparent pricing for every stage.</p>
    <table><tr><td>Free</td><td>$0/mo</td></tr></table>
    <h2>FAQ</h2>
    <h3>What regions do you support?</h3>
    <p>We support US, EU, and APAC regions.</p>
    <a href="/about">About</a>
    <a href="/contact">Contact Us</a>
    <a href="https://twitter.com/acme">Twitter</a>
    <img src="/hero.png" alt="Cloud dashboard screenshot">
    <img src="/logo.png">
</body>
</html>"""


MINIMAL_HTML = """<!DOCTYPE html>
<html>
<head><title>My Page</title></head>
<body><p>Hello world.</p></body>
</html>"""


class TestPageExtractor:
    def test_extracts_title(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert p.title == "Acme Corp - Cloud Platform"

    def test_extracts_meta_description(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert p.meta["description"] == "Acme Corp provides cloud infrastructure for startups."

    def test_extracts_og_tags(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert p.meta["og:title"] == "Acme Corp"
        assert p.meta["og:image"] == "https://acme.example.com/og.png"

    def test_extracts_twitter_tags(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert p.meta["twitter:card"] == "summary_large_image"

    def test_extracts_json_ld(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert len(p.json_ld) == 1
        assert "@graph" in p.json_ld[0]

    def test_extracts_headings(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        levels = [h[0] for h in p.headings]
        assert 1 in levels
        assert 2 in levels
        assert 3 in levels
        h1_texts = [h[1] for h in p.headings if h[0] == 1]
        assert "Cloud Platform for Startups" in h1_texts

    def test_extracts_paragraphs(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert len(p.paragraphs) >= 3

    def test_extracts_links(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert "/about" in p.links
        assert "/contact" in p.links

    def test_extracts_images(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert len(p.images) == 2
        assert p.images[0]["alt"] == "Cloud dashboard screenshot"
        assert p.images[1]["alt"] is None

    def test_detects_lists(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert p.has_lists is True

    def test_detects_tables(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert p.has_tables is True

    def test_minimal_html(self):
        p = PageExtractor()
        p.feed(MINIMAL_HTML)
        p.close()
        assert p.title == "My Page"
        assert len(p.json_ld) == 0
        assert p.has_lists is False
        assert p.has_tables is False

    def test_empty_html(self):
        p = PageExtractor()
        p.feed("")
        p.close()
        assert p.title == ""
        assert len(p.headings) == 0
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /Users/patrickmitchell/rote-playoffs && python3 -m pytest tests/test_parsers.py -v
```

Expected: FAIL with `ImportError: cannot import name 'PageExtractor' from 'score'`

- [ ] **Step 4: Implement PageExtractor**

Write `score.py` with:
```python
#!/usr/bin/env python3
"""AI Visibility Audit - scores how discoverable a site is to AI assistants."""

import json
import re
import sys
import textwrap
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from statistics import median
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import xml.etree.ElementTree as ET


# ---------------------------------------------------------------------------
# HTML Extraction
# ---------------------------------------------------------------------------

class PageExtractor(HTMLParser):
    """Extracts signals from HTML for AI visibility scoring."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self.meta = {}
        self.json_ld = []
        self.headings = []
        self.paragraphs = []
        self.links = []
        self.images = []
        self.has_lists = False
        self.has_tables = False
        self._tag_stack = []
        self._current_data = []
        self._in_jsonld = False
        self._jsonld_buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self._tag_stack.append(tag)
        self._current_data = []

        if tag == "meta":
            key = a.get("name", a.get("property", "")).lower()
            val = a.get("content", "")
            if key and val:
                self.meta[key] = val

        if tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._in_jsonld = True
            self._jsonld_buf = []

        if tag == "a":
            href = a.get("href", "")
            if href:
                self.links.append(href)

        if tag == "img":
            self.images.append({"src": a.get("src", ""), "alt": a.get("alt", None)})

        if tag in ("ul", "ol"):
            self.has_lists = True
        if tag == "table":
            self.has_tables = True

    def handle_data(self, data):
        if self._in_jsonld:
            self._jsonld_buf.append(data)
        self._current_data.append(data)

    def handle_endtag(self, tag):
        text = " ".join(self._current_data).strip()

        if tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            raw = "".join(self._jsonld_buf).strip()
            if raw:
                try:
                    self.json_ld.append(json.loads(raw))
                except json.JSONDecodeError:
                    pass

        if tag == "title" and not self.title:
            self.title = text

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6") and text:
            self.headings.append((int(tag[1]), text))

        if tag == "p" and text:
            self.paragraphs.append(text)

        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()
        self._current_data = []

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /Users/patrickmitchell/rote-playoffs && python3 -m pytest tests/test_parsers.py -v
```

Expected: all 13 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/patrickmitchell/rote-playoffs
git add score.py tests/ .gitignore
git commit -m "feat: add PageExtractor HTML parser with full signal extraction"
```

---

### Task 2: URL fetcher + robots.txt parser + AI Crawler Access scorer

**Files:**
- Modify: `score.py` (append fetcher, robots parser, scorer)
- Create: `tests/test_crawler_access.py`

**Interfaces:**
- Consumes: `PageExtractor` from Task 1
- Produces: `fetch_url(url: str, timeout: int) -> tuple[int, str]`, `fetch_all(base_url: str) -> dict[str, tuple[int, str]]`, `parse_robots(text: str) -> dict[str, list[tuple[str, str]]]`, `is_bot_blocked(agents: dict, bot_name: str) -> bool`, `score_crawler_access(fetched: dict) -> tuple[int, dict[str, bool]]`

- [ ] **Step 1: Write failing tests**

`tests/test_crawler_access.py`:
```python
from score import parse_robots, is_bot_blocked, score_crawler_access


ROBOTS_BLOCK_ALL = """User-agent: *
Disallow: /"""

ROBOTS_BLOCK_GPTBOT = """User-agent: GPTBot
Disallow: /

User-agent: *
Allow: /"""

ROBOTS_BLOCK_MULTIPLE = """User-agent: GPTBot
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: *
Allow: /"""

ROBOTS_ALLOW_ALL = """User-agent: *
Allow: /"""

ROBOTS_EMPTY = ""


class TestParseRobots:
    def test_parses_block_all(self):
        agents = parse_robots(ROBOTS_BLOCK_ALL)
        assert "*" in agents
        assert ("disallow", "/") in agents["*"]

    def test_parses_specific_bot(self):
        agents = parse_robots(ROBOTS_BLOCK_GPTBOT)
        assert "gptbot" in agents
        assert ("disallow", "/") in agents["gptbot"]

    def test_handles_empty(self):
        agents = parse_robots(ROBOTS_EMPTY)
        assert agents == {}

    def test_ignores_comments(self):
        agents = parse_robots("# comment\nUser-agent: *\nDisallow: /private # no bots")
        assert "*" in agents
        assert ("disallow", "/private") in agents["*"]


class TestIsBotBlocked:
    def test_bot_explicitly_blocked(self):
        agents = parse_robots(ROBOTS_BLOCK_GPTBOT)
        assert is_bot_blocked(agents, "GPTBot") is True

    def test_bot_not_mentioned_wildcard_allows(self):
        agents = parse_robots(ROBOTS_ALLOW_ALL)
        assert is_bot_blocked(agents, "GPTBot") is False

    def test_wildcard_blocks_unnamed_bot(self):
        agents = parse_robots(ROBOTS_BLOCK_ALL)
        assert is_bot_blocked(agents, "ClaudeBot") is True

    def test_bot_explicitly_allowed_overrides_wildcard(self):
        robots = "User-agent: GPTBot\nAllow: /\n\nUser-agent: *\nDisallow: /"
        agents = parse_robots(robots)
        assert is_bot_blocked(agents, "GPTBot") is False

    def test_empty_robots_allows_all(self):
        agents = parse_robots(ROBOTS_EMPTY)
        assert is_bot_blocked(agents, "GPTBot") is False


class TestScoreCrawlerAccess:
    def _make_fetched(self, robots="", robots_status=200,
                      llms_status=404, llms_full_status=404,
                      sitemap="", sitemap_status=404):
        return {
            "html": (200, "<html></html>"),
            "robots": (robots_status, robots),
            "llms": (llms_status, "# llms.txt" if llms_status == 200 else ""),
            "llms_full": (llms_full_status, "# full" if llms_full_status == 200 else ""),
            "sitemap": (sitemap_status, sitemap),
        }

    def test_perfect_score(self):
        fetched = self._make_fetched(
            robots=ROBOTS_ALLOW_ALL,
            llms_status=200,
            llms_full_status=200,
            sitemap='<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/</loc></url></urlset>',
            sitemap_status=200,
        )
        score, signals = score_crawler_access(fetched)
        assert score == 25

    def test_zero_score(self):
        fetched = self._make_fetched(robots_status=404)
        score, signals = score_crawler_access(fetched)
        assert score == 0
        assert signals["robots_exists"] is False

    def test_blocked_bots_lose_points(self):
        fetched = self._make_fetched(robots=ROBOTS_BLOCK_MULTIPLE)
        score, signals = score_crawler_access(fetched)
        assert signals["GPTBot_allowed"] is False
        assert signals["ClaudeBot_allowed"] is False
        assert signals["PerplexityBot_allowed"] is True
        assert score == 3 + 3 + 3  # robots(3) + perplexity(3) + google(3)

    def test_llms_txt_awards_5_points(self):
        fetched = self._make_fetched(robots=ROBOTS_ALLOW_ALL, llms_status=200)
        score, _ = score_crawler_access(fetched)
        # 3(robots) + 12(bots) + 5(llms) = 20
        assert score == 20
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/patrickmitchell/rote-playoffs && python3 -m pytest tests/test_crawler_access.py -v
```

Expected: ImportError

- [ ] **Step 3: Implement fetcher, robots parser, and crawler scorer**

Append to `score.py`:
```python
# ---------------------------------------------------------------------------
# URL Fetching
# ---------------------------------------------------------------------------

def fetch_url(url, timeout=10):
    """Fetch a URL. Returns (status_code, body_text). Returns (0, '') on error."""
    try:
        req = Request(url, headers={"User-Agent": "AIVisibilityAudit/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            return (resp.status, resp.read().decode("utf-8", errors="replace"))
    except HTTPError as e:
        return (e.code, "")
    except (URLError, OSError, ValueError):
        return (0, "")


def fetch_all(base_url):
    """Fetch page HTML + robots.txt + llms.txt + llms-full.txt + sitemap.xml."""
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    targets = {
        "html": base_url,
        "robots": f"{origin}/robots.txt",
        "llms": f"{origin}/.well-known/llms.txt",
        "llms_full": f"{origin}/.well-known/llms-full.txt",
        "sitemap": f"{origin}/sitemap.xml",
    }
    results = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch_url, url): key for key, url in targets.items()}
        futures[pool.submit(fetch_url, f"{origin}/llms.txt")] = "llms_alt"
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    if results["llms"][0] != 200 and results.get("llms_alt", (0, ""))[0] == 200:
        results["llms"] = results["llms_alt"]
    return results


# ---------------------------------------------------------------------------
# Robots.txt Parsing
# ---------------------------------------------------------------------------

AI_BOTS = ["GPTBot", "ClaudeBot", "PerplexityBot", "GoogleOther", "Google-Extended"]


def parse_robots(text):
    """Parse robots.txt into {user_agent_lower: [(directive, value)]}."""
    agents = {}
    current = None
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.lower().startswith("user-agent:"):
            current = line.split(":", 1)[1].strip().lower()
            agents.setdefault(current, [])
        elif current and ":" in line:
            directive, value = line.split(":", 1)
            agents[current].append((directive.strip().lower(), value.strip()))
    return agents


def is_bot_blocked(agents, bot_name):
    """Check if a bot is blocked. Bot-specific rules override wildcard."""
    bot_lower = bot_name.lower()
    if bot_lower in agents:
        for directive, value in agents[bot_lower]:
            if directive == "disallow" and value == "/":
                return True
            if directive == "allow" and value == "/":
                return False
        return False
    if "*" in agents:
        for directive, value in agents["*"]:
            if directive == "disallow" and value == "/":
                return True
    return False


# ---------------------------------------------------------------------------
# Dimension 1: AI Crawler Access (25 points)
# ---------------------------------------------------------------------------

def score_crawler_access(fetched):
    """Score AI Crawler Access. Returns (score, signals_dict)."""
    signals = {}
    score = 0

    robots_status, robots_body = fetched["robots"]
    has_robots = robots_status == 200 and robots_body.strip()
    signals["robots_exists"] = has_robots
    if has_robots:
        score += 3
        agents = parse_robots(robots_body)
    else:
        agents = {}

    for bot in ["GPTBot", "ClaudeBot", "PerplexityBot"]:
        blocked = is_bot_blocked(agents, bot)
        signals[f"{bot}_allowed"] = not blocked
        if not blocked:
            score += 3

    google_blocked = is_bot_blocked(agents, "GoogleOther") and is_bot_blocked(agents, "Google-Extended")
    signals["GoogleOther_allowed"] = not google_blocked
    if not google_blocked:
        score += 3

    signals["llms_txt"] = fetched["llms"][0] == 200
    if signals["llms_txt"]:
        score += 5

    signals["llms_full_txt"] = fetched["llms_full"][0] == 200
    if signals["llms_full_txt"]:
        score += 2

    sitemap_ok = False
    if fetched["sitemap"][0] == 200:
        try:
            ET.fromstring(fetched["sitemap"][1])
            sitemap_ok = True
        except ET.ParseError:
            pass
    signals["sitemap"] = sitemap_ok
    if sitemap_ok:
        score += 3

    return score, signals
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/patrickmitchell/rote-playoffs && python3 -m pytest tests/test_crawler_access.py -v
```

Expected: all 13 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/patrickmitchell/rote-playoffs
git add score.py tests/test_crawler_access.py
git commit -m "feat: add URL fetcher, robots.txt parser, AI Crawler Access scorer"
```

---

### Task 3: Structured Data scorer

**Files:**
- Modify: `score.py` (append structured data scorer)
- Create: `tests/test_structured_data.py`

**Interfaces:**
- Consumes: `PageExtractor` from Task 1
- Produces: `score_structured_data(extractor: PageExtractor) -> tuple[int, dict[str, bool]]`

- [ ] **Step 1: Write failing tests**

`tests/test_structured_data.py`:
```python
from score import PageExtractor, score_structured_data
from tests.test_parsers import FULL_HTML, MINIMAL_HTML


HTML_NO_GRAPH = """<html><head>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Test"}</script>
<meta property="og:title" content="Test">
<meta property="og:description" content="Desc">
<meta property="og:image" content="https://example.com/img.png">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="Test">
<meta name="twitter:description" content="Desc">
</head><body></body></html>"""


HTML_FAQ_SCHEMA = """<html><head>
<script type="application/ld+json">{
  "@context": "https://schema.org",
  "@graph": [
    {"@type": "Organization", "name": "X", "url": "https://x.com", "logo": "https://x.com/logo.png", "description": "Desc", "sameAs": ["https://twitter.com/x"]},
    {"@type": "FAQPage", "mainEntity": [{"@type": "Question"}]},
    {"@type": "BreadcrumbList", "itemListElement": []}
  ]
}</script>
<meta property="og:title" content="X">
<meta property="og:description" content="D">
<meta property="og:image" content="https://x.com/og.png">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="X">
<meta name="twitter:description" content="D">
</head><body></body></html>"""


def _extract(html):
    p = PageExtractor()
    p.feed(html)
    p.close()
    return p


class TestStructuredData:
    def test_full_html_scores_high(self):
        score, signals = score_structured_data(_extract(FULL_HTML))
        assert signals["has_jsonld"] is True
        assert signals["has_graph"] is True
        assert signals["has_org_or_local"] is True
        assert score >= 25

    def test_minimal_html_scores_zero(self):
        score, signals = score_structured_data(_extract(MINIMAL_HTML))
        assert score == 0
        assert signals["has_jsonld"] is False

    def test_no_graph_loses_5_points(self):
        score_with, _ = score_structured_data(_extract(FULL_HTML))
        score_without, signals = score_structured_data(_extract(HTML_NO_GRAPH))
        assert signals["has_graph"] is False
        assert score_with > score_without

    def test_faq_and_breadcrumb_schemas(self):
        score, signals = score_structured_data(_extract(HTML_FAQ_SCHEMA))
        assert signals["has_faq_or_howto"] is True
        assert signals["has_breadcrumb"] is True

    def test_og_tags_detected(self):
        _, signals = score_structured_data(_extract(FULL_HTML))
        assert signals["has_og_tags"] is True

    def test_twitter_tags_detected(self):
        _, signals = score_structured_data(_extract(FULL_HTML))
        assert signals["has_twitter_tags"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/patrickmitchell/rote-playoffs && python3 -m pytest tests/test_structured_data.py -v
```

- [ ] **Step 3: Implement structured data scorer**

Append to `score.py`:
```python
# ---------------------------------------------------------------------------
# Dimension 2: Structured Data (30 points)
# ---------------------------------------------------------------------------

def _flatten_types(json_ld_list):
    """Extract all @type values from JSON-LD blocks, including inside @graph."""
    types = []
    items = []
    for block in json_ld_list:
        if "@graph" in block:
            items.extend(block["@graph"])
        else:
            items.append(block)
    for item in items:
        t = item.get("@type", "")
        if isinstance(t, list):
            types.extend(t)
        elif t:
            types.append(t)
    return types, items


def score_structured_data(ext):
    """Score Structured Data dimension. Returns (score, signals_dict)."""
    signals = {}
    score = 0
    types, items = _flatten_types(ext.json_ld)

    signals["has_jsonld"] = len(ext.json_ld) > 0
    if signals["has_jsonld"]:
        score += 5

    signals["has_graph"] = any("@graph" in b for b in ext.json_ld)
    if signals["has_graph"]:
        score += 5

    org_types = {"Organization", "LocalBusiness"}
    signals["has_org_or_local"] = bool(org_types & set(types))
    if signals["has_org_or_local"]:
        score += 5

    required_fields = {"name", "url", "logo", "description", "sameAs"}
    org_items = [i for i in items if i.get("@type") in org_types]
    if org_items:
        present = {k for k in required_fields if org_items[0].get(k)}
        completeness = len(present) / len(required_fields)
        signals["schema_completeness"] = completeness
        score += round(5 * completeness)
    else:
        signals["schema_completeness"] = 0.0

    faq_types = {"FAQPage", "HowTo"}
    signals["has_faq_or_howto"] = bool(faq_types & set(types))
    if signals["has_faq_or_howto"]:
        score += 3

    signals["has_breadcrumb"] = "BreadcrumbList" in types
    if signals["has_breadcrumb"]:
        score += 2

    og_required = {"og:title", "og:description", "og:image", "og:type"}
    og_present = {k for k in og_required if k in ext.meta}
    signals["has_og_tags"] = len(og_present) == len(og_required)
    if signals["has_og_tags"]:
        score += 3

    tw_required = {"twitter:card", "twitter:title", "twitter:description"}
    tw_present = {k for k in tw_required if k in ext.meta}
    signals["has_twitter_tags"] = len(tw_present) == len(tw_required)
    if signals["has_twitter_tags"]:
        score += 2

    return score, signals
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/patrickmitchell/rote-playoffs && python3 -m pytest tests/test_structured_data.py -v
```

- [ ] **Step 5: Commit**

```bash
cd /Users/patrickmitchell/rote-playoffs
git add score.py tests/test_structured_data.py
git commit -m "feat: add Structured Data scorer (JSON-LD, OG, Twitter)"
```

---

### Task 4: Content Citability scorer

**Files:**
- Modify: `score.py` (append citability scorer)
- Create: `tests/test_citability.py`

**Interfaces:**
- Consumes: `PageExtractor` from Task 1
- Produces: `score_content_citability(extractor: PageExtractor) -> tuple[int, dict]`

- [ ] **Step 1: Write failing tests**

`tests/test_citability.py`:
```python
from score import PageExtractor, score_content_citability
from tests.test_parsers import FULL_HTML, MINIMAL_HTML


HTML_GOOD_CONTENT = """<html><head>
<meta name="description" content="A platform that helps developers ship faster with reliable infrastructure.">
</head><body>
<h1>Ship Faster</h1>
<p>Our platform helps developers deploy applications in seconds. We handle scaling, monitoring, and security so you can focus on building.</p>
<h2>Features</h2>
<p>Auto-scaling, global CDN, and edge computing.</p>
<h3>Auto-Scaling</h3>
<p>Scale from zero to millions without configuration changes.</p>
<h3>What makes us different?</h3>
<p>We optimize for developer experience first.</p>
<ul><li>One-click deploys</li><li>Preview environments</li></ul>
<ol><li>Sign up</li><li>Connect repo</li><li>Deploy</li></ol>
<table><tr><th>Plan</th><th>Price</th></tr><tr><td>Free</td><td>$0</td></tr></table>
<img src="/a.png" alt="Dashboard">
<img src="/b.png" alt="Deploy flow">
<img src="/c.png" alt="Monitoring">
</body></html>"""


HTML_LONG_PARAGRAPHS = """<html><head>
<meta name="description" content="Test">
</head><body>
<h1>Title</h1>
<p>""" + " ".join(["word"] * 200) + """</p>
<p>""" + " ".join(["word"] * 200) + """</p>
</body></html>"""


def _extract(html):
    p = PageExtractor()
    p.feed(html)
    p.close()
    return p


class TestContentCitability:
    def test_good_content_scores_high(self):
        score, signals = score_content_citability(_extract(HTML_GOOD_CONTENT))
        assert score >= 20
        assert signals["has_single_h1"] is True
        assert signals["heading_depth"] >= 3

    def test_minimal_html_scores_low(self):
        score, signals = score_content_citability(_extract(MINIMAL_HTML))
        assert score <= 3

    def test_faq_pattern_detected(self):
        _, signals = score_content_citability(_extract(HTML_GOOD_CONTENT))
        assert signals["has_faq_patterns"] is True

    def test_long_paragraphs_penalized(self):
        _, signals = score_content_citability(_extract(HTML_LONG_PARAGRAPHS))
        assert signals["short_paragraphs"] is False

    def test_image_alt_coverage(self):
        _, signals = score_content_citability(_extract(HTML_GOOD_CONTENT))
        assert signals["alt_coverage"] >= 0.8

    def test_meta_desc_length(self):
        _, signals = score_content_citability(_extract(HTML_GOOD_CONTENT))
        assert signals["meta_desc_ok"] is True

    def test_lists_detected(self):
        _, signals = score_content_citability(_extract(HTML_GOOD_CONTENT))
        assert signals["has_lists"] is True

    def test_tables_detected(self):
        _, signals = score_content_citability(_extract(HTML_GOOD_CONTENT))
        assert signals["has_tables"] is True

    def test_full_html_word_count(self):
        _, signals = score_content_citability(_extract(FULL_HTML))
        assert signals["word_count"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/patrickmitchell/rote-playoffs && python3 -m pytest tests/test_citability.py -v
```

- [ ] **Step 3: Implement citability scorer**

Append to `score.py`:
```python
# ---------------------------------------------------------------------------
# Dimension 3: Content Citability (25 points)
# ---------------------------------------------------------------------------

def score_content_citability(ext):
    """Score Content Citability dimension. Returns (score, signals_dict)."""
    signals = {}
    score = 0

    h1_count = sum(1 for h in ext.headings if h[0] == 1)
    signals["has_single_h1"] = h1_count == 1
    if h1_count == 1:
        score += 3

    levels_used = set(h[0] for h in ext.headings)
    signals["heading_depth"] = len(levels_used)
    if len(levels_used) >= 3:
        score += 3

    all_text = " ".join(ext.paragraphs)
    word_count = len(all_text.split())
    signals["word_count"] = word_count
    if word_count >= 300:
        score += 3

    if ext.paragraphs:
        lengths = [len(p.split()) for p in ext.paragraphs]
        med = median(lengths) if lengths else 0
        signals["median_paragraph_words"] = med
        signals["short_paragraphs"] = med < 100
        if med < 100:
            score += 3
    else:
        signals["median_paragraph_words"] = 0
        signals["short_paragraphs"] = False

    question_headings = [h for h in ext.headings if "?" in h[1]]
    signals["has_faq_patterns"] = len(question_headings) > 0
    if question_headings:
        score += 3

    signals["has_lists"] = ext.has_lists
    if ext.has_lists:
        score += 2

    signals["has_tables"] = ext.has_tables
    if ext.has_tables:
        score += 2

    desc = ext.meta.get("description", "")
    desc_len = len(desc)
    signals["meta_desc_ok"] = 120 <= desc_len <= 160
    signals["meta_desc_len"] = desc_len
    if signals["meta_desc_ok"]:
        score += 3

    if ext.images:
        with_alt = sum(1 for img in ext.images if img["alt"])
        coverage = with_alt / len(ext.images)
    else:
        coverage = 1.0
    signals["alt_coverage"] = coverage
    if coverage >= 0.8:
        score += 3

    return score, signals
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/patrickmitchell/rote-playoffs && python3 -m pytest tests/test_citability.py -v
```

- [ ] **Step 5: Commit**

```bash
cd /Users/patrickmitchell/rote-playoffs
git add score.py tests/test_citability.py
git commit -m "feat: add Content Citability scorer"
```

---

### Task 5: Entity & Authority scorer

**Files:**
- Modify: `score.py` (append authority scorer)
- Create: `tests/test_authority.py`

**Interfaces:**
- Consumes: `PageExtractor` from Task 1, `_flatten_types` from Task 3
- Produces: `score_entity_authority(extractor: PageExtractor) -> tuple[int, dict]`

- [ ] **Step 1: Write failing tests**

`tests/test_authority.py`:
```python
from score import PageExtractor, score_entity_authority
from tests.test_parsers import FULL_HTML, MINIMAL_HTML


HTML_NO_SAMEAS = """<html><head>
<title>Acme Corp</title>
<meta property="og:title" content="Acme Corp">
<script type="application/ld+json">{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "Acme Corp"
}</script>
</head><body>
<a href="/about">About</a>
<a href="/contact">Contact</a>
</body></html>"""


HTML_BRAND_MISMATCH = """<html><head>
<title>Acme Corp - Home</title>
<meta property="og:title" content="Acme Industries">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Acme LLC"}</script>
</head><body></body></html>"""


HTML_WITH_AUTHOR = """<html><head>
<title>Blog Post</title>
<script type="application/ld+json">{
  "@context": "https://schema.org",
  "@graph": [
    {"@type": "Organization", "name": "Blog", "sameAs": ["https://twitter.com/blog", "https://github.com/blog", "https://linkedin.com/company/blog"]},
    {"@type": "Person", "name": "Jane Doe"}
  ]
}</script>
</head><body>
<a href="/about">About</a>
<a href="/contact">Contact</a>
</body></html>"""


def _extract(html):
    p = PageExtractor()
    p.feed(html)
    p.close()
    return p


class TestEntityAuthority:
    def test_full_html_scores_high(self):
        score, signals = score_entity_authority(_extract(FULL_HTML))
        assert score >= 15
        assert signals["has_sameas"] is True
        assert signals["sameas_count"] >= 3

    def test_minimal_scores_zero(self):
        score, signals = score_entity_authority(_extract(MINIMAL_HTML))
        assert score == 0

    def test_no_sameas_loses_points(self):
        score, signals = score_entity_authority(_extract(HTML_NO_SAMEAS))
        assert signals["has_sameas"] is False
        assert signals["sameas_count"] == 0

    def test_author_detected(self):
        _, signals = score_entity_authority(_extract(HTML_WITH_AUTHOR))
        assert signals["has_author"] is True

    def test_contact_about_links(self):
        _, signals = score_entity_authority(_extract(FULL_HTML))
        assert signals["has_contact_link"] is True
        assert signals["has_about_link"] is True

    def test_brand_consistency(self):
        _, signals = score_entity_authority(_extract(FULL_HTML))
        assert signals["brand_consistent"] is True

    def test_brand_mismatch(self):
        _, signals = score_entity_authority(_extract(HTML_BRAND_MISMATCH))
        assert signals["brand_consistent"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/patrickmitchell/rote-playoffs && python3 -m pytest tests/test_authority.py -v
```

- [ ] **Step 3: Implement authority scorer**

Append to `score.py`:
```python
# ---------------------------------------------------------------------------
# Dimension 4: Entity & Authority (20 points)
# ---------------------------------------------------------------------------

def _extract_brand_names(ext):
    """Pull brand name candidates from title, og:title, and schema name."""
    names = []
    if ext.title:
        name = ext.title.split("-")[0].split("|")[0].strip()
        if name:
            names.append(name.lower())
    og = ext.meta.get("og:title", "")
    if og:
        names.append(og.lower().split("-")[0].split("|")[0].strip())
    _, items = _flatten_types(ext.json_ld)
    for item in items:
        if item.get("@type") in ("Organization", "LocalBusiness"):
            n = item.get("name", "")
            if n:
                names.append(n.lower())
    return names


def score_entity_authority(ext):
    """Score Entity & Authority dimension. Returns (score, signals_dict)."""
    signals = {}
    score = 0
    _, items = _flatten_types(ext.json_ld)

    org_items = [i for i in items if i.get("@type") in ("Organization", "LocalBusiness")]
    sameas = []
    if org_items:
        sameas = org_items[0].get("sameAs", [])
        if isinstance(sameas, str):
            sameas = [sameas]

    signals["has_sameas"] = len(sameas) > 0
    if signals["has_sameas"]:
        score += 5

    signals["sameas_count"] = len(sameas)
    if len(sameas) >= 3:
        score += 2

    person_types = {"Person"}
    signals["has_author"] = bool(person_types & {i.get("@type") for i in items})
    if signals["has_author"]:
        score += 3

    links_lower = [l.lower() for l in ext.links]
    signals["has_contact_link"] = any("contact" in l for l in links_lower)
    if signals["has_contact_link"]:
        score += 3

    signals["has_about_link"] = any("about" in l for l in links_lower)
    if signals["has_about_link"]:
        score += 3

    brands = _extract_brand_names(ext)
    if len(brands) >= 2:
        first = brands[0]
        signals["brand_consistent"] = all(b == first for b in brands)
    elif len(brands) == 1:
        signals["brand_consistent"] = True
    else:
        signals["brand_consistent"] = False
    if signals["brand_consistent"]:
        score += 4

    return score, signals
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/patrickmitchell/rote-playoffs && python3 -m pytest tests/test_authority.py -v
```

- [ ] **Step 5: Commit**

```bash
cd /Users/patrickmitchell/rote-playoffs
git add score.py tests/test_authority.py
git commit -m "feat: add Entity & Authority scorer"
```

---

### Task 6: Fix recommendation engine + report formatter

**Files:**
- Modify: `score.py` (append recommender and formatter)
- Create: `tests/test_recommender.py`
- Create: `tests/test_formatter.py`

**Interfaces:**
- Consumes: all signals dicts from Tasks 2-5, `PageExtractor` from Task 1, `fetched` dict from Task 2
- Produces: `generate_recommendations(ext, fetched, all_signals: dict) -> list[dict]` where each dict has keys `title: str`, `points: int`, `why: str`, `code: str`. Also `format_report(url, scores: dict, all_signals: dict, recommendations: list) -> str`.

- [ ] **Step 1: Write failing tests for recommender**

`tests/test_recommender.py`:
```python
from score import PageExtractor, generate_recommendations
from tests.test_parsers import MINIMAL_HTML


def _extract(html):
    p = PageExtractor()
    p.feed(html)
    p.close()
    return p


def _minimal_fetched():
    return {
        "html": (200, MINIMAL_HTML),
        "robots": (200, "User-agent: *\nAllow: /"),
        "llms": (404, ""),
        "llms_full": (404, ""),
        "sitemap": (404, ""),
    }


class TestRecommender:
    def test_returns_list(self):
        ext = _extract(MINIMAL_HTML)
        signals = {
            "llms_txt": False, "llms_full_txt": False,
            "has_org_or_local": False, "has_graph": False,
            "has_sameas": False, "sameas_count": 0,
            "GPTBot_allowed": True, "ClaudeBot_allowed": True,
            "PerplexityBot_allowed": True, "GoogleOther_allowed": True,
            "has_faq_or_howto": False, "has_breadcrumb": False,
            "has_og_tags": False, "has_twitter_tags": False,
            "meta_desc_ok": False, "meta_desc_len": 0,
            "brand_consistent": False, "has_contact_link": False,
            "has_about_link": False, "has_author": False,
            "schema_completeness": 0.0, "sitemap": False,
            "robots_exists": True,
        }
        recs = generate_recommendations(ext, _minimal_fetched(), signals)
        assert isinstance(recs, list)
        assert len(recs) <= 5

    def test_sorted_by_points_desc(self):
        ext = _extract(MINIMAL_HTML)
        signals = {
            "llms_txt": False, "llms_full_txt": False,
            "has_org_or_local": False, "has_graph": False,
            "has_sameas": False, "sameas_count": 0,
            "GPTBot_allowed": True, "ClaudeBot_allowed": True,
            "PerplexityBot_allowed": True, "GoogleOther_allowed": True,
            "has_faq_or_howto": False, "has_breadcrumb": False,
            "has_og_tags": False, "has_twitter_tags": False,
            "meta_desc_ok": False, "meta_desc_len": 0,
            "brand_consistent": False, "has_contact_link": False,
            "has_about_link": False, "has_author": False,
            "schema_completeness": 0.0, "sitemap": False,
            "robots_exists": True,
        }
        recs = generate_recommendations(ext, _minimal_fetched(), signals)
        points = [r["points"] for r in recs]
        assert points == sorted(points, reverse=True)

    def test_each_rec_has_required_fields(self):
        ext = _extract(MINIMAL_HTML)
        signals = {
            "llms_txt": False, "llms_full_txt": False,
            "has_org_or_local": False, "has_graph": False,
            "has_sameas": False, "sameas_count": 0,
            "GPTBot_allowed": True, "ClaudeBot_allowed": True,
            "PerplexityBot_allowed": True, "GoogleOther_allowed": True,
            "has_faq_or_howto": False, "has_breadcrumb": False,
            "has_og_tags": False, "has_twitter_tags": False,
            "meta_desc_ok": False, "meta_desc_len": 0,
            "brand_consistent": False, "has_contact_link": False,
            "has_about_link": False, "has_author": False,
            "schema_completeness": 0.0, "sitemap": False,
            "robots_exists": True,
        }
        recs = generate_recommendations(ext, _minimal_fetched(), signals)
        for rec in recs:
            assert "title" in rec
            assert "points" in rec
            assert "why" in rec
            assert "code" in rec

    def test_llms_txt_recommendation_personalized(self):
        ext = _extract(MINIMAL_HTML)
        signals = {
            "llms_txt": False, "llms_full_txt": False,
            "has_org_or_local": False, "has_graph": False,
            "has_sameas": False, "sameas_count": 0,
            "GPTBot_allowed": True, "ClaudeBot_allowed": True,
            "PerplexityBot_allowed": True, "GoogleOther_allowed": True,
            "has_faq_or_howto": False, "has_breadcrumb": False,
            "has_og_tags": False, "has_twitter_tags": False,
            "meta_desc_ok": False, "meta_desc_len": 0,
            "brand_consistent": False, "has_contact_link": False,
            "has_about_link": False, "has_author": False,
            "schema_completeness": 0.0, "sitemap": False,
            "robots_exists": True,
        }
        recs = generate_recommendations(ext, _minimal_fetched(), signals)
        llms_recs = [r for r in recs if "llms.txt" in r["title"].lower()]
        if llms_recs:
            assert "My Page" in llms_recs[0]["code"]
```

- [ ] **Step 2: Write failing tests for formatter**

`tests/test_formatter.py`:
```python
from score import format_report


class TestFormatter:
    def test_contains_domain(self):
        output = format_report(
            "https://example.com",
            {"crawler": 15, "structured": 20, "citability": 18, "authority": 12},
            {},
            []
        )
        assert "example.com" in output

    def test_contains_total_score(self):
        output = format_report(
            "https://example.com",
            {"crawler": 15, "structured": 20, "citability": 18, "authority": 12},
            {},
            []
        )
        assert "65 / 100" in output

    def test_contains_bar_chart(self):
        output = format_report(
            "https://example.com",
            {"crawler": 25, "structured": 0, "citability": 25, "authority": 0},
            {},
            []
        )
        assert "AI Crawler Access" in output
        assert "Structured Data" in output

    def test_contains_recommendations(self):
        recs = [{"title": "Add llms.txt", "points": 8, "why": "AI looks here first", "code": "# llms.txt\n> Example"}]
        output = format_report(
            "https://example.com",
            {"crawler": 0, "structured": 0, "citability": 0, "authority": 0},
            {},
            recs
        )
        assert "Add llms.txt" in output
        assert "+8pts" in output

    def test_contains_gravitasindex_cta(self):
        output = format_report(
            "https://example.com",
            {"crawler": 0, "structured": 0, "citability": 0, "authority": 0},
            {},
            []
        )
        assert "gravitasindex.com" in output
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /Users/patrickmitchell/rote-playoffs && python3 -m pytest tests/test_recommender.py tests/test_formatter.py -v
```

- [ ] **Step 4: Implement recommender**

Append to `score.py`:
```python
# ---------------------------------------------------------------------------
# Fix Recommendation Engine
# ---------------------------------------------------------------------------

def generate_recommendations(ext, fetched, signals):
    """Generate up to 5 personalized fix recommendations sorted by impact."""
    recs = []
    url = ext.meta.get("og:url", "")
    site_name = ext.title.split("-")[0].split("|")[0].strip() or "Your Site"
    description = ext.meta.get("description", "")

    if not signals.get("llms_txt"):
        desc_line = f"> {description}" if description else "> [Add a one-line description of your site]"
        recs.append({
            "title": "Add llms.txt",
            "points": 5,
            "why": "AI assistants look for /.well-known/llms.txt to understand your site. This is the single highest-impact file for AI discoverability.",
            "code": f"# {site_name}\n{desc_line}\n\n## Docs\n- [Homepage]({url or 'https://yoursite.com'})",
        })

    blocked_bots = []
    for bot in ["GPTBot", "ClaudeBot", "PerplexityBot"]:
        if not signals.get(f"{bot}_allowed", True):
            blocked_bots.append(bot)
    if not signals.get("GoogleOther_allowed", True):
        blocked_bots.append("GoogleOther")
    if blocked_bots:
        lines = "\n".join(f"User-agent: {bot}\nAllow: /" for bot in blocked_bots)
        recs.append({
            "title": f"Unblock {', '.join(blocked_bots)} in robots.txt",
            "points": 3 * len(blocked_bots),
            "why": f"Your robots.txt blocks {len(blocked_bots)} AI crawler(s). Unblocking lets AI assistants index your content and cite it in answers.",
            "code": f"# Add to robots.txt:\n{lines}",
        })

    if not signals.get("has_org_or_local"):
        social_links = [l for l in ext.links if any(s in l for s in ["twitter.com", "linkedin.com", "github.com", "facebook.com", "instagram.com", "youtube.com"])]
        sameas_json = ""
        if social_links:
            sameas_json = ',\n    "sameAs": ' + json.dumps(social_links[:5])
        logo = ext.meta.get("og:image", "https://yoursite.com/logo.png")
        recs.append({
            "title": "Add Organization schema",
            "points": 5,
            "why": "Organization schema tells AI assistants who you are, what you do, and where to find your profiles. Without it, AI has to guess.",
            "code": '<script type="application/ld+json">\n' + json.dumps({
                "@context": "https://schema.org",
                "@type": "Organization",
                "name": site_name,
                "url": url or "https://yoursite.com",
                "logo": logo,
                "description": description or "[Your description]",
                "sameAs": social_links[:5] if social_links else ["https://twitter.com/yourhandle"]
            }, indent=2) + "\n</script>",
        })
    elif not signals.get("has_graph"):
        recs.append({
            "title": "Wrap JSON-LD in @graph",
            "points": 5,
            "why": "Using @graph connects your schema entities (Organization, WebSite, pages) into a knowledge graph that AI can traverse, rather than isolated fragments.",
            "code": '{\n  "@context": "https://schema.org",\n  "@graph": [\n    { "@type": "Organization", ... },\n    { "@type": "WebSite", ... }\n  ]\n}',
        })

    if not signals.get("has_sameas") and signals.get("has_org_or_local"):
        social_links = [l for l in ext.links if any(s in l for s in ["twitter.com", "linkedin.com", "github.com", "facebook.com"])]
        if social_links:
            recs.append({
                "title": "Add sameAs social links to Organization schema",
                "points": 5,
                "why": "Your Organization schema has no sameAs links. Adding your social profiles helps AI cross-reference your brand identity.",
                "code": '"sameAs": ' + json.dumps(social_links[:5], indent=2),
            })

    if not signals.get("has_og_tags"):
        recs.append({
            "title": "Add Open Graph meta tags",
            "points": 3,
            "why": "OG tags (og:title, og:description, og:image, og:type) are read by AI assistants and social platforms to understand and preview your pages.",
            "code": f'<meta property="og:title" content="{site_name}">\n<meta property="og:description" content="{description or "[Description]"}">\n<meta property="og:image" content="{ext.meta.get("og:image", "https://yoursite.com/og.png")}">\n<meta property="og:type" content="website">',
        })

    if not signals.get("has_faq_or_howto"):
        question_headings = [h for h in ext.headings if "?" in h[1]]
        if question_headings:
            qa_items = []
            for _, q in question_headings[:3]:
                qa_items.append({"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": "[Answer]"}})
            recs.append({
                "title": "Add FAQ schema for your question headings",
                "points": 3,
                "why": f"You have {len(question_headings)} question-style heading(s) but no FAQ schema. Adding it makes AI assistants more likely to cite your answers directly.",
                "code": '<script type="application/ld+json">\n' + json.dumps({
                    "@context": "https://schema.org",
                    "@type": "FAQPage",
                    "mainEntity": qa_items
                }, indent=2) + "\n</script>",
            })

    if not signals.get("meta_desc_ok"):
        first_para = ext.paragraphs[0] if ext.paragraphs else ""
        suggested = first_para[:155].rsplit(" ", 1)[0] + "." if len(first_para) > 155 else first_para
        if suggested and len(suggested) < 120:
            suggested = suggested
        elif not suggested:
            suggested = f"{site_name} - [Describe what you do in 120-160 characters]"
        recs.append({
            "title": "Fix meta description length (aim for 120-160 chars)",
            "points": 3,
            "why": f"Your meta description is {signals.get('meta_desc_len', 0)} characters. AI assistants use it as a summary. 120-160 chars is the sweet spot.",
            "code": f'<meta name="description" content="{suggested}">',
        })

    if not signals.get("sitemap"):
        recs.append({
            "title": "Add sitemap.xml",
            "points": 3,
            "why": "A valid sitemap.xml helps AI crawlers discover all your pages efficiently.",
            "code": f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url><loc>{url or "https://yoursite.com/"}</loc></url>\n</urlset>',
        })

    recs.sort(key=lambda r: r["points"], reverse=True)
    return recs[:5]
```

- [ ] **Step 5: Implement formatter**

Append to `score.py`:
```python
# ---------------------------------------------------------------------------
# Report Formatter
# ---------------------------------------------------------------------------

def _bar(score, max_score, width=10):
    """Render an ASCII progress bar."""
    filled = round((score / max_score) * width) if max_score else 0
    return "█" * filled + "░" * (width - filled)


def format_report(url, scores, all_signals, recommendations):
    """Format the full audit report as a string."""
    parsed = urlparse(url)
    domain = parsed.netloc or url
    total = sum(scores.values())

    lines = []
    lines.append(f"AI VISIBILITY AUDIT — {domain}")
    lines.append(f"Score: {total} / 100")
    lines.append("")

    dims = [
        ("AI Crawler Access", scores["crawler"], 25),
        ("Structured Data", scores["structured"], 30),
        ("Content Citability", scores["citability"], 25),
        ("Entity & Authority", scores["authority"], 20),
    ]
    for name, sc, mx in dims:
        bar = _bar(sc, mx)
        lines.append(f"  {name:<22} {bar}  {sc}/{mx}")

    if recommendations:
        lines.append("")
        lines.append("TOP FIXES (by impact):")
        lines.append("")
        for i, rec in enumerate(recommendations, 1):
            lines.append(f"{i}. {rec['title']} (+{rec['points']}pts)")
            lines.append(f"   {rec['why']}")
            lines.append("   ───")
            for code_line in rec["code"].splitlines():
                lines.append(f"   {code_line}")
            lines.append("   ───")
            lines.append("")

    lines.append("Want automated weekly monitoring? gravitasindex.com")
    return "\n".join(lines)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /Users/patrickmitchell/rote-playoffs && python3 -m pytest tests/test_recommender.py tests/test_formatter.py -v
```

- [ ] **Step 7: Commit**

```bash
cd /Users/patrickmitchell/rote-playoffs
git add score.py tests/test_recommender.py tests/test_formatter.py
git commit -m "feat: add fix recommendation engine and report formatter"
```

---

### Task 7: CLI entry point + integration test + Rote Play capture

**Files:**
- Modify: `score.py` (append `main()` and `if __name__` block)
- Create: `tests/test_integration.py`

**Interfaces:**
- Consumes: all functions from Tasks 1-6
- Produces: `main(args: list[str]) -> None` (prints report to stdout, exits 0 on success, 1 on error). CLI usage: `python3 score.py <url>`

- [ ] **Step 1: Write the integration test**

`tests/test_integration.py`:
```python
import subprocess
import sys


class TestCLIIntegration:
    def test_exits_1_on_missing_url(self):
        result = subprocess.run(
            [sys.executable, "score.py"],
            capture_output=True, text=True,
            cwd="/Users/patrickmitchell/rote-playoffs"
        )
        assert result.returncode == 1
        assert "Usage:" in result.stderr

    def test_exits_1_on_invalid_url(self):
        result = subprocess.run(
            [sys.executable, "score.py", "not-a-url"],
            capture_output=True, text=True,
            cwd="/Users/patrickmitchell/rote-playoffs"
        )
        assert result.returncode == 1

    def test_runs_on_example_dot_com(self):
        result = subprocess.run(
            [sys.executable, "score.py", "https://example.com"],
            capture_output=True, text=True,
            timeout=30,
            cwd="/Users/patrickmitchell/rote-playoffs"
        )
        assert result.returncode == 0
        assert "AI VISIBILITY AUDIT" in result.stdout
        assert "/ 100" in result.stdout
        assert "AI Crawler Access" in result.stdout
        assert "gravitasindex.com" in result.stdout
```

- [ ] **Step 2: Implement main() and CLI entry point**

Append to `score.py`:
```python
# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main(args):
    """Run the AI Visibility Audit on a URL."""
    if not args:
        print("Usage: python3 score.py <url>", file=sys.stderr)
        sys.exit(1)

    url = args[0]
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    parsed = urlparse(url)
    if not parsed.netloc:
        print(f"Error: invalid URL '{args[0]}'", file=sys.stderr)
        sys.exit(1)

    print(f"Auditing {url} ...\n", file=sys.stderr)

    fetched = fetch_all(url)

    if fetched["html"][0] == 0:
        print(f"Error: could not reach {url}", file=sys.stderr)
        sys.exit(1)

    ext = PageExtractor()
    ext.feed(fetched["html"][1])
    ext.close()

    crawler_score, crawler_signals = score_crawler_access(fetched)
    structured_score, structured_signals = score_structured_data(ext)
    citability_score, citability_signals = score_content_citability(ext)
    authority_score, authority_signals = score_entity_authority(ext)

    scores = {
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

    recs = generate_recommendations(ext, fetched, all_signals)
    report = format_report(url, scores, all_signals, recs)
    print(report)


if __name__ == "__main__":
    main(sys.argv[1:])
```

- [ ] **Step 3: Run unit tests**

```bash
cd /Users/patrickmitchell/rote-playoffs && python3 -m pytest tests/ -v --ignore=tests/test_integration.py
```

Expected: all unit tests pass.

- [ ] **Step 4: Run integration test**

```bash
cd /Users/patrickmitchell/rote-playoffs && python3 -m pytest tests/test_integration.py -v --timeout=30
```

Expected: all 3 tests pass. The example.com test makes a live HTTP request.

- [ ] **Step 5: Manual smoke test on 3 different sites**

```bash
cd /Users/patrickmitchell/rote-playoffs
python3 score.py https://example.com
python3 score.py https://stripe.com
python3 score.py https://boxfordpartners.com
```

Verify: each produces a score, bar charts, and recommendations. Check that recommendations are personalized (site names appear in generated code). Confirm output completes in under 15 seconds per site.

- [ ] **Step 6: Commit**

```bash
cd /Users/patrickmitchell/rote-playoffs
git add score.py tests/test_integration.py
git commit -m "feat: add CLI entry point, complete AI Visibility Audit tool"
```

- [ ] **Step 7: Install Rote**

```bash
curl -fsSL https://getrote.dev/playoffs/install.sh | sh
```

After install, verify:
```bash
which rote
rote --version
```

- [ ] **Step 8: Complete warm-up (sign in + run hello + practice Play)**

In Claude Code:
1. `/play what's new` (verify feed loads)
2. `/play run hello` (run the diagnostic Play)
3. `/play run` a second public Play (e.g., `modiqo/website-launch-readiness`)
4. Post "warmed up" in the Modiqo Discord

- [ ] **Step 9: Capture the audit as a Rote Play**

In Claude Code, run:
```
/play audit the AI visibility of https://boxfordpartners.com using python3 score.py
```

Guide the agent through:
1. Running `python3 /Users/patrickmitchell/rote-playoffs/score.py <url>`
2. Confirming the output is correct
3. When Rote asks where the method should live, choose **Community**

Verify the published Play URI opens and the contract shows:
- Parameters: `url`
- Effect: read-only
- Credentials: none
- Runtime: python3

- [ ] **Step 10: Verify the Play runs for someone else**

Run the published Play via its URI:
```
/play run <your-published-play-uri>
```

Confirm it prompts for a URL, runs the audit, and produces the same report format.
