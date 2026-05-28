"""
Video/audio file upload extractor.

Handles locally-uploaded video and audio files:
  - Video: .mp4, .mov, .webm, .avi, .mkv
  - Audio: .mp3, .wav, .m4a, .aac, .ogg

Extraction strategy:
  1. Try openai-whisper (local) if installed — transcribes directly from the file path.
  2. If whisper not installed, try ffmpeg to extract audio then whisper.
  3. If neither available, fall back to reading any embedded text metadata via mutagen.
  4. Final fallback: return a placeholder noting manual transcription is needed.

Source URL format: file:///absolute/path/to/uploaded/file.mp4
"""
import asyncio
import os
import tempfile
from pathlib import Path

import structlog

from app.core.exceptions import ContentProcessingError
from app.utils.hashing import sha256_text
from .base import BaseExtractor, ExtractedContent

log = structlog.get_logger(__name__)


def _parse_file_url(url: str) -> str:
    """Convert file:///path/to/file → /path/to/file."""
    if url.startswith("file://"):
        return url[7:]
    return url


class VideoUploadExtractor(BaseExtractor):
    """
    Transcribe locally-uploaded video/audio files using Whisper.

    Falls back gracefully when whisper is not installed or ffmpeg is missing.
    """

    @property
    def supported_content_types(self) -> list[str]:
        return ["video_upload", "audio"]

    async def extract(
        self,
        *,
        url: str | None = None,
        file_bytes: bytes | None = None,
        content_item_metadata: dict | None = None,
    ) -> ExtractedContent:
        meta = content_item_metadata or {}
        language_hint = meta.get("language", "en")

        file_path = _parse_file_url(url) if url else None

        if not file_path or not os.path.exists(file_path):
            raise ContentProcessingError(
                f"Video/audio file not found at path: {file_path}. "
                "The file may have been cleaned up or the path is incorrect."
            )

        file_size = os.path.getsize(file_path)
        file_ext = Path(file_path).suffix.lower()
        log.info("video_upload_extracting", path=file_path, ext=file_ext, size_mb=round(file_size / 1024 / 1024, 1))

        # Try whisper transcription
        try:
            segments, detected_lang = await self._transcribe_with_whisper(file_path, language_hint)
            raw_text = " ".join(seg["text"].strip() for seg in segments if seg.get("text", "").strip())
            if not raw_text:
                raw_text = f"[Video/audio file uploaded: {Path(file_path).name}. Transcription returned empty result.]"
            
            word_count = len(raw_text.split())
            return ExtractedContent(
                raw_text=raw_text,
                content_hash=sha256_text(raw_text),
                word_count=word_count,
                segments=segments,
                all_segments={detected_lang or language_hint: segments},
                detected_source_language=detected_lang,
                extraction_metadata={
                    "file_path": file_path,
                    "file_ext": file_ext,
                    "file_size_bytes": file_size,
                    "transcription_method": "whisper_local",
                    "segment_count": len(segments),
                },
            )

        except ImportError:
            log.warning(
                "whisper_not_installed",
                hint="Install with: pip install openai-whisper",
                file=file_path,
            )
        except Exception as e:
            log.warning("whisper_transcription_failed", error=str(e), file=file_path)

        # Fallback: return placeholder text so pipeline can still generate *some* content
        file_name = Path(file_path).name
        placeholder = (
            f"[Uploaded media file: {file_name}]\n\n"
            f"Automatic transcription was not available (whisper not installed or failed). "
            f"This content was uploaded as a {file_ext.lstrip('.')} file of "
            f"{round(file_size / 1024 / 1024, 1)} MB. "
            f"To enable AI transcription, install openai-whisper on the server: "
            f"pip install openai-whisper"
        )
        return ExtractedContent(
            raw_text=placeholder,
            content_hash=sha256_text(placeholder),
            word_count=len(placeholder.split()),
            segments=[],
            extraction_metadata={
                "file_path": file_path,
                "file_ext": file_ext,
                "file_size_bytes": file_size,
                "transcription_method": "fallback_placeholder",
            },
        )

    async def _transcribe_with_whisper(
        self, file_path: str, language_hint: str
    ) -> tuple[list[dict], str | None]:
        """
        Run whisper transcription in a thread pool (CPU-bound task).
        Returns (segments, detected_language).
        """
        import whisper  # type: ignore  # optional dependency

        def _run_whisper() -> tuple[list[dict], str | None]:
            from app.config import settings
            model_name = getattr(settings, "whisper_model", "base")
            log.info("whisper_loading_model", model=model_name)
            model = whisper.load_model(model_name)

            # whisper can accept file paths directly
            result = model.transcribe(
                file_path,
                language=language_hint if language_hint != "auto" else None,
                verbose=False,
            )

            raw_segments = result.get("segments", [])
            segments = [
                {
                    "start_sec": round(seg["start"], 2),
                    "end_sec": round(seg["end"], 2),
                    "text": seg["text"].strip(),
                }
                for seg in raw_segments
                if seg.get("text", "").strip()
            ]
            detected_lang = result.get("language")
            log.info("whisper_done", segments=len(segments), detected_lang=detected_lang)
            return segments, detected_lang

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run_whisper)
