"""
config.py — Application configuration loader.

Reads environment variables (populated from .env by python-dotenv).
Validates required values at startup and exposes a Config singleton.
"""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Flask ─────────────────────────────────────────────────────────────────
    FLASK_ENV: str = os.getenv("FLASK_ENV", "development")
    SECRET_KEY: str = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    DEBUG: bool = FLASK_ENV == "development"

    # ── Gemini ────────────────────────────────────────────────────────────────
    GEMINI_API_KEY: str = (os.getenv("GEMINI_API_KEY") or os.getenv("gemini_api") or os.getenv("GEMINI_API") or "").strip()
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    GEMINI_FILE_SEARCH_STORE: str = os.getenv("GEMINI_FILE_SEARCH_STORE", "")

    # ── Sarvam ────────────────────────────────────────────────────────────────
    SARVAM_API_KEY: str = (os.getenv("SARVAM_API_KEY") or os.getenv("sarvam_ai") or os.getenv("SARVAM_AI") or os.getenv("sarvam_api") or "").strip()
    SARVAM_STT_MODEL: str = os.getenv("SARVAM_STT_MODEL", "saaras:v2")
    SARVAM_TTS_MODEL: str = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "instance/jarvis.db")

    # ── Agent limits ──────────────────────────────────────────────────────────
    DEFAULT_LANGUAGE: str = os.getenv("DEFAULT_LANGUAGE", "en-IN")
    MAX_AGENT_STEPS: int = int(os.getenv("MAX_AGENT_STEPS", "8"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "2"))
    REQUEST_TIMEOUT_SECONDS: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
    MAX_AUDIO_SECONDS: int = int(os.getenv("MAX_AUDIO_SECONDS", "30"))
    MAX_AUDIO_UPLOAD_MB: int = int(os.getenv("MAX_AUDIO_UPLOAD_MB", "10"))
    MAX_CONCURRENT_RUNS: int = int(os.getenv("MAX_CONCURRENT_RUNS", "2"))

    @classmethod
    def integration_status(cls) -> dict:
        """Return safe integration status (no secrets)."""
        return {
            "gemini": bool(cls.GEMINI_API_KEY),
            "sarvam": bool(cls.SARVAM_API_KEY),
            "gemini_model": cls.GEMINI_MODEL,
            "sarvam_stt_model": cls.SARVAM_STT_MODEL,
            "sarvam_tts_model": cls.SARVAM_TTS_MODEL,
            "file_search_store_configured": bool(cls.GEMINI_FILE_SEARCH_STORE),
            "default_language": cls.DEFAULT_LANGUAGE,
        }

    @classmethod
    def ensure_instance_dir(cls) -> None:
        """Create the instance directory if it does not exist."""
        db_path = Path(cls.DATABASE_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)


config = Config()
