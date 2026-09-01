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
    offset = 0

    for para in paragraphs:
        sentences = split_sentences(para)
        if len(sentences) < 2:
            # Still need to advance offset even if we skip this paragraph
            pos = text.find(para, offset)
            if pos != -1:
                offset = pos + len(para)
            continue
        lengths = [len(s.split()) for s in sentences]
        avg = mean(lengths)
        if avg == 0:
            # Still need to advance offset
            pos = text.find(para, offset)
            if pos != -1:
                offset = pos + len(para)
            continue
        cv = stdev(lengths) / avg
        para_cvs.append(cv)

        if cv < 0.3:
            start = text.find(para, offset)
            if start == -1:
                continue
            offset = start + len(para)
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
        else:
            # Advance offset even if cv >= 0.3
            pos = text.find(para, offset)
            if pos != -1:
                offset = pos + len(para)

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
