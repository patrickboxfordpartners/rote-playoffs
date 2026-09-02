# AEO Content Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a content citability audit + writing pipeline that teaches non-technical site owners why AI assistants skip their content and helps them fix it.

**Architecture:** A Python package (`aeo_writer/`) with five modules: detection engine (5 heuristic signals), side-by-side review UI (local HTTP server + vanilla JS SPA), draft generator (Claude API + voice extraction), Medium publisher, and CLI orchestrator. Detect mode requires zero API keys; write mode requires `ANTHROPIC_API_KEY`.

**Tech Stack:** Python 3.10+ stdlib, `anthropic` SDK (write mode only), `http.server` for review UI, `string.Template` for HTML templating

**Spec:** `docs/superpowers/specs/2026-09-01-aeo-writer-design.md`

## Global Constraints

- Python 3.10+ stdlib only, except `anthropic` SDK for write mode
- No other pip packages — no Jinja, no flask, no markdown libraries
- All user-facing annotations use educational/citability language, never "AI detection" framing
- Detection scores: 0.0 = strong citeable writing, 1.0 = weak generic writing
- Signal weights: burstiness 25%, vocabulary 20%, hedging 15%, monotony 20%, specificity 20%
- Risk levels: STRONG (< 0.3), NEEDS_WORK (0.3-0.6), WEAK (> 0.6)
- Package structure: `aeo_writer/` with `__init__.py`, relative imports internally (`from .detector import ...`)
- Tests: `tests/aeo_writer/` directory, import as `from aeo_writer.detector import ...`
- Entry point: `python3 -m aeo_writer` (via `__main__.py`)
- All tests run with `pytest tests/aeo_writer/ -v` from the project root

---

### Task 1: Detection Engine — Data Types, Text Utilities, Burstiness & Vocabulary Signals

**Files:**
- Create: `aeo_writer/__init__.py`
- Create: `aeo_writer/detector.py`
- Create: `tests/aeo_writer/__init__.py`
- Create: `tests/aeo_writer/conftest.py`
- Create: `tests/aeo_writer/test_detector.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces:
  - `FlaggedSpan(start: int, end: int, signal: str, score: float, annotation: str, suggestion: str)` dataclass
  - `DetectionResult(text: str, overall_score: float, risk_level: str, signal_scores: dict[str, float], flags: list[FlaggedSpan])` dataclass
  - `split_sentences(text: str) -> list[str]`
  - `split_paragraphs(text: str) -> list[str]`
  - `STALE_TERMS: list[str]` — the 40-term vocabulary blacklist
  - `_score_burstiness(text: str, paragraphs: list[str]) -> tuple[float, list[FlaggedSpan]]`
  - `_score_vocabulary(text: str) -> tuple[float, list[FlaggedSpan]]`

- [ ] **Step 1: Create package structure and shared test fixtures**

Create three empty files for Python package resolution:

`aeo_writer/__init__.py`:
```python
```

`tests/aeo_writer/__init__.py`:
```python
```

`tests/aeo_writer/conftest.py`:
```python
AI_GENERATED_TEXT = """\
In today's rapidly evolving digital landscape, businesses must leverage \
comprehensive strategies to navigate the complexities of online visibility. \
Moreover, it's worth noting that a holistic approach to content creation is \
essential for fundamentally transforming your digital presence.

Furthermore, organizations should consider the multifaceted nature of search \
engine optimization. It's possible that embracing these robust methodologies \
could potentially lead to significant improvements. To some extent, the nuanced \
interplay between content quality and technical optimization may determine success.

Ultimately, the crucial takeaway is that businesses need to embark on a journey \
of digital transformation. By harnessing the power of cutting-edge technologies \
and spearheading innovative content strategies, organizations can effectively \
move the needle on their online performance."""

HUMAN_WRITTEN_TEXT = """\
Last Tuesday, I burned $4,200 on Facebook ads that generated exactly zero sales. \
Not "low ROAS" — literally zero.

Here's what went wrong. My targeting was a mess. I'd copied a lookalike audience \
from a campaign that worked in 2024, but the source audience had degraded. The 37 \
people who originally converted had since been diluted by 2,000+ email subscribers \
who never bought anything.

So I rebuilt from scratch. Started with the 12 customers who spent over $500 in \
the past 90 days. Built a 1% lookalike off that. Three days later: $1,800 in \
spend, $11,400 in revenue. A 6.3x ROAS.

The takeaway? Your source audience quality matters more than your ad creative. \
I've tested this across 14 accounts now. Every time, cleaning the source audience \
beats writing better copy."""
```

- [ ] **Step 2: Write failing tests for text utilities**

`tests/aeo_writer/test_detector.py`:
```python
from aeo_writer.detector import (
    FlaggedSpan, DetectionResult,
    split_sentences, split_paragraphs,
    STALE_TERMS, _score_burstiness, _score_vocabulary,
)
from conftest import AI_GENERATED_TEXT, HUMAN_WRITTEN_TEXT


class TestSplitSentences:
    def test_simple_three_sentences(self):
        result = split_sentences("Hello world. This is a test. Done now.")
        assert len(result) == 3

    def test_single_sentence(self):
        assert len(split_sentences("Just one sentence here.")) == 1

    def test_question_and_exclamation(self):
        result = split_sentences("Really? Yes! I think so.")
        assert len(result) == 3

    def test_empty_string(self):
        assert split_sentences("") == []

    def test_preserves_abbreviations(self):
        result = split_sentences("Dr. Smith went home. He was tired.")
        assert len(result) == 2
        assert "Dr. Smith" in result[0]


class TestSplitParagraphs:
    def test_double_newline(self):
        result = split_paragraphs("First paragraph.\n\nSecond paragraph.")
        assert len(result) == 2

    def test_single_paragraph(self):
        assert len(split_paragraphs("Just one paragraph.")) == 1

    def test_empty_string(self):
        assert split_paragraphs("") == []

    def test_multiple_blank_lines(self):
        result = split_paragraphs("Para one.\n\n\n\nPara two.")
        assert len(result) == 2


class TestFlaggedSpanDataclass:
    def test_creation(self):
        span = FlaggedSpan(start=0, end=10, signal="vocabulary", score=1.0,
                           annotation="test", suggestion="fix this")
        assert span.start == 0
        assert span.signal == "vocabulary"

    def test_default_suggestion(self):
        span = FlaggedSpan(start=0, end=5, signal="test", score=0.5,
                           annotation="note")
        assert span.suggestion == ""


class TestBurstiness:
    def test_uniform_sentences_score_high(self):
        text = "The cat sat down. The dog ran fast. The bird flew high. The fish swam deep."
        score, flags = _score_burstiness(text, [text])
        assert score > 0.5
        assert len(flags) == 1
        assert flags[0].signal == "burstiness"

    def test_varied_sentences_score_low(self):
        text = ("Stop. The quick brown fox jumped over the incredibly lazy dog "
                "that was sleeping peacefully in the warm afternoon sun by the river. "
                "Why? Because it felt like the right thing to do at that exact moment.")
        score, flags = _score_burstiness(text, [text])
        assert score < 0.4

    def test_single_sentence_paragraph_skipped(self):
        text = "Just one sentence here."
        score, flags = _score_burstiness(text, [text])
        assert score == 0.0
        assert flags == []

    def test_ai_text_scores_higher_than_human(self):
        ai_paras = split_paragraphs(AI_GENERATED_TEXT)
        human_paras = split_paragraphs(HUMAN_WRITTEN_TEXT)
        ai_score, _ = _score_burstiness(AI_GENERATED_TEXT, ai_paras)
        human_score, _ = _score_burstiness(HUMAN_WRITTEN_TEXT, human_paras)
        assert ai_score > human_score


class TestVocabulary:
    def test_stale_terms_flagged(self):
        text = "We need to delve into this comprehensive landscape."
        score, flags = _score_vocabulary(text)
        assert score > 0.0
        flagged_terms = {f.annotation.split("'")[1] for f in flags}
        assert "delve" in flagged_terms
        assert "comprehensive" in flagged_terms
        assert "landscape" in flagged_terms

    def test_clean_text_no_flags(self):
        text = "The company grew 40% last year. Sales hit twelve million dollars."
        score, flags = _score_vocabulary(text)
        assert score == 0.0
        assert flags == []

    def test_case_insensitive(self):
        text = "DELVE into the ROBUST system."
        _, flags = _score_vocabulary(text)
        assert len(flags) == 2

    def test_multi_word_phrases_detected(self):
        text = "It's worth noting that we should move the needle here."
        _, flags = _score_vocabulary(text)
        terms = {f.annotation.split("'")[1] for f in flags}
        assert "it's worth noting" in terms
        assert "move the needle" in terms

    def test_ai_text_scores_higher_than_human(self):
        ai_score, _ = _score_vocabulary(AI_GENERATED_TEXT)
        human_score, _ = _score_vocabulary(HUMAN_WRITTEN_TEXT)
        assert ai_score > human_score

    def test_stale_terms_list_has_40_entries(self):
        assert len(STALE_TERMS) == 40
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/aeo_writer/test_detector.py -v`
Expected: FAIL (ImportError — module doesn't exist yet)

- [ ] **Step 4: Implement data types and text utilities**

`aeo_writer/detector.py`:
```python
"""Citability detection engine — 5-signal heuristic analysis."""

import re
from dataclasses import dataclass, field
from statistics import mean, stdev


