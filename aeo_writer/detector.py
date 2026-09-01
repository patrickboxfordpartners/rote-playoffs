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
    length_score = max(0.0, min(1.0, (0.185 - length_cv) / 0.15))
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
