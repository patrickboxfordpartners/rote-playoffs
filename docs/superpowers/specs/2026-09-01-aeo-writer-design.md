# AEO Content Agent — Design Spec

## Overview

A Rote Play that helps non-technical site owners improve their content's citability by AI assistants. Two modes: a standalone detection audit that scores any existing article's "citability fitness" with educational annotations, and a full content pipeline that drafts, reviews, and publishes improved blog posts to Medium.

**Play name:** `aeo-writer`
**Positioning:** "Your site scores 34/100. Here's why AI skips your content, and how to fix it."
**Target user:** Small business owners and content creators who don't understand how AI assistants select content to cite.

## Design Principles

1. **Educate, don't game.** Annotations explain why content is weak, not that it "looks AI-generated." The same signals that flag AI text also flag generic human writing.
2. **Zero-barrier entry.** The detection mode requires no API keys, no accounts — paste text or point at a file. The full pipeline is the advanced path.
3. **Human review is the point.** The side-by-side UI teaches the user what good citeable writing looks like. It's not an obstacle to automate away.
4. **One funnel.** The AI Visibility Audit (Phase 1) drives users here. Low content citability score → run existing posts through the detector → use the writer to draft better ones.

## Modes

### Mode 1: Detect (standalone, no API keys)

```
aeo-writer detect <file_or_url>
```

Runs the 5-signal detection engine on existing content. Opens the side-by-side review UI with educational annotations. No Claude API key needed, no Medium token needed.

This is the hackathon hook — anyone can try it immediately.

### Mode 2: Write (full pipeline)

```
aeo-writer write --topic "..." --target-url "https://example.com" [--keywords "k1,k2"] [--medium-token TOKEN]
```

Runs the complete pipeline: voice extraction → draft generation → detection audit → side-by-side review → post-edit verification → optional Medium publish.

Requires: `ANTHROPIC_API_KEY` env var. Optional: `MEDIUM_TOKEN` env var for publishing.

## File Structure

```
aeo-writer/
  main.py            - CLI orchestrator (argparse, two subcommands)
  writer.py          - voice extraction + Claude draft generation
  detector.py        - 5-signal heuristic detection engine
  reviewer.py        - HTML generation + local HTTP server + browser open
  publisher.py       - Medium API integration
  templates/
    review.html      - side-by-side review SPA (vanilla JS + CSS grid)
```

**Dependencies:** Python 3.10+ stdlib only, except `anthropic` SDK for write mode. No other pip packages.

## Component 1: Detection Engine (detector.py)

The core of both modes. Five independent signals, each producing per-span annotations with educational explanations.

### Signal 1: Burstiness (sentence length variance)

Human writing mixes short punchy sentences with longer flowing ones. Generic writing tends toward uniform length.

- **Unit:** paragraph
- **Metric:** coefficient of variation (std/mean) of sentence word counts within each paragraph
- **Flag:** CV < 0.3
- **Annotation:** "This paragraph's sentences are all about the same length. Mix in a short sentence or two — AI assistants prefer content with natural rhythm."
- **Weight:** 25%

### Signal 2: Vocabulary Staleness

Certain words appear disproportionately in template-driven and AI-generated content. Their presence signals generic writing, not original thought.

- **Unit:** sentence
- **Metric:** count of stale terms per 1000 words
- **Stale terms list:**

```
delve, tapestry, landscape, moreover, furthermore, it's worth noting,
in conclusion, comprehensive, robust, leverage, utilize, paradigm,
synergy, holistic, nuanced, multifaceted, pivotal, crucial, essential,
fundamental, significantly, ultimately, in today's [noun], navigate,
realm, foster, harness, embark, spearhead, underscore, shed light on,
at the end of the day, it goes without saying, needless to say,
game-changer, cutting-edge, best-in-class, move the needle,
deep dive, unpack, double down
```

- **Flag:** > 5 stale terms per 1000 words
- **Annotation:** "'{term}' is overused in generic content. Replace with a specific word that says what you actually mean."
- **Weight:** 20%

