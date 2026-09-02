# AI Visibility Audit — Play Design Spec

## Overview

A Rote Play that scores how discoverable any public website is to AI assistants (ChatGPT, Claude, Perplexity, Google AI Overviews) and produces ranked fix recommendations with copy-pasteable implementation code.

**Play name:** `ai-visibility-audit`
**Parameters:** `url` (required) — the site to audit
**Effect:** Read-only (no writes)
**Credentials:** None
**Runtime dependency:** `python3`
**Harness:** Claude Code (`/play`)

## Scoring System

100-point rubric across 4 dimensions.

### 1. AI Crawler Access (25 points)

| Signal | Points | How checked |
|--------|--------|-------------|
| robots.txt exists and is parseable | 3 | `GET /robots.txt`, status 200, valid format |
| GPTBot not blocked | 3 | Parse User-agent/Disallow rules |
| ClaudeBot not blocked | 3 | Parse User-agent/Disallow rules |
| PerplexityBot not blocked | 3 | Parse User-agent/Disallow rules |
| GoogleOther / Google-Extended not blocked | 3 | Parse User-agent/Disallow rules |
| llms.txt present | 5 | `GET /.well-known/llms.txt` or `/llms.txt`, status 200 |
| llms-full.txt present | 2 | `GET /.well-known/llms-full.txt`, status 200 |
| sitemap.xml accessible | 3 | `GET /sitemap.xml`, status 200, valid XML |

### 2. Structured Data (30 points)

| Signal | Points | How checked |
|--------|--------|-------------|
| At least one JSON-LD block | 5 | Parse `<script type="application/ld+json">` |
| Uses @graph (connected entities) | 5 | Check for `"@graph"` key in JSON-LD |
| Organization or LocalBusiness schema | 5 | Check @type in JSON-LD |
| Schema completeness (name, url, logo, description, sameAs) | 5 | Check required fields present |
| FAQ or HowTo schema present | 3 | Check @type |
| Breadcrumb schema present | 2 | Check @type |
| Open Graph tags (og:title, og:description, og:image, og:type) | 3 | Parse `<meta property="og:*">` |
| Twitter Card tags (twitter:card, twitter:title, twitter:description) | 2 | Parse `<meta name="twitter:*">` |

### 3. Content Citability (25 points)

| Signal | Points | How checked |
|--------|--------|-------------|
| Exactly one H1 tag | 3 | Count `<h1>` elements |
| H2-H6 heading depth (at least 3 levels used) | 3 | Count distinct heading levels |
| Content length >= 300 words on page | 3 | Strip tags, count words |
| Short paragraphs (median < 100 words) | 3 | Parse `<p>` tags, compute median length |
| Question-answer patterns (FAQ-style content) | 3 | Detect `?` in headings or definition lists |
| Lists present (ul/ol) | 2 | Check for `<ul>` or `<ol>` |
| Tables present | 2 | Check for `<table>` |
| Meta description present and 120-160 chars | 3 | Parse `<meta name="description">` |
| Image alt text coverage >= 80% | 3 | Count `<img>` with/without alt |

### 4. Entity & Authority (20 points)

| Signal | Points | How checked |
|--------|--------|-------------|
| Organization schema has sameAs (social links) | 5 | Check sameAs array in JSON-LD |
| sameAs has >= 3 profiles | 2 | Count sameAs entries |
| Author/Person schema present | 3 | Check @type Person in JSON-LD |
| Contact page linked (href contains "contact") | 3 | Scan `<a>` hrefs |
| About page linked (href contains "about") | 3 | Scan `<a>` hrefs |
| Brand name consistent across title, og:title, schema name | 4 | Extract and compare brand strings |

## Technical Architecture

### Step DAG

```
[fetch_html] ──────────┐
[fetch_robots_txt] ─────┤
[fetch_llms_txt] ───────┤──> [score_and_report]
[fetch_llms_full_txt] ──┤
[fetch_sitemap_xml] ────┘
```

