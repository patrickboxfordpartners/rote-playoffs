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
- Use ## (H2) for main sections, ### (H3) for subsections (never # — Medium uses that for title)
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
