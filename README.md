# AEO Toolkit — Make Your Content Visible to AI

Three tools that audit and improve how AI assistants see your site. Zero API keys for the core audit. All Python stdlib.

## The Problem

AI assistants (ChatGPT, Claude, Perplexity, Google AI) now drive significant traffic. If your site isn't optimized for them, you're invisible to a growing audience. Most people don't know what AI assistants look for, and existing SEO tools don't check for it.

## The Tools

### `aeo-pipeline` — Full AI Readiness Scan

One URL in, complete diagnosis out. Combines technical visibility, content quality, and agent readiness into a single 0-100 score. Opens an interactive dashboard with side-by-side comparison.

```
$ python3 -m aeo_pipeline boxfordpartners.com

================================================================
  AI READINESS REPORT: boxfordpartners.com
================================================================

  AI Readiness Score: 80/100  (A — Excellent)

  TECHNICAL VISIBILITY  [65/100]
  ────────────────────────────────────────────
    AI Crawler Access      ██████████  25/25
    Structured Data        ████████░░  25/30
    Content Citability     █░░░░░░░░░  3/25
    Entity & Authority     ██████░░░░  12/20

  CONTENT QUALITY  [94/100 — STRONG]
  ────────────────────────────────────────────
    burstiness             ██████████  100%
    vocabulary             ████████░░  76%
    hedging                ██████████  100%
    monotony               ██████████  100%
    specificity            █████████░  92%

  AGENT READINESS
  ────────────────────────────────────────────
    Score: 44/100  (D)
    Discovery              █░░░░░░░░░  3/33
    Access                 ████░░░░░░  30/84
    Usability              ░░░░░░░░░░  3/161
    Payments               ░░░░░░░░░░  0/16
    Cloudflare: Level 1 — Basic Web Presence
```

**Interactive dashboard** opens automatically with:
- Side-by-side view: your site with content annotations + scored report
- Agent readiness breakdown (ora.ai + Cloudflare AI Gateway)
- Downloadable standalone HTML report
- Plain-language explanations of why each signal matters

```bash
# Standard mode (no API keys needed)
python3 -m aeo_pipeline yoursite.com

# Multi-agent mode (with Firecrawl + Mitosis + LLM)
python3 -m aeo_pipeline yoursite.com --agents

# Terminal-only output
python3 -m aeo_pipeline yoursite.com --no-browser

# JSON for pipelines
python3 -m aeo_pipeline yoursite.com --json

# As a Rote play
rote play run aeo-pipeline 'url=yoursite.com'
```

#### Multi-Agent Mode (`--agents`)

When API keys are available, the pipeline runs a 4-agent mesh that adds LLM-generated insights:

| Agent | Role | Requires |
|-------|------|----------|
| **Crawl Agent** | Firecrawl-powered JS rendering + page inventory | `FIRECRAWL_API_KEY` |
| **Memory Agent** | Stores scan history, computes deltas between scans | Mitosis (optional) |
| **Reasoning Agent** | Plain-language executive summary + priority actions | `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` |
| **Orchestrator** | Coordinates agents via Cotal mesh or in-process bus | None |

