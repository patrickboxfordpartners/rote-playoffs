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