### Signal 3: Hedging Density

Excessive hedging ("may", "might", "could potentially") weakens claims and makes content less citable. AI assistants prefer definitive statements they can quote.

- **Unit:** sentence
- **Metric:** ratio of sentences containing hedge phrases to total sentences
- **Hedge phrases:**

```
may, might, could potentially, it's possible that, arguably,
to some extent, in some cases, it could be said, perhaps,
it seems, appears to, tends to, generally speaking,
it is worth considering, one might argue
```

- **Flag:** > 15% of sentences contain hedging
- **Annotation:** "This sentence hedges instead of committing. AI assistants cite definitive statements — say what you mean directly."
- **Weight:** 15%

### Signal 4: Structural Monotony

Predictable paragraph structure (same opening patterns, same lengths) signals templated writing. Varied structure signals original thought.

- **Unit:** paragraph
- **Metrics:**
  - Opening word repetition: percentage of paragraphs starting with the same 3 opening words
  - Paragraph length variance: CV of paragraph word counts
- **Flag:** > 40% same opening words OR paragraph CV < 0.25
- **Annotation:** "Your paragraphs follow the same pattern. Start some with a question, a quote, a number, or a single-word sentence — variety signals original thinking."
- **Weight:** 20%

### Signal 5: Specificity Ratio

AI assistants cite content that contains concrete, verifiable details. Vague generalities get skipped.

- **Unit:** paragraph
- **Metric:** ratio of sentences containing at least one concrete specific (numbers, proper nouns, dates, quoted speech, first-person anecdotes, named examples) to total sentences
- **Flag:** < 20% of sentences contain specifics
- **Annotation:** "This paragraph has no specific details — no numbers, names, or examples. AI assistants skip vague content because they can't verify or cite it."
- **Weight:** 20%

### Composite Scoring

Each signal produces a score from 0.0 (strong, citeable writing) to 1.0 (weak, generic writing).

**Overall citability risk levels:**
- **STRONG** (composite < 0.3): "This content is well-structured for AI citation."
- **NEEDS WORK** (0.3 - 0.6): "Some sections could be improved for better AI visibility."
- **WEAK** (> 0.6): "AI assistants are likely skipping this content. See flagged sections."

### Output Format

```python
@dataclass
class FlaggedSpan:
    start: int          # character offset in source text
    end: int            # character offset in source text
    signal: str         # signal name (burstiness, vocabulary, hedging, monotony, specificity)
    score: float        # 0.0-1.0 for this span
    annotation: str     # educational explanation
    suggestion: str     # optional concrete fix suggestion

@dataclass
class DetectionResult:
    text: str                       # original text
    overall_score: float            # 0.0-1.0 composite
    risk_level: str                 # STRONG / NEEDS_WORK / WEAK
    signal_scores: dict[str, float] # per-signal scores
    flags: list[FlaggedSpan]        # all flagged spans
```

## Component 2: Side-by-Side Review UI (reviewer.py)

A local HTTP server serving a single-page HTML app. This is the teaching tool — it shows the user exactly what to fix and why.

### Layout

**Left panel (60% width):** Clean rendered article. Markdown converted to HTML. Readable, no distractions.

**Right panel (40% width):** Same article with flagged passages highlighted. Each highlight is color-coded by signal and has a tooltip/popover with the educational annotation.

### Color Coding

