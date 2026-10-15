"""
ai/language_manager.py — Language configuration and capability matrix.

Add new languages by extending LANGUAGE_CONFIG. All other code reads
from this config; no language-specific conditionals elsewhere.
"""
from __future__ import annotations

from typing import Optional

# ── Language configuration ─────────────────────────────────────────────────────
# Each entry maps a locale code to display name and capability flags.
LANGUAGE_CONFIG: dict[str, dict] = {
    "en-IN": {
        "display_name": "English",
        "locale": "en-IN",
        "stt_available": True,
        "tts_available": True,
        "tts_speaker": "priya",      # Sarvam Bulbul v3 English speaker
        "translation_available": True,
        "gemini_native": True,
    },
    "kn-IN": {
        "display_name": "Kannada",
        "locale": "kn-IN",
        "stt_available": True,
        "tts_available": True,
        "tts_speaker": "kavya",      # Sarvam Bulbul v3 Kannada speaker
        "translation_available": True,
        "gemini_native": True,
    },
    "hi-IN": {
        "display_name": "Hindi",
        "locale": "hi-IN",
        "stt_available": True,
        "tts_available": True,
        "tts_speaker": "aditya",     # Sarvam Bulbul v3 Hindi speaker
        "translation_available": True,
        "gemini_native": True,
    },
    "ta-IN": {
        "display_name": "Tamil",
        "locale": "ta-IN",
        "stt_available": True,
        "tts_available": True,
        "tts_speaker": "gokul",      # Sarvam Bulbul v3 Tamil speaker
        "translation_available": True,
        "gemini_native": True,
    },
    "te-IN": {
        "display_name": "Telugu",
        "locale": "te-IN",
        "stt_available": True,
        "tts_available": True,
        "tts_speaker": "kavitha",    # Sarvam Bulbul v3 Telugu speaker
        "translation_available": True,
        "gemini_native": True,
    },
}

DEFAULT_LANGUAGE = "en-IN"


def get_language(locale: str) -> Optional[dict]:
    return LANGUAGE_CONFIG.get(locale)


def is_stt_supported(locale: str) -> bool:
    lang = LANGUAGE_CONFIG.get(locale)
    return bool(lang and lang["stt_available"])


def is_tts_supported(locale: str) -> bool:
    lang = LANGUAGE_CONFIG.get(locale)
    return bool(lang and lang["tts_available"])


def get_tts_speaker(locale: str) -> Optional[str]:
    lang = LANGUAGE_CONFIG.get(locale)
    return lang["tts_speaker"] if lang else None


def resolve_language(locale: str) -> str:
    """Return locale if supported, else fall back to default."""
    return locale if locale in LANGUAGE_CONFIG else DEFAULT_LANGUAGE


def all_languages() -> list[dict]:
    return [
        {"locale": k, **v}
        for k, v in LANGUAGE_CONFIG.items()
    ]


def language_instruction(response_language: str) -> str:
    """
    Return a system instruction telling Gemini which language to use
    for user-facing text in the response.
    """
    lang = LANGUAGE_CONFIG.get(response_language, LANGUAGE_CONFIG[DEFAULT_LANGUAGE])
    name = lang["display_name"]
    return (
        f"The user prefers responses in {name} ({response_language}). "
        f"Generate all user-facing text, plans, step titles, and summaries in {name}. "
        "Keep technical identifiers, tool names, status values, JSON keys, "
        "and API field names in English."
    )
