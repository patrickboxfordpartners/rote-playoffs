# AEO Toolkit — Make Your Content Visible to AI

Three tools that audit and improve how AI assistants see your site. Zero API keys for the audit pipeline. All Python stdlib.

## The Problem

AI assistants (ChatGPT, Claude, Perplexity) now drive significant traffic. If your site isn't optimized for them, you're invisible to a growing audience. Most people don't know what AI assistants look for, and existing SEO tools don't check for it.

## The Tools

### `aeo-pipeline` — Full AI Readiness Scan

One URL in, complete diagnosis out. Combines technical visibility and content quality into a single 0-100 score.

```
$ python3 -m aeo_pipeline gravitasindex.com

================================================================
  AI READINESS REPORT: gravitasindex.com
================================================================

  AI Readiness Score: 82/100  (A — Excellent)

  TECHNICAL VISIBILITY  [63/100]
  ────────────────────────────────────────────
    AI Crawler Access      █████████░  23/25
    Structured Data        ███████░░░  22/30
    Content Citability     ██████░░░░  14/25
    Entity & Authority     ██░░░░░░░░  4/20

  CONTENT QUALITY  [100/100 — STRONG]
  ────────────────────────────────────────────
    burstiness             ██████████  100%
    vocabulary             ██████████  100%
    hedging                ██████████  100%
    monotony               ██████████  100%
    specificity            ██████████  100%

  PRIORITY ACTION PLAN
  ────────────────────────────────────────────
    1. [TECHNICAL] Wrap JSON-LD in @graph (+5pts visibility)
    2. [TECHNICAL] Add sameAs social links (+5pts visibility)
```

```bash
# As a Rote play
rote play run aeo-pipeline 'url=yoursite.com'
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

| Signal | What it measures |
|--------|-----------------|
| **Burstiness** | Sentence length variation (robotic = uniform) |
| **Vocabulary** | Generic filler words ("leverage", "comprehensive") |
| **Hedging** | Weak qualifiers ("it's possible that", "to some extent") |
| **Monotony** | Repetitive paragraph structure |
| **Specificity** | Concrete details vs. vague claims |

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

The detect mode also opens a local review UI with color-coded annotations — edit directly, recheck, approve.

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
git clone https://github.com/patrickmitchell/rote-playoffs.git
cd rote-playoffs

# Run the full pipeline on any URL (Python 3.10+, no pip install needed)
python3 -m aeo_pipeline yoursite.com

# Run tests
python3 -m pytest tests/ -v
```

## Requirements

- Python 3.10+
- No external dependencies for audit/detect modes
- `anthropic` SDK only needed for write mode (`pip install anthropic`)
- `MEDIUM_TOKEN` only needed for publishing to Medium

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

Content scoring WEAK (< 30/100) with 3+ elevated signals triggers a **Content Quality Alert** explaining the patterns found.

## Project Structure

```
score.py                    # AI visibility audit (standalone)
aeo_writer/                 # Content citability engine
  detector.py               # 5-signal heuristic detection
  reviewer.py               # Side-by-side review UI server
  writer.py                 # Voice extraction + Claude API drafts
  publisher.py              # Medium API integration
  __main__.py               # CLI orchestrator
aeo_pipeline/               # Unified pipeline
  __main__.py               # Combines both tools
tests/                      # 92 tests across all modules
```

## Rote Plays

All three tools are packaged as [Rote](https://rote.dev) plays for the hackathon registry:

| Play | Parameters | API Keys |
|------|-----------|----------|
| `aeo-pipeline` | `url` (required) | None |
| `ai-visibility-audit` | `url` (required) | None |
| `aeo-writer` | `command`, `input` (required); `target_url`, `keywords` (optional) | None for detect; `ANTHROPIC_API_KEY` for write |

---

Built for the [Rote Playoffs Hackathon](https://rote.dev/playoffs) (Sep 1-6, 2026) by [Patrick Mitchell](https://boxfordpartners.com).
