"""
EdgeTTSProvider — Microsoft Edge TTS (Tier 0, free, no API key).

Uses the `edge-tts` Python library which reverse-engineers the same neural
TTS engine that Microsoft Edge uses for Read Aloud.

Capabilities:
  - 400+ voices across 100+ languages / locales
  - No API key, no rate limit (beyond connection limits)
  - Natural neural voice quality (comparable to Azure TTS)
  - Output: MP3 (written directly to output_path)

Limitations:
  - Requires an outbound HTTPS connection to speech.platform.bing.com
  - No SSML control beyond rate/pitch (no emotion tags)
  - Voice cloning not supported (raises NotImplementedError)

Voice format: "en-US-ChristopherNeural"
  If the caller passes a short voice name (e.g. "Christopher") or just
  a language code (e.g. "en"), _resolve_voice() picks a sensible default.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from app.services.video.providers.base import TTSProvider, VoiceInfo

log = structlog.get_logger(__name__)

# ── Language → default voice mapping ─────────────────────────────────────────
# Covers the most common languages used on Moodle LMS platforms.
# Keys are BCP-47 primary subtag (lowercase).
_DEFAULT_VOICES: dict[str, str] = {
    "en":  "en-US-ChristopherNeural",
    "hi":  "hi-IN-MadhurNeural",
    "ar":  "ar-SA-HamedNeural",
    "fr":  "fr-FR-HenriNeural",
    "de":  "de-DE-ConradNeural",
    "es":  "es-ES-AlvaroNeural",
    "pt":  "pt-BR-AntonioNeural",
    "zh":  "zh-CN-YunxiNeural",
    "ja":  "ja-JP-KeitaNeural",
    "ko":  "ko-KR-InJoonNeural",
    "ru":  "ru-RU-DmitryNeural",
    "tr":  "tr-TR-AhmetNeural",
    "it":  "it-IT-DiegoNeural",
    "pl":  "pl-PL-MarekNeural",
    "nl":  "nl-NL-MaartenNeural",
    "sv":  "sv-SE-MattiasNeural",
    "da":  "da-DK-JeppeNeural",
    "fi":  "fi-FI-HarriNeural",
    "nb":  "nb-NO-FinnNeural",
    "id":  "id-ID-ArdiNeural",
    "ms":  "ms-MY-OsmanNeural",
    "th":  "th-TH-NiwatNeural",
    "vi":  "vi-VN-NamMinhNeural",
    "uk":  "uk-UA-OstapNeural",
    "cs":  "cs-CZ-AntoninNeural",
    "ro":  "ro-RO-EmilNeural",
    "hu":  "hu-HU-TamasNeural",
    "el":  "el-GR-NestorasNeural",
    "he":  "he-IL-AvriNeural",
    "bn":  "bn-IN-BashkarNeural",
    "ta":  "ta-IN-ValluvarNeural",
    "te":  "te-IN-MohanNeural",
    "ml":  "ml-IN-MidhunNeural",
    "ur":  "ur-PK-AsadNeural",
    "sw":  "sw-KE-RafikiNeural",
}

# Fallback when language is not in the map
_FALLBACK_VOICE = "en-US-ChristopherNeural"


class EdgeTTSProvider(TTSProvider):
    """
    Microsoft Edge TTS — free, no API key, 400+ neural voices.

    Thread-safety: edge_tts.Communicate is not reentrant; each synthesize()
    call creates a new Communicate instance so concurrent calls are safe.
    """

    def __init__(self) -> None:
        pass  # No credentials needed

    # ── TTSProvider interface ─────────────────────────────────────────────────

    async def synthesize(
        self,
        text: str,
        voice: str,
        language: str,
        output_path: Path,
    ) -> float:
        """
        Synthesize text to MP3 at output_path.

        voice: full EdgeTTS voice ID (e.g. "en-US-ChristopherNeural")
               or short name ("Christopher") or empty string.
               Falls back to language-mapped default if not provided.

        Returns audio duration in seconds (measured from the output file).
        """
        import edge_tts

        resolved_voice = self._resolve_voice(voice, language)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        log.debug(
            "edge_tts_synthesize",
            chars=len(text),
            voice=resolved_voice,
            output=str(output_path),
        )

        communicate = edge_tts.Communicate(text, resolved_voice)
        await communicate.save(str(output_path))

        duration = await self._measure_duration(output_path)
        log.debug("edge_tts_done", duration_sec=round(duration, 2), voice=resolved_voice)
        return duration

    async def list_voices(self, language: str) -> list[VoiceInfo]:
        """
        Return all EdgeTTS voices whose locale starts with the language code.

        e.g. language="en" returns en-US-*, en-GB-*, en-AU-*, etc.
        """
        import edge_tts

        all_voices = await edge_tts.list_voices()
        lang_prefix = language.lower()

        filtered = [
            VoiceInfo(
                voice_id=v["ShortName"],
                name=v.get("FriendlyName", v["ShortName"]),
                language=v.get("Locale", ""),
                gender=v.get("Gender"),
            )
            for v in all_voices
            if v.get("Locale", "").lower().startswith(lang_prefix)
        ]

        if not filtered:
            # Return the default voice for this language as a single entry
            default_id = _DEFAULT_VOICES.get(lang_prefix, _FALLBACK_VOICE)
            filtered = [
                VoiceInfo(
                    voice_id=default_id,
                    name=default_id,
                    language=language,
                )
            ]

        return filtered

    # voice cloning not supported — inherits NotImplementedError from base

    # ── Private helpers ───────────────────────────────────────────────────────

    def _resolve_voice(self, voice: str, language: str) -> str:
        """
        Resolve the best EdgeTTS voice ID from (voice, language).

        Priority:
          1. Full EdgeTTS ID passed in voice  (contains "-" and "Neural")
          2. Language-mapped default
          3. Global fallback
        """
        if voice and "-" in voice and "Neural" in voice:
            return voice   # Already a valid EdgeTTS ShortName

        # voice might be a short hint like "Christopher" — ignore it and
        # pick the language-default for correctness and reliability
        lang_key = language.lower().split("-")[0]  # "en-US" → "en"
        return _DEFAULT_VOICES.get(lang_key, _FALLBACK_VOICE)

    @staticmethod
    async def _measure_duration(audio_path: Path) -> float:
        """
        Measure audio duration in seconds using pydub (async-safe wrapper).

        pydub blocks on file I/O, so we run it in the default executor.
        Falls back to 0.0 if pydub is unavailable or the file is unreadable.
        """
        def _blocking() -> float:
            try:
                from pydub import AudioSegment
                seg = AudioSegment.from_file(str(audio_path))
                return len(seg) / 1000.0
            except Exception as exc:  # noqa: BLE001
                log.warning("edge_tts_duration_measure_failed", error=str(exc))
                return 0.0

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _blocking)
