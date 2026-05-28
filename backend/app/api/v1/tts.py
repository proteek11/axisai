"""
Voice AI Tutor — Text-to-Speech endpoint.

Phase 18: Learner speaks → RAG chat answers → this endpoint synthesizes
the response to audio using EdgeTTS (free, 400+ voices, already in stack).

Routes (JWT auth):
  POST /tts/synthesize   — text → MP3 bytes (audio/mpeg)
  GET  /tts/voices       — list available voices for a language
"""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.v1.auth import get_current_user_dep as get_current_user
from app.core.redis import get_redis
from app.services.video.providers.tts.edge_tts import EdgeTTSProvider

log = structlog.get_logger(__name__)
router = APIRouter()

# ── Redis cache: SHA256(text+voice) → MP3 bytes, TTL 1 hour ─────────────────
_TTS_CACHE_TTL = 3600  # seconds


def _cache_key(text: str, voice: str) -> str:
    payload = f"{voice}:{text}"
    return f"tts_cache:{hashlib.sha256(payload.encode()).hexdigest()}"


# ── Schemas ──────────────────────────────────────────────────────────────────

class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice: Optional[str] = Field(None, description="EdgeTTS voice ID e.g. 'en-US-JennyNeural'")
    language: Optional[str] = Field("en", description="BCP-47 language code e.g. 'en', 'hi', 'ar'")


class VoiceInfo(BaseModel):
    voice_id: str
    name: str
    language: str
    gender: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post(
    "/tts/synthesize",
    summary="Synthesize text to MP3 audio (Voice AI Tutor)",
    response_class=Response,
    responses={
        200: {"content": {"audio/mpeg": {}}, "description": "MP3 audio bytes"},
        400: {"description": "Text too long or invalid"},
        500: {"description": "TTS synthesis failed"},
    },
)
async def synthesize_speech(
    req: SynthesizeRequest,
    user=Depends(get_current_user),
):
    """
    Convert text to MP3 audio using EdgeTTS.

    - Checks Redis cache first (TTL 1h) — avoids re-synthesising identical responses
    - Falls back to EdgeTTS synthesis if not cached
    - Returns raw MP3 bytes with Content-Type: audio/mpeg
    """
    voice = req.voice or ""
    language = req.language or "en"

    cache_key = _cache_key(req.text, f"{voice}:{language}")

    # ── Try cache ─────────────────────────────────────────────────────────
    try:
        redis = await get_redis()
        cached = await redis.get(cache_key)
        if cached:
            log.debug("tts_cache_hit", key=cache_key[:20])
            return Response(
                content=cached,
                media_type="audio/mpeg",
                headers={"X-TTS-Cache": "hit"},
            )
    except Exception as e:
        log.warning("tts_cache_read_failed", error=str(e))

    # ── Synthesize ────────────────────────────────────────────────────────
    try:
        provider = EdgeTTSProvider()
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "speech.mp3"
            await provider.synthesize(
                text=req.text,
                voice=voice,
                language=language,
                output_path=output_path,
            )
            mp3_bytes = output_path.read_bytes()

    except Exception as e:
        log.error("tts_synthesis_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TTS synthesis failed: {str(e)}",
        )

    # ── Cache result ──────────────────────────────────────────────────────
    try:
        redis = await get_redis()
        await redis.set(cache_key, mp3_bytes, ex=_TTS_CACHE_TTL)
    except Exception as e:
        log.warning("tts_cache_write_failed", error=str(e))

    log.info("tts_synthesized", chars=len(req.text), voice=voice or "default", lang=language)

    return Response(
        content=mp3_bytes,
        media_type="audio/mpeg",
        headers={"X-TTS-Cache": "miss"},
    )


@router.get(
    "/tts/voices",
    response_model=list[VoiceInfo],
    summary="List available TTS voices for a language",
)
async def list_voices(
    language: str = "en",
    user=Depends(get_current_user),
):
    """
    Return available EdgeTTS voices for the given language code.
    e.g. language=en → all en-US, en-GB, en-AU, en-IN voices.
    """
    try:
        provider = EdgeTTSProvider()
        voices = await provider.list_voices(language)
        return [
            VoiceInfo(
                voice_id=v.voice_id,
                name=v.name,
                language=v.language,
                gender=v.gender,
            )
            for v in voices
        ]
    except Exception as e:
        log.error("tts_list_voices_failed", language=language, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list voices: {str(e)}",
        )
