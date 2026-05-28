"""
ElevenLabsProvider — ElevenLabs premium TTS with voice cloning.

API reference: https://elevenlabs.io/docs/api-reference

Features:
  - Hyper-realistic neural voices
  - 29+ languages via eleven_multilingual_v2 model
  - Voice cloning: upload 1-min audio sample → custom voice_id
  - Fine-grained voice stability / similarity_boost / style controls
  - Streaming support (not used here; full file download for MoviePy compat.)

Configuration:
  api_key        : VIDEO_ELEVENLABS_KEY  OR  tenant.config.video.api_keys.elevenlabs
  default_voice  : tenant.config.video.elevenlabs_default_voice
                   (default: "EXAVITQu4vr4xnSDxMaL" — Rachel, warm female EN)
  model          : "eleven_multilingual_v2" (default) or "eleven_turbo_v2_5"

Pricing (May 2026): ~$0.30/1000 chars on Creator plan; $0.18 on Scale.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import structlog

from app.services.video.providers.base import TTSProvider, VoiceInfo

log = structlog.get_logger(__name__)

_BASE_URL    = "https://api.elevenlabs.io/v1"
_TTS_URL     = _BASE_URL + "/text-to-speech/{voice_id}"
_VOICES_URL  = _BASE_URL + "/voices"
_VOICE_ADD   = _BASE_URL + "/voices/add"

# Default voice: Rachel — warm, versatile female EN voice
_DEFAULT_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"

# Recommended model for multilingual content
_DEFAULT_MODEL = "eleven_multilingual_v2"

# Request timeout — ElevenLabs is generally fast (<5 s for short clips)
_TIMEOUT_SEC = 60.0


class ElevenLabsProvider(TTSProvider):
    """
    ElevenLabs premium TTS.

    output_path is always an MP3 (ElevenLabs default output).
    Voice cloning is supported via clone_voice().
    """

    def __init__(
        self,
        api_key: str,
        default_voice_id: str = _DEFAULT_VOICE_ID,
        model: str = _DEFAULT_MODEL,
    ) -> None:
        if not api_key:
            raise ValueError("ElevenLabsProvider requires a non-empty api_key")
        self._api_key         = api_key
        self._default_voice   = default_voice_id or _DEFAULT_VOICE_ID
        self._model           = model

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

        voice: ElevenLabs voice_id string (21-char hash).
               Falls back to self._default_voice if blank.
        """
        voice_id = voice.strip() if voice and len(voice) > 4 else self._default_voice
        output_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "text": text,
            "model_id": self._model,
            "voice_settings": {
                "stability":        0.50,
                "similarity_boost": 0.75,
                "style":            0.00,
                "use_speaker_boost": True,
            },
        }

        log.debug(
            "elevenlabs_tts_synthesize",
            voice_id=voice_id,
            model=self._model,
            chars=len(text),
        )

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SEC) as client:
                resp = await client.post(
                    _TTS_URL.format(voice_id=voice_id),
                    headers={
                        "xi-api-key":   self._api_key,
                        "Accept":       "audio/mpeg",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                output_path.write_bytes(resp.content)
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"ElevenLabs TTS failed: HTTP {exc.response.status_code} "
                f"— {exc.response.text[:300]}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"ElevenLabs TTS error: {exc}") from exc

        return _measure_duration(output_path)

    async def list_voices(self, language: str) -> list[VoiceInfo]:
        """Fetch all available voices (account voices + ElevenLabs library)."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    _VOICES_URL,
                    headers={"xi-api-key": self._api_key},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            log.warning("elevenlabs_list_voices_failed", error=str(exc))
            return []

        voices = []
        for v in data.get("voices", []):
            labels = v.get("labels", {})
            voices.append(VoiceInfo(
                voice_id=v.get("voice_id", ""),
                name=v.get("name", ""),
                language=labels.get("language", "en"),
                gender=labels.get("gender"),
                preview_url=v.get("preview_url"),
            ))
        return voices

    async def clone_voice(self, audio_sample: Path, name: str) -> str:
        """
        Clone a voice from an audio sample (WAV/MP3, min 1 minute recommended).

        Returns the new voice_id string.
        Raises RuntimeError on API error.
        """
        log.info("elevenlabs_clone_voice", name=name, sample=str(audio_sample))

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                with open(audio_sample, "rb") as f:
                    resp = await client.post(
                        _VOICE_ADD,
                        headers={"xi-api-key": self._api_key},
                        data={
                            "name": name,
                            "description": f"Auto-cloned voice: {name}",
                        },
                        files={"files": (audio_sample.name, f, "audio/mpeg")},
                    )
                    resp.raise_for_status()
                    data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"ElevenLabs voice clone failed: HTTP {exc.response.status_code} "
                f"— {exc.response.text[:300]}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"ElevenLabs voice clone error: {exc}") from exc

        voice_id: str = data.get("voice_id", "")
        if not voice_id:
            raise RuntimeError("ElevenLabs clone_voice returned no voice_id")

        log.info("elevenlabs_voice_cloned", name=name, voice_id=voice_id)
        return voice_id

    async def delete_cloned_voice(self, voice_id: str) -> None:
        """Delete a previously cloned voice (cleanup). Non-fatal on error."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.delete(
                    f"{_BASE_URL}/voices/{voice_id}",
                    headers={"xi-api-key": self._api_key},
                )
            log.info("elevenlabs_voice_deleted", voice_id=voice_id)
        except Exception as exc:
            log.warning("elevenlabs_voice_delete_failed", voice_id=voice_id, error=str(exc))


# ── Duration helper ───────────────────────────────────────────────────────────

def _measure_duration(path: Path) -> float:
    try:
        import mutagen.mp3
        return float(mutagen.mp3.MP3(str(path)).info.length)
    except Exception:
        pass
    try:
        import subprocess, json
        out = subprocess.check_output(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
            timeout=10,
        )
        return float(json.loads(out)["format"]["duration"])
    except Exception:
        pass
    return path.stat().st_size / (128 * 1024 / 8)
