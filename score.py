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
