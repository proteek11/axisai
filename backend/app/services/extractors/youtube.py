"""
YouTube video transcript extractor.

Extraction strategy (priority order):
  1. youtube-transcript-api — scrapes YouTube's internal caption API, no API key needed.
     Covers ~90% of videos that have captions (manual or auto-generated).
  2. yt-dlp subtitle download — downloads VTT subtitles for videos with captions.
     Broader coverage than transcript-api for some region-locked or embedded players.
  3. yt-dlp audio + Whisper (local) — downloads audio and transcribes locally.
     Only active if openai-whisper is installed (`pip install 'axis-ai[whisper]'`).

Why not YouTube Data API v3?
  API key required + 10,000 unit/day quota.  youtube-transcript-api covers the vast
  majority of cases without any key. YouTube Data API support can be layered on later.

YouTube URL formats supported:
  - https://www.youtube.com/watch?v=VIDEO_ID
  - https://youtu.be/VIDEO_ID
  - https://youtube.com/embed/VIDEO_ID
  - https://youtube.com/shorts/VIDEO_ID
  - https://www.youtube.com/watch?v=VIDEO_ID&t=30s  (time params are ignored)
"""
import asyncio
import re
import tempfile
from pathlib import Path

import structlog

from app.core.exceptions import ContentProcessingError
from app.utils.hashing import sha256_text
from .base import BaseExtractor, ExtractedContent

log = structlog.get_logger(__name__)

# Regex patterns to extract video ID from all YouTube URL variants
_YT_PATTERNS = [
    r"(?:youtube\.com/watch\?.*?v=)([a-zA-Z0-9_-]{11})",
    r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
    r"(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
    r"(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
]


def _parse_youtube_id(url: str) -> str | None:
    """Extract 11-character YouTube video ID from any supported URL format."""
    for pattern in _YT_PATTERNS:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def _segments_to_text(segments: list[dict]) -> str:
    """Join transcript segments into a single, clean readable text string."""
    parts = [seg["text"].strip() for seg in segments if seg.get("text", "").strip()]
    return " ".join(parts)


