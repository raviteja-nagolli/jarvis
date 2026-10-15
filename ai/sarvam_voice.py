"""
ai/sarvam_voice.py — Sarvam AI speech-to-text and text-to-speech adapter.

Uses the sarvamai SDK when available; falls back to the REST API via requests.
Never logs API keys or full audio payloads.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Optional

import requests

from config import config

logger = logging.getLogger(__name__)

_SARVAM_BASE = "https://api.sarvam.ai"
_STT_ENDPOINT = f"{_SARVAM_BASE}/speech-to-text"
_TTS_ENDPOINT = f"{_SARVAM_BASE}/text-to-speech"
_TRANSLATE_ENDPOINT = f"{_SARVAM_BASE}/translate"


class SarvamError(Exception):
    """Normalized Sarvam API error."""
    def __init__(self, message: str, provider_code: Optional[str] = None):
        super().__init__(message)
        self.provider_code = provider_code


def _headers() -> dict:
    return {
        "api-subscription-key": config.SARVAM_API_KEY,
    }


def _check_configured() -> None:
    if not config.SARVAM_API_KEY:
        raise SarvamError("Sarvam API key is not configured. Set SARVAM_API_KEY in .env")


# ── Speech-to-text ─────────────────────────────────────────────────────────────

def transcribe_audio(
    audio_bytes: bytes,
    content_type: str = "audio/webm",
    language_code: str = "unknown",
    model: Optional[str] = None,
) -> dict:
    """
    Send audio bytes to Sarvam STT.
    Returns:
        {
            "transcript": str,
            "language_code": str,
            "request_id": str | None,
            "success": bool,
            "error": str | None,
        }
    """
    _check_configured()

    stt_model = model or config.SARVAM_STT_MODEL

    # Determine file extension from MIME type
    _ext_map = {
        "audio/webm": ("audio.webm", "audio/webm"),
        "audio/wav": ("audio.wav", "audio/wav"),
        "audio/mp4": ("audio.mp4", "audio/mp4"),
        "audio/ogg": ("audio.ogg", "audio/ogg"),
        "audio/mpeg": ("audio.mp3", "audio/mpeg"),
        "audio/mp3": ("audio.mp3", "audio/mpeg"),
    }
    fname, mime = _ext_map.get(content_type.lower().split(";")[0].strip(),
                                ("audio.webm", "audio/webm"))

    payload = {
        "model": stt_model,
        "with_timestamps": "false",
        "with_disfluencies": "false",
    }
    if language_code and language_code != "unknown":
        payload["language_code"] = language_code

    files = {"file": (fname, io.BytesIO(audio_bytes), mime)}

    try:
        resp = requests.post(
            _STT_ENDPOINT,
            headers=_headers(),
            data=payload,
            files=files,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        transcript = data.get("transcript", "")
        return {
            "transcript": transcript,
            "language_code": data.get("language_code", language_code),
            "request_id": resp.headers.get("x-request-id"),
            "success": True,
            "error": None,
        }
    except requests.HTTPError as exc:
        msg = f"Sarvam STT HTTP {exc.response.status_code}"
        try:
            detail = exc.response.json()
            msg = detail.get("message", msg)
        except Exception:
            pass
        logger.error("Sarvam STT error: %s", msg)
        return {"transcript": "", "language_code": language_code,
                "request_id": None, "success": False, "error": msg}
    except requests.RequestException as exc:
        logger.error("Sarvam STT request failed: %s", exc)
        return {"transcript": "", "language_code": language_code,
                "request_id": None, "success": False, "error": str(exc)}


# ── Text-to-speech ─────────────────────────────────────────────────────────────

def synthesize_speech(
    text: str,
    language_code: str = "en-IN",
    speaker: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """
    Send text to Sarvam TTS and return audio bytes.
    Returns:
        {
            "audio_bytes": bytes | None,
            "audio_format": str,   # "wav"
            "success": bool,
            "error": str | None,
        }
    """
    _check_configured()
    from ai.language_manager import get_tts_speaker, is_tts_supported

    if not is_tts_supported(language_code):
        return {
            "audio_bytes": None,
            "audio_format": "wav",
            "success": False,
            "error": f"TTS not supported for language '{language_code}'",
        }

    tts_model = model or config.SARVAM_TTS_MODEL
    tts_speaker = speaker or get_tts_speaker(language_code) or "meera"

    # Sarvam TTS supports up to 500 chars per request; chunk if needed
    MAX_CHARS = 500
    segments = [text[i:i+MAX_CHARS] for i in range(0, len(text), MAX_CHARS)] if text else [""]

    all_audio = []
    for segment in segments:
        payload = {
            "inputs": [segment],
            "target_language_code": language_code,
            "speaker": tts_speaker,
            "model": tts_model,
            "enable_preprocessing": True,
        }
        try:
            resp = requests.post(
                _TTS_ENDPOINT,
                headers={**_headers(), "Content-Type": "application/json"},
                json=payload,
                timeout=config.REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()
            audios = data.get("audios", [])
            if audios:
                audio_b64 = audios[0]
                raw = base64.b64decode(audio_b64)
                all_audio.append(raw)
        except requests.HTTPError as exc:
            msg = f"Sarvam TTS HTTP {exc.response.status_code}"
            try:
                detail = exc.response.json()
                msg = detail.get("message", msg)
            except Exception:
                pass
            logger.error("Sarvam TTS error: %s", msg)
            return {"audio_bytes": None, "audio_format": "wav",
                    "success": False, "error": msg}
        except requests.RequestException as exc:
            logger.error("Sarvam TTS request failed: %s", exc)
            return {"audio_bytes": None, "audio_format": "wav",
                    "success": False, "error": str(exc)}

    combined = b"".join(all_audio)
    return {
        "audio_bytes": combined,
        "audio_format": "wav",
        "success": True,
        "error": None,
    }


# ── Translation (optional fallback) ───────────────────────────────────────────

def translate_text(
    text: str,
    source_language: str,
    target_language: str,
) -> dict:
    """
    Translate text using Sarvam Translate API.
    Returns {"translated_text": str, "success": bool, "error": str|None}.
    """
    _check_configured()
    payload = {
        "input": text,
        "source_language_code": source_language,
        "target_language_code": target_language,
        "speaker_gender": "Male",
        "mode": "formal",
        "enable_preprocessing": False,
    }
    try:
        resp = requests.post(
            _TRANSLATE_ENDPOINT,
            headers={**_headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "translated_text": data.get("translated_text", ""),
            "success": True,
            "error": None,
        }
    except requests.RequestException as exc:
        logger.error("Sarvam translate failed: %s", exc)
        return {"translated_text": text, "success": False, "error": str(exc)}


# ── Capability info ────────────────────────────────────────────────────────────

def get_supported_languages() -> list[dict]:
    """Return the language capability matrix from language_manager."""
    from ai.language_manager import all_languages
    return all_languages()