@dataclass
class FlaggedSpan:
    start: int
    end: int
    signal: str
    score: float
    annotation: str
    suggestion: str = ""


@dataclass
class DetectionResult:
    text: str
    overall_score: float
    risk_level: str
    signal_scores: dict[str, float]
    flags: list[FlaggedSpan] = field(default_factory=list)


_ABBREVS = frozenset({
    "mr", "mrs", "dr", "ms", "prof", "sr", "jr", "st", "vs",
    "etc", "inc", "ltd", "corp", "approx", "dept", "est", "no",
})
_SENT_END = re.compile(r'(?<=[.!?])\s+')


def split_sentences(text: str) -> list[str]:
    if not text.strip():
        return []
    raw = _SENT_END.split(text.strip())
    merged = []
    carry = ""
    for chunk in raw:
        if carry:
            chunk = carry + " " + chunk
            carry = ""
        words = chunk.split()
        if words:
            last = words[-1].rstrip(".!?,:;").lower()
            if last in _ABBREVS:
                carry = chunk
                continue
        merged.append(chunk)
    if carry:
        merged.append(carry)
    return [s for s in merged if s.strip()]


def split_paragraphs(text: str) -> list[str]:
    if not text.strip():
        return []
    parts = re.split(r'\n\s*\n', text.strip())
    return [p.strip() for p in parts if p.strip()]


STALE_TERMS = [
    "delve", "tapestry", "landscape", "moreover", "furthermore",
    "it's worth noting", "in conclusion", "comprehensive", "robust",
    "leverage", "utilize", "paradigm", "synergy", "holistic", "nuanced",
    "multifaceted", "pivotal", "crucial", "essential", "fundamental",
    "significantly", "ultimately", "navigate", "realm", "foster",
    "harness", "embark", "spearhead", "underscore", "shed light on",
    "at the end of the day", "it goes without saying", "needless to say",
    "game-changer", "cutting-edge", "best-in-class", "move the needle",
    "deep dive", "unpack", "double down",
]

_STALE_PATTERNS = [
    (re.compile(r'\b' + re.escape(t) + r'\b', re.IGNORECASE), t)
    for t in STALE_TERMS
]


def _score_burstiness(text: str, paragraphs: list[str]) -> tuple[float, list[FlaggedSpan]]:
    flags = []
    para_cvs = []

    for para in paragraphs:
        sentences = split_sentences(para)
        if len(sentences) < 2:
            continue
        lengths = [len(s.split()) for s in sentences]
        avg = mean(lengths)
        if avg == 0:
            continue
        cv = stdev(lengths) / avg
        para_cvs.append(cv)

        if cv < 0.3:
            start = text.find(para)
            if start == -1:
                continue
            flags.append(FlaggedSpan(
                start=start,
                end=start + len(para),
                signal="burstiness",
                score=max(0.0, 1.0 - cv / 0.3),
                annotation=(
                    "This paragraph's sentences are all about the same length. "
                    "Mix in a short sentence or two — AI assistants prefer content "
                    "with natural rhythm."
                ),
                suggestion="Try varying sentence lengths: follow a long sentence with a short, punchy one.",
            ))

    if not para_cvs:
        return 0.0, flags

    avg_cv = mean(para_cvs)
    score = max(0.0, min(1.0, (0.5 - avg_cv) / 0.4))
    return score, flags


def _score_vocabulary(text: str) -> tuple[float, list[FlaggedSpan]]:
    flags = []
    total_words = len(text.split())
    if total_words == 0:
        return 0.0, flags

    hit_count = 0
    for pattern, term in _STALE_PATTERNS:
        for match in pattern.finditer(text):
            hit_count += 1
            flags.append(FlaggedSpan(
                start=match.start(),
                end=match.end(),
                signal="vocabulary",
                score=1.0,
                annotation=f"'{term}' is overused in generic content. Replace with a specific word that says what you actually mean.",
                suggestion="",
            ))

    hits_per_1000 = hit_count / total_words * 1000
    score = max(0.0, min(1.0, hits_per_1000 / 5.0))
    return score, flags
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/aeo_writer/test_detector.py -v`
Expected: all 21 tests PASS

- [ ] **Step 6: Commit**

```bash
git add aeo_writer/__init__.py aeo_writer/detector.py tests/aeo_writer/__init__.py tests/aeo_writer/conftest.py tests/aeo_writer/test_detector.py
git commit -m "feat(aeo-writer): detection engine foundation — dataclasses, text utils, burstiness & vocabulary signals"
```

---

### Task 2: Detection Engine — Hedging, Monotony, Specificity & Composite Scoring

**Files:**
- Modify: `aeo_writer/detector.py`
- Modify: `tests/aeo_writer/test_detector.py`

**Interfaces:**
- Consumes: `FlaggedSpan`, `DetectionResult`, `split_sentences`, `split_paragraphs`, `_score_burstiness`, `_score_vocabulary` (all from Task 1)
- Produces:
  - `HEDGE_PHRASES: list[str]`
  - `SIGNAL_WEIGHTS: dict[str, float]`
  - `_score_hedging(text: str, sentences: list[str]) -> tuple[float, list[FlaggedSpan]]`
  - `_score_monotony(text: str, paragraphs: list[str]) -> tuple[float, list[FlaggedSpan]]`
  - `_score_specificity(text: str, paragraphs: list[str]) -> tuple[float, list[FlaggedSpan]]`
  - `analyze(text: str) -> DetectionResult` — the main entry point, runs all 5 signals

- [ ] **Step 1: Write failing tests for hedging, monotony, specificity, and analyze()**

Append to `tests/aeo_writer/test_detector.py`:
```python
from aeo_writer.detector import (
    HEDGE_PHRASES, SIGNAL_WEIGHTS,
    _score_hedging, _score_monotony, _score_specificity,
    analyze,
)


class TestHedging:
    def test_heavy_hedging_scores_high(self):
        text = ("It might be possible that this could potentially work. "
                "Perhaps one might argue it seems to be effective. "
                "To some extent, it appears to generally speaking be useful.")
        sentences = split_sentences(text)
        score, flags = _score_hedging(text, sentences)
        assert score > 0.5
        assert len(flags) > 0
        assert all(f.signal == "hedging" for f in flags)

    def test_no_hedging_scores_zero(self):
        text = "Revenue grew 34% last quarter. The product ships tomorrow. Customers love it."
        sentences = split_sentences(text)
        score, flags = _score_hedging(text, sentences)
        assert score == 0.0
        assert flags == []

    def test_standalone_may_in_date_not_flagged(self):
        text = "The event is in May 2026. Registration opens January 15."
        sentences = split_sentences(text)
        _, flags = _score_hedging(text, sentences)
        assert flags == []

    def test_ai_text_scores_higher_than_human(self):
        ai_sents = split_sentences(AI_GENERATED_TEXT)
        human_sents = split_sentences(HUMAN_WRITTEN_TEXT)
        ai_score, _ = _score_hedging(AI_GENERATED_TEXT, ai_sents)
        human_score, _ = _score_hedging(HUMAN_WRITTEN_TEXT, human_sents)
        assert ai_score > human_score


class TestMonotony:
    def test_repetitive_openings_score_high(self):
        text = ("The first point is important.\n\n"
                "The second point follows.\n\n"
                "The third point matters.\n\n"
                "The fourth point concludes.\n\n"
                "The fifth point summarizes.")
        paragraphs = split_paragraphs(text)
        score, flags = _score_monotony(text, paragraphs)
        assert score > 0.5

    def test_varied_openings_score_low(self):
        text = ("Last week I tried something new.\n\n"
                "Here's what happened next.\n\n"
                "3 customers signed up immediately.\n\n"
                "\"Best feature ever,\" one said.\n\n"
                "Why did it work? Simple.")
        paragraphs = split_paragraphs(text)
        score, flags = _score_monotony(text, paragraphs)
        assert score < 0.3

    def test_single_paragraph_scores_zero(self):
        text = "Just one paragraph here."
        paragraphs = split_paragraphs(text)
        score, flags = _score_monotony(text, paragraphs)
        assert score == 0.0


class TestSpecificity:
    def test_vague_text_scores_high(self):
        text = ("Businesses should consider improving their strategies. "
                "Organizations need to think about growth opportunities. "
                "Companies must focus on building better systems.")
        paragraphs = [text]
        score, flags = _score_specificity(text, paragraphs)
        assert score > 0.5
        assert len(flags) == 1
        assert flags[0].signal == "specificity"

    def test_specific_text_scores_low(self):
        text = ("On March 14, 2025, Stripe processed $1.2 billion in payments. "
                "CEO Patrick Collison announced 47 new enterprise clients. "
                "\"We've never seen growth like this,\" he told Reuters.")
        paragraphs = [text]
        score, flags = _score_specificity(text, paragraphs)
        assert score < 0.3
        assert flags == []

    def test_numbers_count_as_specifics(self):
        text = "We gained 500 users in 3 days at $0 cost."
        paragraphs = [text]
        score, _ = _score_specificity(text, paragraphs)
        assert score < 0.3

    def test_ai_text_scores_higher_than_human(self):
        ai_paras = split_paragraphs(AI_GENERATED_TEXT)
        human_paras = split_paragraphs(HUMAN_WRITTEN_TEXT)
        ai_score, _ = _score_specificity(AI_GENERATED_TEXT, ai_paras)
        human_score, _ = _score_specificity(HUMAN_WRITTEN_TEXT, human_paras)
        assert ai_score > human_score