class YouTubeExtractor(BaseExtractor):
    """
    Extracts a transcript from a YouTube video URL.

    Returns ExtractedContent where:
      raw_text  — full concatenated transcript text (goes to chunker → embedder)
      segments  — [{start_sec, end_sec, text}] (saved to Transcript table for UI)
      extraction_metadata — video_id, duration_sec, caption_source, segment_count
    """

    @property
    def supported_content_types(self) -> list[str]:
        return ["youtube"]

    async def extract(
        self,
        *,
        url: str | None = None,
        file_bytes: bytes | None = None,
        content_item_metadata: dict | None = None,
    ) -> ExtractedContent:
        if not url:
            raise ContentProcessingError("YouTubeExtractor requires a URL")

        meta = content_item_metadata or {}
        language = meta.get("language", "en")

        video_id = _parse_youtube_id(url)
        if not video_id:
            raise ContentProcessingError(
                f"Cannot parse YouTube video ID from URL: {url}"
            )

        log.info("youtube_extract_start", video_id=video_id, language=language)

        # ── Strategy 1: youtube-transcript-api ────────────────────────────────
        try:
            segments, all_segs, source = await self._fetch_via_transcript_api(video_id, language)
            if segments:
                log.info(
                    "youtube_transcript_api_success",
                    video_id=video_id,
                    languages=list(all_segs.keys()),
                )
                return self._build_result(video_id, segments, all_segs, source, url)
        except ContentProcessingError:
            raise
        except Exception as e:
            log.warning("youtube_transcript_api_failed", video_id=video_id, error=str(e))

        # ── Strategy 2: yt-dlp subtitle download ──────────────────────────────
        try:
            segments, all_segs, source = await self._fetch_via_ytdlp_subs(url, language)
            if segments:
                log.info(
                    "youtube_ytdlp_subs_success",
                    video_id=video_id,
                    languages=list(all_segs.keys()),
                )
                return self._build_result(video_id, segments, all_segs, source, url)
        except ContentProcessingError:
            raise
        except Exception as e:
            log.warning("youtube_ytdlp_subs_failed", video_id=video_id, error=str(e))

        # ── Strategy 3: yt-dlp audio + Whisper ────────────────────────────────
        try:
            segments, source, detected_lang = await self._fetch_via_whisper(url)
            if segments:
                log.info("youtube_whisper_success", video_id=video_id, detected_lang=detected_lang)
                all_segs = {detected_lang: segments}
                return self._build_result(
                    video_id, segments, all_segs, source, url,
                    detected_source_language=detected_lang,
                )
        except ContentProcessingError:
            raise
        except Exception as e:
            log.warning("youtube_whisper_failed", video_id=video_id, error=str(e))

        raise ContentProcessingError(
            f"No transcript could be obtained for YouTube video '{video_id}'. "
            "The video may have captions disabled and Whisper is not installed."
        )

    # ── Private: strategy implementations ──────────────────────────────────────

    async def _fetch_via_transcript_api(
        self, video_id: str, language: str
    ) -> tuple[list[dict], dict[str, list[dict]], str]:
        """
        Use youtube-transcript-api to fetch ALL available captions (no API key needed).

        Returns:
          primary_segments — best match for requested language
          all_segments     — every available language track: {"en": [...], "fr": [...]}
          source           — "api_captions"

        Preference order for primary:
          1. Manually created transcript in the requested language
          2. Auto-generated transcript in the requested language
          3. Manually created English transcript
          4. Auto-generated English transcript
          5. Any available transcript (first in list)
        """
        loop = asyncio.get_running_loop()

        def _sync_fetch():
            from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
            try:
                from youtube_transcript_api._errors import (  # type: ignore
                    TranscriptsDisabled, NoTranscriptFound, VideoUnavailable,
                )
            except ImportError:
                from youtube_transcript_api import (  # type: ignore
                    TranscriptsDisabled, NoTranscriptFound, VideoUnavailable,
                )

            # Support both old (static) and new (instance) API
            try:
                api = YouTubeTranscriptApi()
                transcript_list = api.list(video_id)
            except TypeError:
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            # ── Fetch ALL tracks ───────────────────────────────────────────
            all_raw: dict[str, list] = {}
            for t in transcript_list:
                try:
                    all_raw[t.language_code] = t.fetch()
                except Exception:
                    pass  # Skip any track that fails (e.g. translation-only)

            if not all_raw:
                raise NoTranscriptFound(video_id, [language], transcript_list)

            # ── Pick primary (best match for requested language) ───────────
            lang_priority = [language, "en", "en-US", "en-GB"]
            primary_lang = None
            for try_lang in lang_priority:
                if try_lang in all_raw:
                    primary_lang = try_lang
                    break
            if primary_lang is None:
                primary_lang = next(iter(all_raw))

            return all_raw, primary_lang

        all_raw, primary_lang = await loop.run_in_executor(None, _sync_fetch)

        # Parse each track into our [{start_sec, end_sec, text}] format
        all_segments: dict[str, list[dict]] = {}
        for lang_code, raw_data in all_raw.items():
            segs: list[dict] = []
            for item in raw_data:
                if hasattr(item, "start"):
                    start = float(item.start)
                    duration = float(getattr(item, "duration", 0))
                    text = str(item.text)
                else:
                    start = float(item.get("start", 0))
                    duration = float(item.get("duration", 0))
                    text = str(item.get("text", ""))
                text = text.strip()
                if text:
                    segs.append({
                        "start_sec": round(start, 2),
                        "end_sec": round(start + duration, 2),
                        "text": text,
                    })
            if segs:
                all_segments[lang_code] = segs

        primary_segments = all_segments.get(primary_lang, [])
        return primary_segments, all_segments, "api_captions"

    async def _fetch_via_ytdlp_subs(
        self, url: str, language: str
    ) -> tuple[list[dict], dict[str, list[dict]], str]:
        """
        Download ALL available subtitles with yt-dlp (no video download).
        Downloads every language track available and returns them all.

        Returns:
          primary_segments — best match for requested language
          all_segments     — every downloaded language track: {"en": [...], "fr": [...]}
          source           — "ytdlp"
        """
        loop = asyncio.get_running_loop()

        def _sync_download():
            try:
                import yt_dlp  # type: ignore
            except ImportError:
                raise ContentProcessingError("yt-dlp is not installed")

            import json

            with tempfile.TemporaryDirectory() as tmpdir:
                ydl_opts = {
                    "skip_download": True,
                    "writesubtitles": True,
                    "writeautomaticsub": True,
                    "subtitleslangs": ["all"],   # download every available track
                    "subtitlesformat": "json3",
                    "outtmpl": f"{tmpdir}/%(id)s.%(ext)s",
                    "quiet": True,
                    "no_warnings": True,
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)

                video_id = info.get("id", "video")

                # Parse every downloaded json3 file — filename format: {id}.{lang}.json3
                all_segs: dict[str, list[dict]] = {}
                for sub_file in Path(tmpdir).glob(f"{video_id}.*.json3"):
                    # Extract language code from filename
                    parts = sub_file.stem.split(".")
                    lang_code = parts[-1] if len(parts) >= 2 else "unknown"
                    try:
                        sub_data = json.loads(sub_file.read_text(encoding="utf-8"))
                        segs = _parse_json3_subs(sub_data)
                        if segs:
                            all_segs[lang_code] = segs
                    except Exception:
                        pass

                return all_segs

        all_segs = await loop.run_in_executor(None, _sync_download)

        # Pick primary
        lang_priority = [language, "en", "en-US", "en-GB"]
        primary_lang = next((l for l in lang_priority if l in all_segs), None)
        if primary_lang is None and all_segs:
            primary_lang = next(iter(all_segs))
        primary_segments = all_segs.get(primary_lang, []) if primary_lang else []

        return primary_segments, all_segs, "ytdlp"

    async def _fetch_via_whisper(self, url: str) -> tuple[list[dict], str, str]:
        """
        Download audio with yt-dlp and transcribe with local OpenAI Whisper.
        Whisper auto-detects the audio language — that detection is returned
        as the third element so the pipeline can tag the transcript correctly.

        Returns:
          segments              — [{start_sec, end_sec, text}]
          source                — "whisper_local"
          detected_language     — BCP-47 language code detected by Whisper (e.g. "fr", "en")
        """
        loop = asyncio.get_running_loop()

        def _sync_transcribe():
            try:
                import whisper  # type: ignore
            except ImportError:
                raise ContentProcessingError(
                    "openai-whisper is not installed. "
                    "Install with: pip install 'axis-ai[whisper]'"
                )
            try:
                import yt_dlp  # type: ignore
            except ImportError:
                raise ContentProcessingError("yt-dlp is not installed")

            with tempfile.TemporaryDirectory() as tmpdir:
                ydl_opts = {
                    "format": "bestaudio/best",
                    "outtmpl": f"{tmpdir}/audio.%(ext)s",
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "64",
                    }],
                    "quiet": True,
                    "no_warnings": True,
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

                audio_files = (
                    list(Path(tmpdir).glob("*.mp3"))
                    + list(Path(tmpdir).glob("*.m4a"))
                    + list(Path(tmpdir).glob("*.webm"))
                )
                if not audio_files:
                    raise ContentProcessingError("yt-dlp failed to download audio")

                from app.config import settings
                whisper_model = getattr(settings, "whisper_model", "base")
                model = whisper.load_model(whisper_model)
                result = model.transcribe(str(audio_files[0]))

                # Whisper returns the detected audio language
                detected_lang = result.get("language", "en")

                segments = []
                for seg in result.get("segments", []):
                    text = seg.get("text", "").strip()
                    if text:
                        segments.append({
                            "start_sec": round(float(seg["start"]), 2),
                            "end_sec": round(float(seg["end"]), 2),
                            "text": text,
                        })
                return segments, detected_lang

        segments, detected_lang = await loop.run_in_executor(None, _sync_transcribe)
        return segments, "whisper_local", detected_lang

    def _build_result(
        self,
        video_id: str,
        segments: list[dict],
        all_segments: dict[str, list[dict]],
        caption_source: str,
        url: str,
        detected_source_language: str | None = None,
    ) -> ExtractedContent:
        raw_text = _segments_to_text(segments)
        duration_sec = segments[-1]["end_sec"] if segments else 0.0
        content_hash = sha256_text(raw_text)
        word_count = len(raw_text.split())

        log.info(
            "youtube_extracted",
            video_id=video_id,
            segments=len(segments),
            words=word_count,
            duration_sec=duration_sec,
            source=caption_source,
            languages=list(all_segments.keys()),
        )

        return ExtractedContent(
            raw_text=raw_text,
            content_hash=content_hash,
            page_count=None,
            word_count=word_count,
            segments=segments,
            all_segments=all_segments,
            detected_source_language=detected_source_language,
            extraction_metadata={
                "video_id": video_id,
                "url": url,
                "duration_sec": duration_sec,
                "segment_count": len(segments),
                "caption_source": caption_source,
                "available_languages": list(all_segments.keys()),
                "extractor": "youtube",
            },
        )


# ── json3 subtitle parser ───────────────────────────────────────────────────

def _parse_json3_subs(data: dict) -> list[dict]:
    """
    Parse yt-dlp json3 subtitle format into our [{start_sec, end_sec, text}] format.
    json3 structure: {"events": [{"tStartMs": 0, "dDurationMs": 5000, "segs": [{"utf8": "Hello"}]}]}
    """
    segments = []
    for event in data.get("events", []):
        segs = event.get("segs", [])
        if not segs:
            continue
        start_ms = event.get("tStartMs", 0)
        duration_ms = event.get("dDurationMs", 0)
        text = "".join(s.get("utf8", "") for s in segs).strip()
        # Skip empty lines and newline-only events
        if text and text != "\n":
            segments.append({
                "start_sec": round(start_ms / 1000, 2),
                "end_sec": round((start_ms + duration_ms) / 1000, 2),
                "text": text,
            })
    return segments
