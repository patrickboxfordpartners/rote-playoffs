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
        if not has_robots:
            for bot in ["GPTBot", "ClaudeBot", "PerplexityBot"]:
                signals[f"{bot}_allowed"] = False
            signals["GoogleOther_allowed"] = False
            return score, signals

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
        if signals["brand_consistent"]:
            score += 4
    else:
        signals["brand_consistent"] = False

    return score, signals


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
