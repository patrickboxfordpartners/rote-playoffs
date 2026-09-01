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
        flagged_signals = {f.signal for f in flags}
        assert flagged_signals == {"vocabulary"}
        assert len(flags) >= 2

    def test_ai_text_scores_higher_than_human(self):
        ai_score, _ = _score_vocabulary(AI_GENERATED_TEXT)
        human_score, _ = _score_vocabulary(HUMAN_WRITTEN_TEXT)
        assert ai_score > human_score

    def test_stale_terms_list_has_40_entries(self):
        assert len(STALE_TERMS) == 40
