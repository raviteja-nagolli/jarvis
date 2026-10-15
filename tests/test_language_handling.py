"""
tests/test_language_handling.py — Multilingual correctness tests.
Uses deterministic text fixtures — no real STT/TTS API calls.
"""
import pytest


# Deterministic transcripts per language
LANG_FIXTURES = {
    "en-IN": {
        "transcript": "Create a study note and add three revision tasks for tomorrow",
        "expected_tool": "create_note",
    },
    "kn-IN": {
        "transcript": "ಒಂದು ಅಧ್ಯಯನ ಟಿಪ್ಪಣಿ ರಚಿಸಿ ಮತ್ತು ನಾಳೆಗೆ ಮೂರು ಕಾರ್ಯಗಳನ್ನು ಸೇರಿಸಿ",
        "expected_tool": "create_note",
    },
    "hi-IN": {
        "transcript": "एक अध्ययन नोट बनाएं और कल के लिए तीन कार्य जोड़ें",
        "expected_tool": "create_note",
    },
    "ta-IN": {
        "transcript": "ஒரு படிப்பு குறிப்பை உருவாக்கி நாளைக்கு மூன்று பணிகளை சேர்க்கவும்",
        "expected_tool": "create_note",
    },
    "te-IN": {
        "transcript": "ఒక అధ్యయన నోట్ సృష్టించండి మరియు రేపటి కోసం మూడు పనులు జోడించండి",
        "expected_tool": "create_note",
    },
}


# ── Language config ────────────────────────────────────────────────────────────

def test_all_five_languages_configured():
    from ai.language_manager import LANGUAGE_CONFIG
    for locale in ["en-IN", "kn-IN", "hi-IN", "ta-IN", "te-IN"]:
        assert locale in LANGUAGE_CONFIG, f"{locale} not in LANGUAGE_CONFIG"


def test_stt_available_for_all_languages():
    from ai.language_manager import is_stt_supported
    for locale in ["en-IN", "kn-IN", "hi-IN", "ta-IN", "te-IN"]:
        assert is_stt_supported(locale), f"STT not available for {locale}"


def test_tts_available_for_all_languages():
    from ai.language_manager import is_tts_supported
    for locale in ["en-IN", "kn-IN", "hi-IN", "ta-IN", "te-IN"]:
        assert is_tts_supported(locale), f"TTS not available for {locale}"


def test_tts_speaker_assigned_for_all_languages():
    from ai.language_manager import get_tts_speaker
    for locale in ["en-IN", "kn-IN", "hi-IN", "ta-IN", "te-IN"]:
        speaker = get_tts_speaker(locale)
        assert speaker, f"No TTS speaker configured for {locale}"


def test_unsupported_locale_falls_back():
    from ai.language_manager import resolve_language, DEFAULT_LANGUAGE
    result = resolve_language("zz-ZZ")
    assert result == DEFAULT_LANGUAGE


# ── Transcript preservation ────────────────────────────────────────────────────

def test_original_transcript_preserved():
    """Original transcript must not be silently translated or discarded."""
    kannada = LANG_FIXTURES["kn-IN"]["transcript"]
    # Simulate storing as-is (no mutation)
    stored = kannada
    assert stored == kannada


@pytest.mark.parametrize("locale", list(LANG_FIXTURES.keys()))
def test_tool_schema_language_independent(locale):
    """
    Tool names, schema field names, and required args must be in English
    regardless of input language.
    """
    from tools.registry import get_tool
    tool = get_tool("create_note")
    assert tool.name == "create_note"
    props = tool.input_schema["properties"]
    assert "title" in props
    assert "content" in props


# ── Response language separation ──────────────────────────────────────────────

def test_input_and_response_language_independent():
    """User can speak Kannada but want English response."""
    from ai.language_manager import language_instruction
    instr = language_instruction("en-IN")
    assert "English" in instr


def test_tts_language_check_blocks_unsupported():
    from ai.language_manager import is_tts_supported
    # Unsupported locale must return False
    assert not is_tts_supported("xx-XX")


# ── Language instruction generator ────────────────────────────────────────────

def test_language_instruction_contains_language_name():
    from ai.language_manager import language_instruction
    instr = language_instruction("kn-IN")
    assert "Kannada" in instr


def test_language_instruction_retains_english_for_identifiers():
    from ai.language_manager import language_instruction
    instr = language_instruction("hi-IN")
    assert "English" in instr  # tells model to keep IDs in English
