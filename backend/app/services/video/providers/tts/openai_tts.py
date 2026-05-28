"""
OpenAITTSProvider — OpenAI text-to-speech (tts-1 / tts-1-hd).

Uses the official `openai` Python SDK (v1.x async client).

Voice options: alloy  echo  fable  onyx  nova  shimmer
  Mnemonic mapping (approximate gender/tone):
    alloy   — neutral, calm
    echo    — male, warm
    fable   — female, warm British
    onyx    — male, deep authoritative
    nova    — female, energetic
    shimmer — female, soft expressive

Model options:
  tts-1     — low latency (~1 s), slightly less natural (default)
  tts-1-hd  — higher quality, ~3 s latency, double the cost

Configuration:
  api_key : VIDEO_OPENAI_TTS_KEY env  OR  tenant.config.video.api_keys.openai_tts
  model   : tenant.config.video.openai_tts_model  (default: tts-1)

Pricing (May 2026): tts-1 $15/M chars, tts-1-hd $30/M chars.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from app.services.video.providers.base import TTSProvider, VoiceInfo

log = structlog.get_logger(__name__)

# All available OpenAI TTS voices
_VOICES = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}

# Language → best default voice (arbitrary but reasonable)
_LANG_DEFAULT: dict[str, str] = {
    "en": "onyx",
    "es": "nova",
    "fr": "alloy",
    "de": "echo",
    "pt": "nova",
    "hi": "alloy",
    "zh": "alloy",
    "ja": "alloy",
    "ko": "alloy",
    "ar": "echo",
}
_FALLBACK_VOICE = "alloy"

# VoiceInfo entries (language-agnostic — OpenAI voices are multilingual)
_VOICE_INFO = [
    VoiceInfo("alloy",   "Alloy",   "multilingual", gender=None),
    VoiceInfo("echo",    "Echo",    "multilingual", gender="male"),
    VoiceInfo("fable",   "Fable",   "multilingual", gender="female"),
    VoiceInfo("onyx",    "Onyx",    "multilingual", gender="male"),
    VoiceInfo("nova",    "Nova",    "multilingual", gender="female"),
    VoiceInfo("shimmer", "Shimmer", "multilingual", gender="female"),
]


class OpenAITTSProvider(TTSProvider):
    """
    OpenAI TTS — 6 multilingual neural voices, no voice cloning on tts-1.

    output_path will be an MP3 file (OpenAI default output format).
    Duration is measured by reading MP3 header via mutagen (if available)
    or estimated from bitrate; falls back to ffprobe.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "tts-1",
        default_voice: str = "alloy",
    ) -> None:
        if not api_key:
            raise ValueError("OpenAITTSProvider requires a non-empty api_key")
        self._api_key      = api_key
        self._model        = model
        self._default_voice = default_voice if default_voice in _VOICES else "alloy"

    # ── TTSProvider interface ─────────────────────────────────────────────────

    async def synthesize(
        self,
        text: str,
        voice: str,
        language: str,
        output_path: Path,
    ) -> float:
        """
        Synthesize text to MP3 at output_path.  Returns duration in seconds.

        voice: OpenAI voice name (alloy/echo/fable/onyx/nova/shimmer).
               Falls back to language default, then self._default_voice.
        """
        resolved_voice = _resolve_voice(voice, language, self._default_voice)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        log.debug(
            "openai_tts_synthesize",
            voice=resolved_voice,
            model=self._model,
            chars=len(text),
        )

        # Import here to keep startup fast
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._api_key)

        try:
            response = await client.audio.speech.create(
                model=self._model,
                voice=resolved_voice,  # type: ignore[arg-type]
                input=text,
                response_format="mp3",
            )
            output_path.write_bytes(response.content)
        except Exception as exc:
            raise RuntimeError(
                f"OpenAI TTS synthesis failed: {exc}"
            ) from exc

        return _measure_duration(output_path)

    async def list_voices(self, language: str) -> list[VoiceInfo]:
        """
        All 6 OpenAI voices are multilingual — return all regardless of language.
        """
        return list(_VOICE_INFO)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_voice(voice: str | None, language: str, default: str) -> str:
    if voice and voice in _VOICES:
        return voice
    lang_key = (language or "en").split("-")[0].lower()
    return _LANG_DEFAULT.get(lang_key, default)


def _measure_duration(path: Path) -> float:
    """Return audio duration in seconds.  Tries mutagen, then ffprobe, then estimates."""
    try:
        import mutagen.mp3
        audio = mutagen.mp3.MP3(str(path))
        return float(audio.info.length)
    except Exception:
        pass

    try:
        import subprocess, json
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", str(path),
            ],
            timeout=10,
        )
        data = json.loads(out)
        return float(data["format"]["duration"])
    except Exception:
        pass

    # Last resort: estimate from file size at 128 kbps
    size_bytes = path.stat().st_size
    return size_bytes / (128 * 1024 / 8)