class TestAnalyze:
    def test_returns_detection_result(self):
        result = analyze(HUMAN_WRITTEN_TEXT)
        assert isinstance(result, DetectionResult)
        assert result.text == HUMAN_WRITTEN_TEXT
        assert 0.0 <= result.overall_score <= 1.0
        assert result.risk_level in ("STRONG", "NEEDS_WORK", "WEAK")
        assert set(result.signal_scores.keys()) == {
            "burstiness", "vocabulary", "hedging", "monotony", "specificity"
        }

    def test_ai_text_scores_higher_than_human(self):
        ai_result = analyze(AI_GENERATED_TEXT)
        human_result = analyze(HUMAN_WRITTEN_TEXT)
        assert ai_result.overall_score > human_result.overall_score

    def test_ai_text_is_weak_or_needs_work(self):
        result = analyze(AI_GENERATED_TEXT)
        assert result.risk_level in ("WEAK", "NEEDS_WORK")

    def test_human_text_is_strong(self):
        result = analyze(HUMAN_WRITTEN_TEXT)
        assert result.risk_level == "STRONG"

    def test_empty_text(self):
        result = analyze("")
        assert result.overall_score == 0.0
        assert result.risk_level == "STRONG"
        assert result.flags == []

    def test_signal_weights_sum_to_one(self):
        assert abs(sum(SIGNAL_WEIGHTS.values()) - 1.0) < 0.001

    def test_flags_have_valid_offsets(self):
        result = analyze(AI_GENERATED_TEXT)
        for flag in result.flags:
            assert 0 <= flag.start < flag.end <= len(AI_GENERATED_TEXT)
            assert flag.signal in SIGNAL_WEIGHTS
```

- [ ] **Step 2: Run tests to verify new tests fail (old tests still pass)**

Run: `pytest tests/aeo_writer/test_detector.py -v`
Expected: Task 1 tests PASS, new tests FAIL (ImportError on missing names)

- [ ] **Step 3: Implement hedging signal**

Append to `aeo_writer/detector.py`:
```python
HEDGE_PHRASES = [
    "could potentially", "it's possible that", "arguably",
    "to some extent", "in some cases", "it could be said", "perhaps",
    "it seems", "appears to", "tends to", "generally speaking",
    "it is worth considering", "one might argue",
]

_HEDGE_PATTERNS = [
    (re.compile(r'\b' + re.escape(h) + r'\b', re.IGNORECASE), h)
    for h in HEDGE_PHRASES
]

_MAY_MIGHT = re.compile(
    r'\b(may|might)\b(?!\s+\d{4})(?!\s+[A-Z][a-z]{2,8}\b)',
    re.IGNORECASE,
)


def _score_hedging(text: str, sentences: list[str]) -> tuple[float, list[FlaggedSpan]]:
    flags = []
    if not sentences:
        return 0.0, flags

    hedging_sentence_count = 0

    for sent in sentences:
        found_hedge = False
        for pattern, phrase in _HEDGE_PATTERNS:
            for match in pattern.finditer(sent):
                offset = text.find(sent)
                if offset == -1:
                    continue
                flags.append(FlaggedSpan(
                    start=offset + match.start(),
                    end=offset + match.end(),
                    signal="hedging",
                    score=1.0,
                    annotation=(
                        "This sentence hedges instead of committing. "
                        "AI assistants cite definitive statements — say what you mean directly."
                    ),
                    suggestion=f"Remove or replace '{phrase}' with a direct statement.",
                ))
                found_hedge = True

        for match in _MAY_MIGHT.finditer(sent):
            offset = text.find(sent)
            if offset == -1:
                continue
            flags.append(FlaggedSpan(
                start=offset + match.start(),
                end=offset + match.end(),
                signal="hedging",
                score=0.8,
                annotation=(
                    "This sentence hedges instead of committing. "
                    "AI assistants cite definitive statements — say what you mean directly."
                ),
                suggestion=f"Replace '{match.group()}' with a definitive verb.",
            ))
            found_hedge = True

        if found_hedge:
            hedging_sentence_count += 1

    ratio = hedging_sentence_count / len(sentences)
    score = max(0.0, min(1.0, ratio / 0.15))
    return score, flags
```

- [ ] **Step 4: Implement monotony signal**

Append to `aeo_writer/detector.py`:
```python
def _score_monotony(text: str, paragraphs: list[str]) -> tuple[float, list[FlaggedSpan]]:
    flags = []
    if len(paragraphs) < 3:
        return 0.0, flags

    openers = []
    lengths = []
    for para in paragraphs:
        words = para.split()
        lengths.append(len(words))
        opener = " ".join(words[:3]).lower() if len(words) >= 3 else para.lower()
        openers.append(opener)

    from collections import Counter
    opener_counts = Counter(openers)
    most_common_count = opener_counts.most_common(1)[0][1]
    opener_repetition = most_common_count / len(paragraphs)

    avg_len = mean(lengths)
    length_cv = stdev(lengths) / avg_len if avg_len > 0 else 0.0

    opener_score = max(0.0, min(1.0, (opener_repetition - 0.2) / 0.2))
    length_score = max(0.0, min(1.0, (0.4 - length_cv) / 0.15))
    monotony = max(opener_score, length_score)

    if opener_repetition > 0.4 or length_cv < 0.25:
        for para in paragraphs:
            start = text.find(para)
            if start == -1:
                continue
            flags.append(FlaggedSpan(
                start=start,
                end=start + len(para),
                signal="monotony",
                score=monotony,
                annotation=(
                    "Your paragraphs follow the same pattern. Start some with a question, "
                    "a quote, a number, or a single-word sentence — variety signals original thinking."
                ),
                suggestion="Vary your paragraph openings and lengths.",
            ))

    return monotony, flags
```

- [ ] **Step 5: Implement specificity signal**

Append to `aeo_writer/detector.py`:
```python
_SPECIFICS = re.compile(
    r'(?:'
    r'\$[\d,]+\.?\d*'           # dollar amounts
    r'|\b\d[\d,.]*%?'           # numbers/percentages
    r'|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d'
    r'|\b\d{4}\b'              # years
    r'|"[^"]{3,}"'             # quoted speech
    r"|'[^']{3,}'"             # quoted speech (single)
    r'|\bI\s+(?:was|am|have|had|went|saw|tried|built|tested|ran|found|made|got|did)\b'  # first-person anecdotes
    r'|\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b'  # multi-word proper nouns
    r')',
    re.MULTILINE,
)


def _score_specificity(text: str, paragraphs: list[str]) -> tuple[float, list[FlaggedSpan]]:
    flags = []
    if not paragraphs:
        return 0.0, flags

    all_sentences = []
    specific_count = 0

    for para in paragraphs:
        sentences = split_sentences(para)
        para_has_specific = False
        for sent in sentences:
            all_sentences.append(sent)
            if _SPECIFICS.search(sent):
                specific_count += 1
                para_has_specific = True

        if not para_has_specific and sentences:
            start = text.find(para)
            if start == -1:
                continue
            flags.append(FlaggedSpan(
                start=start,
                end=start + len(para),
                signal="specificity",
                score=1.0,
                annotation=(
                    "This paragraph has no specific details — no numbers, names, or examples. "
                    "AI assistants skip vague content because they can't verify or cite it."
                ),
                suggestion="Add a concrete number, date, name, or example.",
            ))

    if not all_sentences:
        return 0.0, flags

    ratio = specific_count / len(all_sentences)
    score = max(0.0, min(1.0, (0.3 - ratio) / 0.3))
    return score, flags
```

- [ ] **Step 6: Implement composite analyze() function**

Append to `aeo_writer/detector.py`:
```python
SIGNAL_WEIGHTS = {
    "burstiness": 0.25,
    "vocabulary": 0.20,
    "hedging": 0.15,
    "monotony": 0.20,
    "specificity": 0.20,
}


def analyze(text: str) -> DetectionResult:
    if not text.strip():
        return DetectionResult(
            text=text,
            overall_score=0.0,
            risk_level="STRONG",
            signal_scores={k: 0.0 for k in SIGNAL_WEIGHTS},
            flags=[],
        )

    paragraphs = split_paragraphs(text)
    sentences = split_sentences(text)

    scores = {}
    all_flags = []

    s, f = _score_burstiness(text, paragraphs)
    scores["burstiness"] = s
    all_flags.extend(f)

    s, f = _score_vocabulary(text)
    scores["vocabulary"] = s
    all_flags.extend(f)

    s, f = _score_hedging(text, sentences)
    scores["hedging"] = s
    all_flags.extend(f)

    s, f = _score_monotony(text, paragraphs)
    scores["monotony"] = s
    all_flags.extend(f)

    s, f = _score_specificity(text, paragraphs)
    scores["specificity"] = s
    all_flags.extend(f)

    overall = sum(scores[k] * SIGNAL_WEIGHTS[k] for k in SIGNAL_WEIGHTS)

    if overall < 0.3:
        risk = "STRONG"
    elif overall < 0.6:
        risk = "NEEDS_WORK"
    else:
        risk = "WEAK"

    return DetectionResult(
        text=text,
        overall_score=round(overall, 3),
        risk_level=risk,
        signal_scores={k: round(v, 3) for k, v in scores.items()},
        flags=all_flags,
    )