Agents communicate via [Cotal](https://cotal.ai) peer-to-peer mesh in production, or an in-process LocalBus for development. No central orchestrator — agents are lateral peers.

```bash
# Set up API keys (optional — pipeline degrades gracefully without them)
export FIRECRAWL_API_KEY=fc-...
export OPENAI_API_KEY=sk-...
python3 -m aeo_pipeline yoursite.com --agents
```

### `ai-visibility-audit` — Technical Visibility Score

Checks what AI crawlers see: robots.txt rules, llms.txt, structured data, schema markup, content structure, entity signals. Returns a 0-100 score with personalized fix recommendations (including copy-paste code).

```bash
python3 score.py yoursite.com

# As a Rote play
rote play run ai-visibility-audit 'url=yoursite.com'
```

### `aeo-writer` — Content Citability Audit

Analyzes any content against 5 signals that determine whether AI assistants will cite it:

| Signal | What it measures | Why it matters |
|--------|-----------------|----------------|
| **Burstiness** | Sentence length variation | Uniform sentence length signals template-generated content |
| **Vocabulary** | Generic filler words ("leverage", "comprehensive") | AI assistants prefer specific, concrete language |
| **Hedging** | Weak qualifiers ("it's possible that") | Definitive statements get cited; hedged ones get skipped |
| **Monotony** | Repetitive paragraph structure | Varied structure signals authentic expertise |
| **Specificity** | Concrete details vs. vague claims | Numbers, names, and data make content citable |

```bash
# Audit a file
python3 -m aeo_writer detect article.md

# Audit a URL
python3 -m aeo_writer detect https://example.com/blog/post

# Terminal-only output
python3 -m aeo_writer detect article.md --no-browser

# JSON for pipelines
python3 -m aeo_writer detect article.md --json

# As a Rote play
rote play run aeo-writer 'command=detect' 'input=/path/to/article.md'
```

Write mode (requires `ANTHROPIC_API_KEY`) generates new content matching a target site's voice:

```bash
python3 -m aeo_writer write \
  --topic "How to choose a widget" \
  --target-url https://yoursite.com \
  --keywords "widget selection, best widgets"
```

## Quick Start

```bash
# Clone
git clone https://github.com/patrickboxfordpartners/rote-playoffs.git
cd rote-playoffs

# Run the full pipeline on any URL (Python 3.10+, no pip install needed)
python3 -m aeo_pipeline yoursite.com

# Run with enhanced features (optional)
pip install firecrawl-py tavily-python
export FIRECRAWL_API_KEY=fc-...
python3 -m aeo_pipeline yoursite.com --agents

# Run tests
python3 -m pytest tests/ -v
```

## Requirements

- Python 3.10+
- No external dependencies for standard audit mode
- Optional: `firecrawl-py` for JS-rendered page scraping
- Optional: `tavily-python` for enhanced content extraction
- Optional: `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` for LLM-generated insights
- Optional: `anthropic` SDK for aeo-writer write mode
- Optional: `MEDIUM_TOKEN` for publishing to Medium

## How It Works

**Technical Visibility** (ai-visibility-audit) checks 4 dimensions:
- **AI Crawler Access** (25pts) — robots.txt, llms.txt, sitemap, bot allowlists
- **Structured Data** (30pts) — JSON-LD, @graph, Organization/FAQ/HowTo schema, Open Graph
- **Content Citability** (25pts) — heading structure, paragraph length, FAQ patterns, meta description
- **Entity & Authority** (20pts) — sameAs links, author schema, about/contact pages, brand consistency

**Content Quality** (aeo-writer) analyzes 5 signals using a heuristic detection engine. Each signal is weighted and scored 0.0 (strong) to 1.0 (weak):
- Burstiness (25%) — sentence length coefficient of variation
- Vocabulary (20%) — frequency of 40 known overused terms
- Hedging (15%) — density of qualifying/weakening phrases
- Monotony (20%) — paragraph length uniformity
- Specificity (20%) — presence of numbers, proper nouns, concrete details

**Agent Readiness** checks whether AI agents (not just chatbots) can interact with your site:
- Discovery — sitemap, WebMCP, API endpoints
- Access — authentication, CORS, rate limiting
- Usability — structured responses, error handling
- Data sourced from ora.ai scoring API + Cloudflare AI Gateway detection

**Combined score** = 50% technical visibility + 50% content quality when both are available.

## Project Structure

```
score.py                        # AI visibility audit (standalone)
aeo_writer/                     # Content citability engine
  detector.py                   # 5-signal heuristic detection
  reviewer.py                   # Side-by-side review UI server
  writer.py                     # Voice extraction + Claude API drafts
  publisher.py                  # Medium API integration
  __main__.py                   # CLI orchestrator
aeo_pipeline/                   # Unified pipeline
  __main__.py                   # Combines both tools + --agents flag
  dashboard.py                  # Interactive HTML dashboard server
  fetcher.py                    # Firecrawl + Tavily content extraction
  agent_readiness.py            # ora.ai + Cloudflare AI Gateway checks
  templates/dashboard.html      # Dashboard template (40KB)
  agents/                       # Multi-agent intelligence layer
    orchestrator.py             # Pipeline entrypoint + mesh bootstrap
    crawl_agent.py              # Firecrawl-powered site intake
    memory_agent.py             # Mitosis-backed scan history
    reasoning_agent.py          # LLM analysis + plain-language insights
    mesh.py                     # Cotal mesh + LocalBus fallback
    schema.py                   # Typed message schemas
tests/                          # Test suite
```

## Rote Plays

All three tools are packaged as [Rote](https://rote.dev) plays for the hackathon registry:

| Play | Parameters | API Keys |
|------|-----------|----------|
| `aeo-pipeline` | `url` (required) | None for standard; optional keys for `--agents` mode |
| `ai-visibility-audit` | `url` (required) | None |
| `aeo-writer` | `command`, `input` (required); `target_url`, `keywords` (optional) | None for detect; `ANTHROPIC_API_KEY` for write |

## Links

- [AEO Toolkit Landing Page](https://patrickboxfordpartners.github.io/rote-playoffs/) — Interactive guide with FAQ
- [Boxford Partners AEO Tools](https://www.boxfordpartners.com/tools/aeo) — Learn more about AEO and how we use it
- [Rote Play Registry](https://play.modiqo.ai/patrickmitchell/aeo-pipeline@2.0.0) — Run directly via Rote

---

Built for the [Rote Playoffs Hackathon](https://rote.dev/playoffs) (Sep 1-6, 2026) by [Patrick Mitchell](https://boxfordpartners.com).