| Signal | Color | Rationale |
|--------|-------|-----------|
| Vocabulary staleness | Red (#e74c3c) | Easy fix — swap one word |
| Burstiness | Orange (#e67e22) | Moderate effort — restructure sentences |
| Structural monotony | Orange (#e67e22) | Moderate effort — restructure paragraphs |
| Hedging | Yellow (#f39c12) | Easy-moderate — remove or strengthen |
| Low specificity | Blue (#3498db) | Requires thought — add concrete details |

### Interaction Flow

1. `reviewer.py` writes detection results to a temp JSON file
2. Starts `http.server` on first available port (default 8787, auto-increment if taken)
3. Opens browser via `webbrowser.open()`
4. HTML page fetches the JSON, renders both panels
5. Right panel: flagged spans are `contenteditable` — user clicks and types directly
6. Score indicator at the top updates live as user edits (recalculates on each blur event via JS)
7. **"Save & Re-check"** button: POSTs edited text to local server, server re-runs full detection, page refreshes with updated results
8. **"Approve"** button (detect mode): saves final text to disk, stops server
9. **"Approve & Publish"** button (write mode): saves final text, proceeds to Medium publish step

### Technical Details

- Server: `http.server.HTTPServer` with custom `BaseHTTPRequestHandler`
- Template: `string.Template` substitution (no Jinja, no external deps)
- JS: vanilla, no framework, no build step
- Markdown → HTML: basic regex conversion (headings, bold, italic, links, lists) — not a full parser, good enough for blog content
- Server serves both the HTML page and handles POST/GET for the JSON data
- CORS not needed (same origin)

## Component 3: Draft Generator (writer.py)

Two responsibilities: voice extraction and article generation.

### Voice Extraction

Fetches the target site's existing content to match the owner's writing style.

1. Fetch target URL + up to 3 internal links (blog posts preferred, detected by URL patterns like `/blog/`, `/posts/`, `/articles/`)
2. Strip HTML, extract text paragraphs
3. Analyze and produce a `voice_profile` dict:

```python
voice_profile = {
    "avg_sentence_length": 14.2,        # words
    "sentence_length_variance": 0.45,    # CV
    "vocabulary_level": "conversational", # conversational / professional / technical
    "uses_first_person": True,
    "uses_questions": True,
    "avg_paragraph_length": 3.8,         # sentences
    "tone_markers": ["direct", "casual", "uses contractions"],
    "sample_openings": ["Here's the thing:", "I've seen this..."],
}
```

4. This profile is injected into the generation prompt so the draft matches the site's existing voice.

### Draft Generation

Claude API call with a carefully constructed prompt:

**System prompt includes:**
- The voice profile (write like this site writes)
- Anti-staleness constraints: "Vary sentence lengths. Never use these words: [stale terms list]. Include specific numbers, dates, and names in every section. Avoid hedging — make definitive statements. Start each paragraph differently."
- Medium formatting: use H2/H3 (no H1), short paragraphs, embed images as markdown
- Target keywords to weave in naturally

**Parameters:**
- Model: claude-sonnet-4-20250514 (fast, good writing quality)
- Temperature: 0.9 (higher variance for more natural output)
- Max tokens: 4000

**Output:** markdown string, saved to `drafts/{topic_slug}.md`

## Component 4: Medium Publisher (publisher.py)

Medium REST API v1 integration.

### Authentication

- Integration token from env var `MEDIUM_TOKEN`
- GET `https://api.medium.com/v1/me` to get user ID

### Publishing

- POST `https://api.medium.com/v1/users/{userId}/posts`
- Content format: markdown
- Publish status: draft (default) or public (with `--publish` flag)
- Tags: derived from keywords (max 5 per Medium's limit)
- Canonical URL: optional, set if the content also lives on the target site

### Error Handling

- Missing token: skip publish step, save to local file, print instructions for getting a token
- API errors: print error, save to local file as fallback
- Rate limits: single retry after 5 seconds

## Component 5: CLI Orchestrator (main.py)

```
usage: aeo-writer <command> [options]

commands:
  detect    Run citability audit on existing content
  write     Generate, review, and publish new content

detect options:
  <file>              Path to text/markdown file to analyze
  --url URL           Fetch and analyze content from URL instead
  --no-browser        Print results to terminal instead of opening review UI
  --json              Output detection results as JSON

write options:
  --topic TOPIC       Article topic (required)
  --target-url URL    Target site to match voice (required)
  --keywords KW       Comma-separated target keywords
  --medium-token TOK  Medium integration token (or set MEDIUM_TOKEN env var)
  --publish           Publish to Medium as public (default: draft)
  --no-review         Skip the review UI (for automation)
  --output FILE       Save final article to file instead of publishing
```

### Pipeline Flow (write mode)

1. Parse args, validate ANTHROPIC_API_KEY is set
2. Voice extraction: fetch target URL, build voice profile
3. Draft generation: call Claude API, save draft to `drafts/`
4. Detection audit: run 5-signal engine on the draft
5. If `--no-review`: skip to step 7
6. Review UI: start server, open browser, wait for user approval
7. Post-edit verification: re-run detection on edited text
8. If composite score > 0.6: warn user, offer another review round
9. If MEDIUM_TOKEN set and not `--output`: publish to Medium
10. Print summary: word count, detection score before/after, Medium URL if published

## Rote Play Packaging

### Play Definition (main.ts)

Same pattern as `ai-visibility-audit`:
- YAML frontmatter with `steps_with_presentation` execution model
- `process.exec` step running `python3 main.py` with parameter passthrough
- Resources: all `.py` files + `templates/review.html`

### Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| command | string | yes | "detect" or "write" |
| input | string | yes | File path (detect) or topic (write) |
| target_url | string | no | Target site URL for voice matching (write mode) |
| keywords | string | no | Comma-separated keywords |
| publish | boolean | no | Publish to Medium as public (default: false) |

### deps.toml

```toml
schema_version = 1

[[tools]]
id = "python3"
command = "python3"
required = true
version_requirement = ">=3.10.0"
```

### Play Contract

- **Effect:** Read-only in detect mode. Write (Medium API) in write mode with explicit user consent.
- **Credentials:** None for detect mode. ANTHROPIC_API_KEY + optional MEDIUM_TOKEN for write mode.
- **Runtime:** python3 stdlib + anthropic SDK
- **Network:** Target URL (voice extraction), api.anthropic.com (draft generation), api.medium.com (publishing)
- **Privacy:** Article text sent to Claude API for generation. No other telemetry.

## Testing Strategy

### Unit Tests (detector.py)

- Each signal tested independently with known-AI and known-human text samples
- Edge cases: empty text, single sentence, single paragraph, all-caps, non-English characters
- Composite score math verified
- FlaggedSpan offsets verified against source text

### Unit Tests (writer.py)

- Voice profile extraction from sample HTML
- Prompt construction includes all anti-staleness constraints
- Voice profile dict has all required keys

### Unit Tests (publisher.py)

- Tag truncation to 5
- Draft vs public status
- Error handling for missing token
- Markdown content encoding

### Integration Tests (main.py)

- Detect mode with a sample file produces valid DetectionResult
- Detect mode with `--json` produces parseable JSON
- Write mode without ANTHROPIC_API_KEY exits with clear error message
- Write mode with `--no-review --output` skips UI and saves to file

### Manual Testing

- Run detect mode on 3 known-AI articles (GPT-4, Claude, Gemini output)
- Run detect mode on 3 known-human articles (published journalists)
- Verify AI articles score higher (> 0.5) than human articles (< 0.4)
- Verify the review UI loads, edits save, and re-check updates scores

## Success Criteria

1. `aeo-writer detect` runs on any text file in under 2 seconds with no API keys
2. Detection engine correctly distinguishes AI-written from human-written content (> 70% accuracy on a 20-article test set)
3. Side-by-side review UI loads in any modern browser, edits are functional, scores update
4. A first-time user understands every annotation without external documentation
5. Full write pipeline produces a Medium draft in under 60 seconds
6. The detect mode is compelling enough that a hackathon participant tries it on their own blog post

## Hackathon Strategy

- **Lead with detect mode** in the demo — zero setup, instant value
- **The audit → detector pipeline** is the story: "You scored 34. Here's why. Here's how to fix it."
- **Share-worthy output:** the side-by-side UI with color-coded annotations is visually compelling
- **Adoption hook:** every participant can scan their own blog posts immediately