```

- [ ] **Step 7: Run all tests**

Run: `pytest tests/aeo_writer/test_detector.py -v`
Expected: all tests PASS (Task 1 + Task 2 tests)

- [ ] **Step 8: Commit**

```bash
git add aeo_writer/detector.py tests/aeo_writer/test_detector.py
git commit -m "feat(aeo-writer): complete detection engine — hedging, monotony, specificity signals + composite analyze()"
```

---

### Task 3: Side-by-Side Review UI

**Files:**
- Create: `aeo_writer/templates/review.html`
- Create: `aeo_writer/reviewer.py`
- Create: `tests/aeo_writer/test_reviewer.py`

**Interfaces:**
- Consumes:
  - `DetectionResult` from `aeo_writer.detector` (Task 1)
  - `analyze(text: str) -> DetectionResult` from `aeo_writer.detector` (Task 2)
- Produces:
  - `markdown_to_html(md: str) -> str` — basic markdown to HTML conversion
  - `result_to_json(result: DetectionResult) -> str` — serialize for the browser
  - `start_review(result: DetectionResult, mode: str = "detect", output_path: str = None) -> str | None` — starts HTTP server, opens browser, blocks until user approves, returns edited text or None

- [ ] **Step 1: Write failing tests for reviewer**

`tests/aeo_writer/test_reviewer.py`:
```python
import json
import threading
import time
from urllib.request import urlopen, Request
from urllib.error import URLError

from aeo_writer.detector import analyze
from aeo_writer.reviewer import markdown_to_html, result_to_json, ReviewServer
from conftest import HUMAN_WRITTEN_TEXT


class TestMarkdownToHtml:
    def test_headings(self):
        assert "<h2>" in markdown_to_html("## Hello")
        assert "<h3>" in markdown_to_html("### World")

    def test_bold(self):
        assert "<strong>" in markdown_to_html("This is **bold** text")

    def test_italic(self):
        assert "<em>" in markdown_to_html("This is *italic* text")

    def test_links(self):
        html = markdown_to_html("[click](https://example.com)")
        assert 'href="https://example.com"' in html

    def test_paragraphs(self):
        html = markdown_to_html("First paragraph.\n\nSecond paragraph.")
        assert html.count("<p>") == 2

    def test_lists(self):
        html = markdown_to_html("- item one\n- item two\n- item three")
        assert "<li>" in html

    def test_empty_string(self):
        assert markdown_to_html("") == ""


class TestResultToJson:
    def test_valid_json(self):
        result = analyze(HUMAN_WRITTEN_TEXT)
        data = json.loads(result_to_json(result))
        assert "text" in data
        assert "overall_score" in data
        assert "flags" in data
        assert isinstance(data["flags"], list)

    def test_flags_have_required_fields(self):
        result = analyze(HUMAN_WRITTEN_TEXT)
        data = json.loads(result_to_json(result))
        for flag in data["flags"]:
            assert "start" in flag
            assert "end" in flag
            assert "signal" in flag
            assert "annotation" in flag