The five fetch steps run in parallel (no dependencies between them). `score_and_report` depends on all five and produces the final output.

### Fetching Strategy

Each fetch step:
1. `curl -sS -L -o <output_file> -w '%{http_code}' --max-time 10 <url>`
2. Capture HTTP status code
3. Store response body in a temp file for the scoring step

### Scoring Engine

A single Python3 script (`score.py`) that:
1. Reads the 5 fetched files (HTML, robots.txt, llms.txt, llms-full.txt, sitemap.xml)
2. Parses HTML with `html.parser` (stdlib only, no pip dependencies)
3. Evaluates each signal from the rubric
4. Computes dimension scores and total
5. Generates ranked fix recommendations with implementation code
6. Outputs formatted report to stdout

**No external dependencies.** Python3 stdlib only (`html.parser`, `json`, `re`, `urllib.parse`, `xml.etree.ElementTree`, `textwrap`).

### Fix Recommendation Engine

Each failed signal maps to a fix recommendation with:
- **What:** One-line description
- **Why:** Impact explanation (how it helps AI discoverability)
- **Points:** How many points this fix recovers
- **Code:** The actual content/markup to add, personalized with data extracted from the site

Recommendations are sorted by points descending (highest impact first), capped at top 5.

#### Personalized Fix Generation

| Fix | How personalized |
|-----|-----------------|
| llms.txt | Site name from `<title>`, description from meta description, doc links from sitemap |
| robots.txt rules | Only lists the specific crawlers currently blocked |
| Organization JSON-LD | Fills name from title/og:title, url from canonical/input, logo from og:image, sameAs from detected social links |
| FAQ schema | Extracts existing question-like headings and their following content |
| Meta description | Generates suggested description from first paragraph content |
| Social sameAs | Lists detected social links already on the page that need to be added to schema |

### Output Format

```
AI VISIBILITY AUDIT — {domain}
Score: {total} / 100

AI Crawler Access     {bar}  {score}/25
Structured Data       {bar}  {score}/30
Content Citability    {bar}  {score}/25
Entity & Authority    {bar}  {score}/20

DIMENSION DETAILS:
[Per-dimension pass/fail checklist with signal names]

TOP FIXES (by impact):

1. {fix_title} (+{points}pts)
   {why_it_matters}
   ───
   {copy_pasteable_code}
   ───

2. ...

Want automated weekly monitoring? gravitasindex.com
```

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| url | string | yes | The public URL to audit (homepage recommended) |

## Play Contract

- **Effect:** Read-only. No files written, no APIs called beyond the target URL.
- **Credentials:** None required.
- **Runtime:** python3 (stdlib only)
- **Network:** HTTP GET requests to the target domain only (5 endpoints)
- **Privacy:** No data sent anywhere except to the target URL. No telemetry.

## What This Does NOT Check

Out of scope for v1 (keeps the Play focused and fast):
- JavaScript-rendered content (no browser engine)
- Page speed / Core Web Vitals
- Backlinks or domain authority
- Multi-page crawl (homepage only)
- SSL/TLS configuration
- Security headers

These are explicitly NOT included because they overlap with the existing `website-launch-readiness` Play and dilute the AI-specific focus.

## Success Criteria

1. Runs to completion on any public URL in under 15 seconds
2. Score is reproducible (same URL = same score)
3. A developer who has never seen the Play understands the output without explanation
4. At least 3 of the top 5 recommendations include copy-pasteable code
5. Zero false positives on the pass/fail checklist (if it says something is missing, it is)

## Monetization

One line at the very end of the output: `Want automated weekly monitoring? gravitasindex.com`

No branding in the Play name, no upsell in the middle of the report. Trust first, convert later.

## Hackathon Strategy

- **Primary Play:** This AI Visibility Audit (the main submission)
- **Adoption driver:** Every participant will scan their own portfolio/project
- **Social angle:** Participants will screenshot their scores and share (competitive element)
- **Differentiation:** Only AI-focused audit in the registry, with actionable code output
