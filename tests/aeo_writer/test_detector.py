from aeo_writer.detector import (
    FlaggedSpan, DetectionResult,
    split_sentences, split_paragraphs,
    STALE_TERMS, _score_burstiness, _score_vocabulary,
    HEDGE_PHRASES, SIGNAL_WEIGHTS,
    _score_hedging, _score_monotony, _score_specificity,
    analyze,
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
        flagged_text = {text[f.start:f.end].lower() for f in flags}
        assert "it's worth noting" in flagged_text
        assert "move the needle" in flagged_text

    def test_ai_text_scores_higher_than_human(self):
        ai_score, _ = _score_vocabulary(AI_GENERATED_TEXT)
        human_score, _ = _score_vocabulary(HUMAN_WRITTEN_TEXT)
        assert ai_score > human_score

    def test_stale_terms_list_has_40_entries(self):
        assert len(STALE_TERMS) == 40


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
        assert score < 0.5

    def test_identical_openers_detected(self):
        text = ("The main idea is very important to understand.\n\n"
                "The main idea extends to many areas.\n\n"
                "The main idea applies everywhere in life.\n\n"
                "The main idea cannot be overstated at all.")
        paragraphs = split_paragraphs(text)
        score, flags = _score_monotony(text, paragraphs)
        assert score > 0.5

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