class TestReviewServer:
    def test_server_starts_and_serves_html(self):
        result = analyze(HUMAN_WRITTEN_TEXT)
        server = ReviewServer(result, mode="detect", open_browser=False)
        thread = threading.Thread(target=server.serve_until_approved)
        thread.daemon = True
        thread.start()
        time.sleep(0.3)

        try:
            resp = urlopen(f"http://127.0.0.1:{server.port}/")
            html = resp.read().decode()
            assert "Content Citability Review" in html
        finally:
            server.shutdown()
            thread.join(timeout=2)

    def test_api_data_endpoint(self):
        result = analyze(HUMAN_WRITTEN_TEXT)
        server = ReviewServer(result, mode="detect", open_browser=False)
        thread = threading.Thread(target=server.serve_until_approved)
        thread.daemon = True
        thread.start()
        time.sleep(0.3)

        try:
            resp = urlopen(f"http://127.0.0.1:{server.port}/api/data")
            data = json.loads(resp.read())
            assert "overall_score" in data
            assert "flags" in data
        finally:
            server.shutdown()
            thread.join(timeout=2)

    def test_approve_endpoint_stops_server(self):
        result = analyze(HUMAN_WRITTEN_TEXT)
        server = ReviewServer(result, mode="detect", open_browser=False)
        thread = threading.Thread(target=server.serve_until_approved)
        thread.daemon = True
        thread.start()
        time.sleep(0.3)

        try:
            req = Request(
                f"http://127.0.0.1:{server.port}/api/approve",
                data=json.dumps({"text": "edited text"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urlopen(req)
            assert resp.status == 200
            assert server.approved_text == "edited text"
        finally:
            server.shutdown()
            thread.join(timeout=2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/aeo_writer/test_reviewer.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Create the HTML template**

`aeo_writer/templates/review.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Content Citability Review</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,system-ui,'Segoe UI',sans-serif;background:#0f0f23;color:#e0e0e0}
.header{display:flex;align-items:center;justify-content:space-between;padding:12px 24px;background:#1a1a2e;border-bottom:1px solid #333}
.header h1{font-size:18px;font-weight:600;color:#fff}
.score-badge{display:inline-flex;align-items:center;gap:8px;padding:6px 16px;border-radius:20px;font-weight:700;font-size:14px}
.score-strong{background:#1a472a;color:#2ecc71}
.score-needs-work{background:#4a3500;color:#f39c12}
.score-weak{background:#4a1a1a;color:#e74c3c}
.legend{display:flex;gap:16px;font-size:12px;padding:8px 24px;background:#16213e;border-bottom:1px solid #333}
.legend-item{display:flex;align-items:center;gap:4px}
.legend-dot{width:10px;height:10px;border-radius:50%;display:inline-block}
.actions{display:flex;gap:8px}
.btn{padding:8px 16px;border:none;border-radius:6px;font-size:13px;font-weight:600;cursor:pointer}
.btn-secondary{background:#333;color:#e0e0e0}
.btn-secondary:hover{background:#444}
.btn-primary{background:#3498db;color:#fff}
.btn-primary:hover{background:#2980b9}
.panels{display:grid;grid-template-columns:1fr 1fr;height:calc(100vh - 90px)}
.panel{overflow-y:auto;padding:24px 32px;line-height:1.7}
.panel-left{border-right:1px solid #333}
.panel-left h2,.panel-left h3{margin:24px 0 12px;color:#fff}
.panel-left p{margin:0 0 16px;color:#ccc}
.panel-right{background:#1a1a2e}
.flag{position:relative;cursor:pointer;border-radius:2px;padding:1px 0}
.flag-vocabulary{background:rgba(231,76,60,0.15);border-bottom:2px solid #e74c3c}
.flag-burstiness,.flag-monotony{background:rgba(230,126,34,0.15);border-bottom:2px solid #e67e22}
.flag-hedging{background:rgba(243,156,18,0.15);border-bottom:2px solid #f39c12}
.flag-specificity{background:rgba(52,152,219,0.15);border-bottom:2px solid #3498db}
.tooltip{display:none;position:absolute;bottom:calc(100% + 8px);left:0;min-width:280px;max-width:400px;padding:12px;background:#16213e;border:1px solid #444;border-radius:8px;font-size:13px;line-height:1.5;color:#ddd;z-index:100;box-shadow:0 4px 12px rgba(0,0,0,0.4)}
.flag:hover .tooltip{display:block}
.tooltip .signal-label{font-weight:700;text-transform:uppercase;font-size:11px;letter-spacing:0.5px;margin-bottom:4px}
.tooltip .suggestion{color:#999;font-size:12px;margin-top:6px}
.signal-scores{display:flex;gap:12px;padding:12px 24px;background:#16213e;font-size:12px}
.signal-score{display:flex;align-items:center;gap:6px}
.signal-bar{width:60px;height:6px;border-radius:3px;background:#333;overflow:hidden}
.signal-fill{height:100%;border-radius:3px;transition:width 0.3s}
[contenteditable=true]{outline:none;border-radius:3px}
[contenteditable=true]:focus{box-shadow:0 0 0 2px rgba(52,152,219,0.4)}
.para-block{margin-bottom:16px;padding:8px 12px;border-radius:6px;border-left:3px solid transparent}
.para-block.flagged{border-left-color:#e67e22}
</style>
</head>
<body>
<div class="header">
  <h1>Content Citability Review</h1>
  <div class="score-badge" id="score-badge"></div>
  <div class="actions">
    <button class="btn btn-secondary" id="btn-recheck">Save &amp; Re-check</button>
    <button class="btn btn-primary" id="btn-approve">Approve</button>
  </div>
</div>
<div class="legend">
  <div class="legend-item"><span class="legend-dot" style="background:#e74c3c"></span> Stale vocabulary</div>
  <div class="legend-item"><span class="legend-dot" style="background:#e67e22"></span> Monotony / burstiness</div>
  <div class="legend-item"><span class="legend-dot" style="background:#f39c12"></span> Hedging</div>
  <div class="legend-item"><span class="legend-dot" style="background:#3498db"></span> Low specificity</div>
</div>
<div class="signal-scores" id="signal-scores"></div>
<div class="panels">
  <div class="panel panel-left" id="clean-view"></div>
  <div class="panel panel-right" id="flagged-view"></div>
</div>
<script>
const SIGNAL_COLORS = {
  vocabulary: '#e74c3c', burstiness: '#e67e22', monotony: '#e67e22',
  hedging: '#f39c12', specificity: '#3498db'
};
let DATA = null;

async function loadData() {
  const resp = await fetch('/api/data');
  DATA = await resp.json();
  render();
}

function mdToHtml(md) {
  if (!md) return '';
  return md
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" style="color:#3498db">$1</a>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>')
    .split(/\n\s*\n/)
    .filter(p => p.trim())
    .map(p => p.startsWith('<h') || p.startsWith('<ul') ? p : `<p>${p.trim()}</p>`)
    .join('\n');
}

function renderScoreBadge() {
  const el = document.getElementById('score-badge');
  const s = DATA.overall_score;
  const pct = Math.round((1 - s) * 100);
  let cls, label;
  if (s < 0.3) { cls = 'score-strong'; label = 'STRONG'; }
  else if (s < 0.6) { cls = 'score-needs-work'; label = 'NEEDS WORK'; }
  else { cls = 'score-weak'; label = 'WEAK'; }
  el.className = 'score-badge ' + cls;
  el.textContent = `${pct}/100 — ${label}`;
}

function renderSignalScores() {
  const el = document.getElementById('signal-scores');
  el.innerHTML = Object.entries(DATA.signal_scores).map(([k, v]) => {
    const pct = Math.round((1 - v) * 100);
    const color = SIGNAL_COLORS[k] || '#888';
    return `<div class="signal-score"><span>${k}</span><div class="signal-bar"><div class="signal-fill" style="width:${pct}%;background:${color}"></div></div><span>${pct}%</span></div>`;
  }).join('');
}

function renderCleanView() {
  document.getElementById('clean-view').innerHTML = mdToHtml(DATA.text);
}

function applyFlags(text, flags) {
  const sorted = [...flags].sort((a, b) => b.start - a.start);
  let html = text.replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const offsets = [];
  for (const f of sorted) {
    const before = html.slice(0, f.start);
    const span = html.slice(f.start, f.end);
    const after = html.slice(f.end);
    const cls = `flag flag-${f.signal}`;
    const tip = `<div class="tooltip"><div class="signal-label" style="color:${SIGNAL_COLORS[f.signal]}">${f.signal}</div>${f.annotation}${f.suggestion ? `<div class="suggestion">${f.suggestion}</div>` : ''}</div>`;
    html = before + `<span class="${cls}" contenteditable="true">${span}${tip}</span>` + after;
  }
  return html;
}

function renderFlaggedView() {
  const el = document.getElementById('flagged-view');
  const paras = DATA.text.split(/\n\s*\n/).filter(p => p.trim());
  let offset = 0;
  el.innerHTML = paras.map(para => {
    const start = DATA.text.indexOf(para, offset);
    const end = start + para.length;
    offset = end;
    const paraFlags = DATA.flags.filter(f => f.start >= start && f.end <= end)
      .map(f => ({...f, start: f.start - start, end: f.end - start}));
    const flagged = paraFlags.length > 0;
    const html = applyFlags(para, paraFlags);
    return `<div class="para-block${flagged ? ' flagged' : ''}">${html}</div>`;
  }).join('');
}

function render() {
  renderScoreBadge();
  renderSignalScores();
  renderCleanView();
  renderFlaggedView();
}

function collectText() {
  const blocks = document.querySelectorAll('#flagged-view .para-block');
  return Array.from(blocks).map(b => b.textContent.trim()).join('\n\n');
}

document.getElementById('btn-recheck').addEventListener('click', async () => {
  const text = collectText();
  const resp = await fetch('/api/recheck', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text})
  });
  DATA = await resp.json();
  render();
});

document.getElementById('btn-approve').addEventListener('click', async () => {
  const text = collectText();
  await fetch('/api/approve', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text})
  });
  document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-size:24px;color:#2ecc71">Approved. You can close this tab.</div>';
});

loadData();
</script>
</body>
</html>
```

- [ ] **Step 4: Implement reviewer.py**

`aeo_writer/reviewer.py`:
```python
"""Side-by-side review UI — local HTTP server with detection annotations."""

import json
import os
import re
import socket
import threading
import webbrowser
from dataclasses import asdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from string import Template

from .detector import DetectionResult, analyze


def markdown_to_html(md: str) -> str:
    if not md:
        return ""
    html = md
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
    html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'((?:<li>.*</li>\n?)+)', r'<ul>\1</ul>', html)
    paras = re.split(r'\n\s*\n', html)
    parts = []
    for p in paras:
        p = p.strip()
        if not p:
            continue
        if p.startswith('<h') or p.startswith('<ul'):
            parts.append(p)
        else:
            parts.append(f'<p>{p}</p>')
    return '\n'.join(parts)


def result_to_json(result: DetectionResult) -> str:
    d = asdict(result)
    return json.dumps(d)


def _find_port(start: int = 8787) -> int:
    for port in range(start, start + 100):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    raise RuntimeError("No available port found")


class ReviewServer:
    def __init__(self, result: DetectionResult, mode: str = "detect", open_browser: bool = True):
        self.result = result
        self.mode = mode
        self.open_browser = open_browser
        self.approved_text = None
        self._stop_event = threading.Event()

        self.port = _find_port()
        template_path = os.path.join(os.path.dirname(__file__), "templates", "review.html")
        with open(template_path) as f:
            self._html = f.read()

        server_ref = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/":
                    body = server_ref._html.encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/api/data":
                    body = result_to_json(server_ref.result).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_error(404)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length)) if length else {}

                if self.path == "/api/recheck":
                    new_text = data.get("text", "")
                    server_ref.result = analyze(new_text)
                    body = result_to_json(server_ref.result).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/api/approve":
                    server_ref.approved_text = data.get("text", "")
                    server_ref._stop_event.set()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    body = b'{"ok": true}'
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_error(404)

            def log_message(self, fmt, *args):
                pass

        self._httpd = HTTPServer(('127.0.0.1', self.port), Handler)

    def serve_until_approved(self):
        if self.open_browser:
            webbrowser.open(f"http://127.0.0.1:{self.port}/")
        while not self._stop_event.is_set():
            self._httpd.handle_request()

    def shutdown(self):
        self._stop_event.set()
        self._httpd.server_close()


def start_review(result: DetectionResult, mode: str = "detect", open_browser: bool = True) -> str | None:
    server = ReviewServer(result, mode=mode, open_browser=open_browser)
    print(f"Review UI: http://127.0.0.1:{server.port}/")
    server.serve_until_approved()
    return server.approved_text
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/aeo_writer/test_reviewer.py -v`
Expected: all 8 tests PASS

- [ ] **Step 6: Commit**

```bash
git add aeo_writer/reviewer.py aeo_writer/templates/review.html tests/aeo_writer/test_reviewer.py
git commit -m "feat(aeo-writer): side-by-side review UI with color-coded citability annotations"
```

---

### Task 4: Draft Generator — Voice Extraction & Claude API

**Files:**
- Create: `aeo_writer/writer.py`
- Create: `tests/aeo_writer/test_writer.py`

**Interfaces:**
- Consumes: `STALE_TERMS` from `aeo_writer.detector` (Task 1)
- Produces:
  - `extract_voice(url: str) -> dict` — fetches site content, returns voice profile dict
  - `generate_draft(topic: str, voice_profile: dict, keywords: list[str]) -> str` — calls Claude API, returns markdown
  - `_analyze_voice(texts: list[str]) -> dict` — analyzes extracted text into voice profile (testable without network)
  - `_build_system_prompt(voice: dict, keywords: list[str]) -> str` — constructs the system prompt (testable without API)

- [ ] **Step 1: Write failing tests**

`tests/aeo_writer/test_writer.py`:
```python
from aeo_writer.writer import _analyze_voice, _build_system_prompt, VOICE_DEFAULTS
from aeo_writer.detector import STALE_TERMS


SAMPLE_TEXTS = [
    "I tried running Facebook ads last month. The results were terrible. "
    "Here's what I learned after burning through $2,000 in a week.",
    "So I switched to Google Ads instead. Much better targeting, honestly. "
    "My CPA dropped from $45 to $12 in three days.",
    "The trick? Don't trust automated bidding right away. Start manual, "
    "learn what works, then let the algorithm take over.",
]


class TestAnalyzeVoice:
    def test_returns_all_keys(self):
        profile = _analyze_voice(SAMPLE_TEXTS)
        assert "avg_sentence_length" in profile
        assert "sentence_length_variance" in profile
        assert "vocabulary_level" in profile
        assert "uses_first_person" in profile
        assert "uses_questions" in profile
        assert "avg_paragraph_length" in profile
        assert "tone_markers" in profile
        assert "sample_openings" in profile

    def test_detects_first_person(self):
        profile = _analyze_voice(SAMPLE_TEXTS)
        assert profile["uses_first_person"] is True

    def test_detects_questions(self):
        profile = _analyze_voice(SAMPLE_TEXTS)
        assert profile["uses_questions"] is True

    def test_no_first_person(self):
        formal = ["The company reported strong earnings. Revenue exceeded expectations."]
        profile = _analyze_voice(formal)
        assert profile["uses_first_person"] is False

    def test_sentence_length_is_positive(self):
        profile = _analyze_voice(SAMPLE_TEXTS)
        assert profile["avg_sentence_length"] > 0

    def test_empty_input(self):
        profile = _analyze_voice([])
        assert profile == VOICE_DEFAULTS


class TestBuildSystemPrompt:
    def test_contains_voice_directives(self):
        voice = _analyze_voice(SAMPLE_TEXTS)
        prompt = _build_system_prompt(voice, ["facebook ads", "CPA"])
        assert "facebook ads" in prompt.lower() or "CPA" in prompt
        assert "sentence" in prompt.lower()

    def test_contains_stale_terms_warning(self):
        voice = _analyze_voice(SAMPLE_TEXTS)
        prompt = _build_system_prompt(voice, [])
        for term in STALE_TERMS[:5]:
            assert term in prompt

    def test_contains_medium_formatting(self):
        voice = _analyze_voice(SAMPLE_TEXTS)
        prompt = _build_system_prompt(voice, [])
        assert "H2" in prompt or "h2" in prompt

    def test_anti_hedging_instruction(self):
        voice = _analyze_voice(SAMPLE_TEXTS)
        prompt = _build_system_prompt(voice, [])
        assert "hedg" in prompt.lower() or "definitive" in prompt.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/aeo_writer/test_writer.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement writer.py**

`aeo_writer/writer.py`:
```python
"""Draft generator — voice extraction + Claude API content generation."""

import re
from html.parser import HTMLParser
from statistics import mean, stdev
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError

from .detector import STALE_TERMS, split_sentences


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paragraphs = []
        self.links = []
        self._in_p = False
        self._buf = []
        self._tag_stack = []

    def handle_starttag(self, tag, attrs):
        self._tag_stack.append(tag)
        if tag == "p":
            self._in_p = True
            self._buf = []
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag == "p" and self._in_p:
            text = "".join(self._buf).strip()
            if text:
                self.paragraphs.append(text)
            self._in_p = False
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

    def handle_data(self, data):
        if self._in_p:
            self._buf.append(data)


VOICE_DEFAULTS = {
    "avg_sentence_length": 15.0,
    "sentence_length_variance": 0.4,
    "vocabulary_level": "conversational",
    "uses_first_person": True,
    "uses_questions": False,
    "avg_paragraph_length": 3.0,
    "tone_markers": ["neutral"],
    "sample_openings": [],
}


def _analyze_voice(texts: list[str]) -> dict:
    if not texts:
        return dict(VOICE_DEFAULTS)

    all_sentences = []
    para_sent_counts = []
    has_first_person = False
    has_questions = False
    openings = []

    for text in texts:
        sentences = split_sentences(text)
        all_sentences.extend(sentences)
        para_sent_counts.append(len(sentences))
        if sentences:
            openings.append(sentences[0][:60])
        for s in sentences:
            if re.search(r'\bI\b', s):
                has_first_person = True
            if s.strip().endswith("?"):
                has_questions = True

    if not all_sentences:
        return dict(VOICE_DEFAULTS)

    lengths = [len(s.split()) for s in all_sentences]
    avg_len = mean(lengths)
    cv = stdev(lengths) / avg_len if len(lengths) > 1 and avg_len > 0 else 0.4

    if avg_len > 20:
        level = "professional"
    elif avg_len > 12:
        level = "conversational"
    else:
        level = "casual"

    markers = []
    full = " ".join(texts).lower()
    if any(c in full for c in ["n't", "'re", "'ve", "'ll", "'m"]):
        markers.append("uses contractions")
    if has_first_person:
        markers.append("first person")
    if has_questions:
        markers.append("uses questions")
    if avg_len < 14:
        markers.append("direct")
    if not markers:
        markers.append("neutral")

    return {
        "avg_sentence_length": round(avg_len, 1),
        "sentence_length_variance": round(cv, 2),
        "vocabulary_level": level,
        "uses_first_person": has_first_person,
        "uses_questions": has_questions,
        "avg_paragraph_length": round(mean(para_sent_counts), 1) if para_sent_counts else 3.0,
        "tone_markers": markers,
        "sample_openings": openings[:5],
    }


def _build_system_prompt(voice: dict, keywords: list[str]) -> str:
    stale_list = ", ".join(STALE_TERMS)
    kw_section = f"\nTarget keywords to weave in naturally: {', '.join(keywords)}" if keywords else ""

    return f"""You are a blog content writer matching a specific voice and style.

VOICE PROFILE:
- Average sentence length: {voice['avg_sentence_length']} words (vary between 5-30)
- Sentence length variance: HIGH — mix short punchy sentences with longer ones
- Vocabulary level: {voice['vocabulary_level']}
- Uses first person: {"yes — write as 'I'" if voice['uses_first_person'] else "no — write in third person"}
- Uses questions: {"yes — include rhetorical questions" if voice['uses_questions'] else "rarely"}
- Tone: {', '.join(voice['tone_markers'])}

ANTI-STALENESS RULES (CRITICAL — never break these):
1. NEVER use any of these words/phrases: {stale_list}
2. Vary sentence lengths dramatically. Follow a 25-word sentence with a 4-word one. Then a 15-word one.
3. Include specific numbers, dates, proper nouns, or named examples in EVERY section.
4. Make definitive statements. Never hedge with "may", "might", "could potentially", "it's possible".
5. Start each paragraph with a DIFFERENT pattern — a question, a number, a name, a short statement, a quote.
6. Write like you're telling a specific story, not summarizing a topic.

MEDIUM FORMATTING:
- Use ## for main sections, ### for subsections (never # — Medium uses that for title)
- Keep paragraphs to 2-4 sentences max
- Use bold (**text**) for key takeaways
- Include at least one numbered or bulleted list
- Total length: 800-1200 words
{kw_section}

Write the article now. Start with a hook — a specific anecdote, surprising number, or bold claim. No preamble."""


def extract_voice(url: str) -> dict:
    headers = {"User-Agent": "AEO-Writer/1.0 (content analysis)"}
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except (URLError, OSError):
        return dict(VOICE_DEFAULTS)

    extractor = _TextExtractor()
    extractor.feed(html)

    blog_links = [
        urljoin(url, link)
        for link in extractor.links
        if any(p in link for p in ["/blog/", "/posts/", "/articles/", "/news/"])
    ][:3]

    texts = list(extractor.paragraphs)
    for link in blog_links:
        try:
            req = Request(link, headers=headers)
            with urlopen(req, timeout=10) as resp:
                sub_html = resp.read().decode("utf-8", errors="replace")
            sub = _TextExtractor()
            sub.feed(sub_html)
            texts.extend(sub.paragraphs)
        except (URLError, OSError):
            continue

    return _analyze_voice(texts)


def generate_draft(topic: str, voice_profile: dict, keywords: list[str] | None = None) -> str:
    import anthropic

    client = anthropic.Anthropic()
    system = _build_system_prompt(voice_profile, keywords or [])

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        temperature=0.9,
        system=system,
        messages=[{"role": "user", "content": f"Write a blog post about: {topic}"}],
    )

    return message.content[0].text
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/aeo_writer/test_writer.py -v`
Expected: all 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add aeo_writer/writer.py tests/aeo_writer/test_writer.py
git commit -m "feat(aeo-writer): draft generator with voice extraction and Claude API integration"
```

---

### Task 5: Medium Publisher

**Files:**
- Create: `aeo_writer/publisher.py`
- Create: `tests/aeo_writer/test_publisher.py`

**Interfaces:**
- Consumes: nothing from other tasks (standalone HTTP calls)
- Produces:
  - `publish_to_medium(title: str, content: str, tags: list[str], token: str, publish: bool = False, canonical_url: str = None) -> dict` — returns `{"url": "...", "id": "..."}` on success or `{"error": "..."}` on failure
  - `_get_user_id(token: str) -> str` — fetches Medium user ID

- [ ] **Step 1: Write failing tests**

`tests/aeo_writer/test_publisher.py`:
```python
import json
from unittest.mock import patch, MagicMock

from aeo_writer.publisher import publish_to_medium, _build_post_payload, _get_user_id


class TestBuildPostPayload:
    def test_basic_payload(self):
        payload = _build_post_payload("My Title", "# Content", ["tag1", "tag2"], False, None)
        assert payload["title"] == "My Title"
        assert payload["contentFormat"] == "markdown"
        assert payload["content"] == "# Content"
        assert payload["tags"] == ["tag1", "tag2"]
        assert payload["publishStatus"] == "draft"

    def test_public_status(self):
        payload = _build_post_payload("T", "C", [], True, None)
        assert payload["publishStatus"] == "public"

    def test_tags_truncated_to_five(self):
        payload = _build_post_payload("T", "C", ["a", "b", "c", "d", "e", "f", "g"], False, None)
        assert len(payload["tags"]) == 5

    def test_canonical_url_included(self):
        payload = _build_post_payload("T", "C", [], False, "https://example.com/post")
        assert payload["canonicalUrl"] == "https://example.com/post"

    def test_canonical_url_absent_when_none(self):
        payload = _build_post_payload("T", "C", [], False, None)
        assert "canonicalUrl" not in payload


class TestGetUserId:
    @patch("aeo_writer.publisher.urlopen")
    def test_extracts_user_id(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"data": {"id": "user-123"}}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        assert _get_user_id("token-abc") == "user-123"


class TestPublishToMedium:
    @patch("aeo_writer.publisher.urlopen")
    def test_success(self, mock_urlopen):
        me_resp = MagicMock()
        me_resp.read.return_value = json.dumps({"data": {"id": "u1"}}).encode()
        me_resp.__enter__ = lambda s: s
        me_resp.__exit__ = MagicMock(return_value=False)

        post_resp = MagicMock()
        post_resp.read.return_value = json.dumps({
            "data": {"id": "post-1", "url": "https://medium.com/@user/post-1"}
        }).encode()
        post_resp.__enter__ = lambda s: s
        post_resp.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [me_resp, post_resp]
        result = publish_to_medium("Title", "Content", ["ai"], "tok", False)
        assert result["url"] == "https://medium.com/@user/post-1"

    def test_missing_token_returns_error(self):
        result = publish_to_medium("Title", "Content", [], "", False)
        assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/aeo_writer/test_publisher.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement publisher.py**

`aeo_writer/publisher.py`:
```python
"""Medium API publisher — creates draft or public posts."""

import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

_API_BASE = "https://api.medium.com/v1"


def _build_post_payload(
    title: str,
    content: str,
    tags: list[str],
    publish: bool,
    canonical_url: str | None,
) -> dict:
    payload = {
        "title": title,
        "contentFormat": "markdown",
        "content": content,
        "tags": tags[:5],
        "publishStatus": "public" if publish else "draft",
    }
    if canonical_url:
        payload["canonicalUrl"] = canonical_url
    return payload


def _get_user_id(token: str) -> str:
    req = Request(f"{_API_BASE}/me", headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    with urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    return data["data"]["id"]


def publish_to_medium(
    title: str,
    content: str,
    tags: list[str],
    token: str,
    publish: bool = False,
    canonical_url: str | None = None,
) -> dict:
    if not token:
        return {"error": "No Medium token provided. Set MEDIUM_TOKEN environment variable."}

    try:
        user_id = _get_user_id(token)
    except (URLError, HTTPError, KeyError) as e:
        return {"error": f"Failed to authenticate with Medium: {e}"}

    payload = _build_post_payload(title, content, tags, publish, canonical_url)
    body = json.dumps(payload).encode()

    req = Request(
        f"{_API_BASE}/users/{user_id}/posts",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return {
            "url": data["data"]["url"],
            "id": data["data"]["id"],
        }
    except (URLError, HTTPError) as e:
        return {"error": f"Failed to publish: {e}"}
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/aeo_writer/test_publisher.py -v`
Expected: all 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add aeo_writer/publisher.py tests/aeo_writer/test_publisher.py
git commit -m "feat(aeo-writer): Medium API publisher with draft/public modes"
```

---

### Task 6: CLI Orchestrator & Integration

**Files:**
- Create: `aeo_writer/__main__.py`
- Create: `tests/aeo_writer/test_main.py`

**Interfaces:**
- Consumes:
  - `analyze(text: str) -> DetectionResult` from `aeo_writer.detector` (Task 2)
  - `start_review(result, mode, open_browser) -> str | None` from `aeo_writer.reviewer` (Task 3)
  - `extract_voice(url: str) -> dict` from `aeo_writer.writer` (Task 4)
  - `generate_draft(topic, voice, keywords) -> str` from `aeo_writer.writer` (Task 4)
  - `publish_to_medium(title, content, tags, token, publish, canonical_url) -> dict` from `aeo_writer.publisher` (Task 5)
- Produces: CLI entry point (`python3 -m aeo_writer`)

- [ ] **Step 1: Write failing tests**

`tests/aeo_writer/test_main.py`:
```python
import subprocess
import sys
import os
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAMPLE_FILE = os.path.join(PROJECT_ROOT, "tests", "aeo_writer", "_sample_article.md")


def setup_module():
    with open(SAMPLE_FILE, "w") as f:
        f.write(
            "In today's rapidly evolving digital landscape, businesses must leverage "
            "comprehensive strategies. Moreover, it's worth noting that robust approaches "
            "are essential.\n\n"
            "Furthermore, organizations should consider the multifaceted nature of growth. "
            "It's possible that these methodologies could potentially help. To some extent, "
            "the nuanced dynamics may determine outcomes.\n\n"
            "Ultimately, the crucial takeaway is clear. By harnessing cutting-edge tools, "
            "companies can move the needle effectively."
        )


def teardown_module():
    if os.path.exists(SAMPLE_FILE):
        os.remove(SAMPLE_FILE)


def _run(*args):
    return subprocess.run(
        [sys.executable, "-m", "aeo_writer", *args],
        capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=10,
    )


class TestDetectMode:
    def test_detect_file_prints_report(self):
        result = _run("detect", SAMPLE_FILE, "--no-browser")
        assert result.returncode == 0
        assert "CITABILITY REPORT" in result.stdout

    def test_detect_json_output(self):
        result = _run("detect", SAMPLE_FILE, "--no-browser", "--json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "overall_score" in data
        assert "flags" in data

    def test_detect_missing_file(self):
        result = _run("detect", "/nonexistent/file.md", "--no-browser")
        assert result.returncode != 0

    def test_detect_shows_signal_scores(self):
        result = _run("detect", SAMPLE_FILE, "--no-browser")
        assert "burstiness" in result.stdout.lower() or "Burstiness" in result.stdout
        assert "vocabulary" in result.stdout.lower() or "Vocabulary" in result.stdout


class TestWriteMode:
    def test_write_without_api_key_errors(self):
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        result = subprocess.run(
            [sys.executable, "-m", "aeo_writer", "write",
             "--topic", "test", "--target-url", "https://example.com",
             "--no-review", "--output", "/dev/null"],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=10, env=env,
        )
        assert result.returncode != 0
        assert "ANTHROPIC_API_KEY" in result.stderr


class TestHelpText:
    def test_help_shows_both_commands(self):
        result = _run("--help")
        assert "detect" in result.stdout
        assert "write" in result.stdout

    def test_detect_help(self):
        result = _run("detect", "--help")
        assert result.returncode == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/aeo_writer/test_main.py -v`
Expected: FAIL (module has no `__main__`)

- [ ] **Step 3: Implement __main__.py**

`aeo_writer/__main__.py`:
```python
"""AEO Content Agent — CLI entry point."""

import argparse
import json
import os
import sys
from dataclasses import asdict
from urllib.request import Request, urlopen
from urllib.error import URLError

from .detector import analyze
from .reviewer import start_review, result_to_json
from .writer import extract_voice, generate_draft
from .publisher import publish_to_medium


def _read_input(path_or_url: str) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        from html.parser import HTMLParser

        class Strip(HTMLParser):
            def __init__(self):
                super().__init__()
                self.parts = []
                self._skip = {"script", "style"}
                self._stack = []
            def handle_starttag(self, tag, attrs):
                self._stack.append(tag)
            def handle_endtag(self, tag):
                if self._stack and self._stack[-1] == tag:
                    self._stack.pop()
            def handle_data(self, data):
                if not any(t in self._skip for t in self._stack):
                    self.parts.append(data)

        req = Request(path_or_url, headers={"User-Agent": "AEO-Writer/1.0"})
        with urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        s = Strip()
        s.feed(html)
        return "\n\n".join(p.strip() for p in " ".join(s.parts).split("\n\n") if p.strip())

    with open(path_or_url) as f:
        return f.read()


def _format_report(result) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("CITABILITY REPORT")
    lines.append("=" * 60)

    pct = round((1 - result.overall_score) * 100)
    lines.append(f"\nOverall: {pct}/100 — {result.risk_level}")
    lines.append("")

    for signal, score in result.signal_scores.items():
        bar_len = round((1 - score) * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        pct = round((1 - score) * 100)
        lines.append(f"  {signal:<14} {bar}  {pct}%")

    if result.flags:
        lines.append(f"\n{len(result.flags)} issues found:\n")
        seen = set()
        for flag in result.flags:
            key = (flag.signal, flag.start)
            if key in seen:
                continue
            seen.add(key)
            snippet = result.text[flag.start:flag.end][:60]
            if len(result.text[flag.start:flag.end]) > 60:
                snippet += "..."
            lines.append(f"  [{flag.signal.upper()}] \"{snippet}\"")
            lines.append(f"    → {flag.annotation}")
            lines.append("")

    return "\n".join(lines)


def cmd_detect(args):
    try:
        text = _read_input(args.input)
    except (FileNotFoundError, URLError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    result = analyze(text)

    if args.json:
        print(result_to_json(result))
        return

    if args.no_browser:
        print(_format_report(result))
        return

    edited = start_review(result, mode="detect")
    if edited:
        out_path = args.input + ".reviewed.md" if not args.input.startswith("http") else "reviewed.md"
        with open(out_path, "w") as f:
            f.write(edited)
        print(f"\nSaved reviewed text to {out_path}")


def cmd_write(args):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    print(f"Extracting voice from {args.target_url}...")
    voice = extract_voice(args.target_url)

    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else []

    print(f"Generating draft on: {args.topic}...")
    draft = generate_draft(args.topic, voice, keywords)

    slug = args.topic.lower().replace(" ", "-")[:40]
    os.makedirs("drafts", exist_ok=True)
    draft_path = f"drafts/{slug}.md"
    with open(draft_path, "w") as f:
        f.write(draft)
    print(f"Draft saved to {draft_path}")

    result = analyze(draft)
    print(f"\nInitial citability: {round((1 - result.overall_score) * 100)}/100 — {result.risk_level}")
    print(f"Issues found: {len(result.flags)}")

    final_text = draft
    if not args.no_review:
        edited = start_review(result, mode="write")
        if edited:
            final_text = edited
            result2 = analyze(final_text)
            print(f"\nPost-edit citability: {round((1 - result2.overall_score) * 100)}/100 — {result2.risk_level}")

            if result2.overall_score > 0.6:
                print("Warning: content still scores WEAK. Consider another review pass.")

    if args.output:
        with open(args.output, "w") as f:
            f.write(final_text)
        print(f"Final article saved to {args.output}")
        return

    token = args.medium_token or os.environ.get("MEDIUM_TOKEN", "")
    if token:
        title = final_text.split("\n")[0].lstrip("#").strip() or args.topic
        tags = keywords[:5] if keywords else []
        print(f"\nPublishing to Medium...")
        pub = publish_to_medium(title, final_text, tags, token, args.publish)
        if "url" in pub:
            print(f"Published: {pub['url']}")
        else:
            print(f"Publish failed: {pub['error']}")
            fallback = f"drafts/{slug}-final.md"
            with open(fallback, "w") as f:
                f.write(final_text)
            print(f"Saved to {fallback}")
    else:
        fallback = f"drafts/{slug}-final.md"
        with open(fallback, "w") as f:
            f.write(final_text)
        print(f"\nNo MEDIUM_TOKEN set. Saved final article to {fallback}")
        print("Get a token: https://medium.com/me/settings/security → Integration tokens")


def main():
    parser = argparse.ArgumentParser(
        prog="aeo-writer",
        description="AEO Content Agent — improve your content's citability for AI assistants",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    det = sub.add_parser("detect", help="Run citability audit on existing content")
    det.add_argument("input", help="Path to text/markdown file, or URL")
    det.add_argument("--no-browser", action="store_true", help="Print results to terminal")
    det.add_argument("--json", action="store_true", help="Output as JSON")
    det.set_defaults(func=cmd_detect)

    wr = sub.add_parser("write", help="Generate, review, and publish new content")
    wr.add_argument("--topic", required=True, help="Article topic")
    wr.add_argument("--target-url", required=True, help="Site URL to match voice")
    wr.add_argument("--keywords", default="", help="Comma-separated target keywords")
    wr.add_argument("--medium-token", default="", help="Medium integration token")
    wr.add_argument("--publish", action="store_true", help="Publish as public (default: draft)")
    wr.add_argument("--no-review", action="store_true", help="Skip review UI")
    wr.add_argument("--output", default="", help="Save to file instead of publishing")
    wr.set_defaults(func=cmd_write)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/aeo_writer/test_main.py -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Manual smoke test — detect mode**

Run: `python3 -m aeo_writer detect tests/aeo_writer/_sample_article.md --no-browser`

Expected: prints a citability report with signal scores and flagged issues. The AI-generated sample text should score WEAK or NEEDS_WORK with flags on vocabulary, hedging, and specificity.

- [ ] **Step 6: Commit**

```bash
git add aeo_writer/__main__.py tests/aeo_writer/test_main.py
git commit -m "feat(aeo-writer): CLI orchestrator with detect and write subcommands"
```

---

### Task 7: Rote Play Packaging & Final Integration

**Files:**
- Create: `~/.rote/flows/aeo-writer/main.ts`
- Create: `~/.rote/flows/aeo-writer/deps.toml`
- Create: `~/.rote/flows/aeo-writer/resources/` (copy all Python files)

**Interfaces:**
- Consumes: all modules from Tasks 1-6
- Produces: a publishable Rote Play at `patrickmitchell/aeo-writer`

- [ ] **Step 1: Run full test suite to confirm everything passes**

Run: `pytest tests/ -v`
Expected: all tests pass (both `tests/` for audit and `tests/aeo_writer/` for writer)

- [ ] **Step 2: Create the Rote Play directory and copy resources**

The Rote Play needs all Python files in a flat `resources/` directory with adjusted imports (flat instead of relative). Create a packaging script:

```bash
mkdir -p ~/.rote/flows/aeo-writer/resources/aeo_writer/templates
cp aeo_writer/__init__.py ~/.rote/flows/aeo-writer/resources/aeo_writer/
cp aeo_writer/__main__.py ~/.rote/flows/aeo-writer/resources/aeo_writer/
cp aeo_writer/detector.py ~/.rote/flows/aeo-writer/resources/aeo_writer/
cp aeo_writer/reviewer.py ~/.rote/flows/aeo-writer/resources/aeo_writer/
cp aeo_writer/writer.py ~/.rote/flows/aeo-writer/resources/aeo_writer/
cp aeo_writer/publisher.py ~/.rote/flows/aeo-writer/resources/aeo_writer/
cp aeo_writer/templates/review.html ~/.rote/flows/aeo-writer/resources/aeo_writer/templates/
```

- [ ] **Step 3: Create deps.toml**

`~/.rote/flows/aeo-writer/deps.toml`:
```toml
schema_version = 1

[[tools]]
id = "python3"
command = "python3"
required = true
version_requirement = ">=3.10.0"
```

- [ ] **Step 4: Create main.ts**

`~/.rote/flows/aeo-writer/main.ts`:
```typescript
#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: aeo-writer
 * description: Audit and improve any content's citability for AI assistants — detect mode needs zero API keys
 * provenance:
 *   author: patrickmitchell <patrick@boxfordpartners.com>
 * parameters:
 * - name: command
 *   type: string
 *   required: true
 *   description: '"detect" to audit existing content, "write" to generate new content'
 * - name: input
 *   type: string
 *   required: true
 *   description: File path (detect mode) or article topic (write mode)
 * - name: target_url
 *   type: string
 *   required: false
 *   description: Target site URL to match voice (write mode only)
 * - name: keywords
 *   type: string
 *   required: false
 *   description: Comma-separated target keywords
 * metadata:
 *   version: 1.0.0
 *   rote_version: 0.77.0
 *   status: released
 *   kind: atomic
 *   flow_type: parallel
 *   execution_model: steps_with_presentation
 *   requires_sessions: false
 *   tags:
 *   - aeo
 *   - content
 *   - ai
 *   - writing
 *   - medium
 * steps:
 *   run:
 *     type: process.exec
 *     argv:
 *     - python3
 *     - '-m'
 *     - aeo_writer
 *     - $command
 *     - $input
 *     - '--no-browser'
 *     timeout_ms: 120000
 *     env:
 *       PYTHONPATH: '@resource{.}'
 * ---
 */

const presentationSdk = await import("__ROTE_PRESENTATION_SDK__").catch((cause) => {
  throw new Error(
    "This is a rote steps presentation program. Run it with `rote play run <name>`.",
    { cause },
  );
});
const { FlowOutput, loadPresentationContext, stepName } = presentationSdk;

const out = new FlowOutput();
const ctx = await loadPresentationContext();

const runStep = ctx.step(stepName("run"));

switch (runStep.outcome.status) {
  case "completed":
  case "restored": {
    const body = runStep.outcome.output.body;
    let report = "";
    if (body && typeof body === "object" && "stdout" in body) {
      const stdout = (body as Record<string, unknown>).stdout;
      if (stdout && typeof stdout === "object" && "text" in (stdout as Record<string, unknown>)) {
        report = String((stdout as Record<string, string>).text);
      }
    }
    if (report) {
      out.human(report);
      out.summary(report.split("\n").slice(0, 5).join("\n"));
      out.result({ report, command: ctx.params.command, input: ctx.params.input });
    } else {
      out.human("Completed but produced no output.");
      out.summary("No output");
      out.result({ report: "" });
    }
    break;
  }
  case "failed":
    out.human(`Failed: ${runStep.outcome.output.message}`);
    out.summary("Failed");
    out.result({ error: runStep.outcome.output.message });
    break;
  case "blocked":
    out.human("Blocked.");
    out.summary("Blocked");
    out.result({ error: "blocked" });
    break;
  case "skipped":
    out.human("Skipped.");
    out.summary("Skipped");
    out.result({ error: "skipped" });
    break;
  default:
    throw new Error(
      `unsupported step outcome: ${JSON.stringify(runStep.outcome)}. ` +
        `Re-export the play to regenerate this switch.`,
    );
}
```

- [ ] **Step 5: Test the Play locally**

Run: `rote play run aeo-writer 'command=detect' 'input=tests/aeo_writer/_sample_article.md' --yes`

Expected: Play runs, detection engine scores the sample article, outputs the citability report.

Note: The `_sample_article.md` file is created by the test suite's `setup_module`. If it doesn't exist, create it first:
```bash
python3 -c "
text = '''In today's rapidly evolving digital landscape, businesses must leverage comprehensive strategies. Moreover, it's worth noting that robust approaches are essential.

Furthermore, organizations should consider the multifaceted nature of growth. It's possible that these methodologies could potentially help. To some extent, the nuanced dynamics may determine outcomes.

Ultimately, the crucial takeaway is clear. By harnessing cutting-edge tools, companies can move the needle effectively.'''
with open('tests/aeo_writer/_sample_article.md', 'w') as f:
    f.write(text)
"
```

- [ ] **Step 6: Publish to registry**

Run: `rote play publish aeo-writer`

Expected: publishes as `patrickmitchell/aeo-writer@1.0.0`

- [ ] **Step 7: Commit**

```bash
git add aeo_writer/ tests/aeo_writer/
git commit -m "feat(aeo-writer): complete AEO Content Agent with Rote Play packaging"
```
