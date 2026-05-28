"""
Vimeo video transcript extractor.

Extraction strategy (priority order):
  1. Vimeo API text tracks — uses the Bearer token if provided.
     Fetches GET /videos/{id}/texttracks, downloads the VTT file for the best
     matching language. Works for private, unlisted, and public videos as long
     as the token has access.
  2. yt-dlp subtitle download — works for public and some unlisted videos.
     No token needed; yt-dlp scrapes the Vimeo player embed page.
  3. yt-dlp audio + Whisper — audio-only download then local transcription.
     Only active if openai-whisper is installed.

Passing the Vimeo token:
  Include "vimeo_token" in the ingest request's metadata field:
    POST /api/v1/ingest
    {
      "source_url": "https://vimeo.com/123456789",
      "content_type": "vimeo",
      "metadata": { "vimeo_token": "your-personal-access-token" }
    }
  The token is stored in ContentItem.moodle_metadata and threaded into
  content_item_metadata when the extractor is called by the pipeline.

Vimeo URL formats supported:
  - https://vimeo.com/VIDEO_ID                         (public)
  - https://vimeo.com/VIDEO_ID/HASH                    (unlisted — hash in URL path)
  - https://player.vimeo.com/video/VIDEO_ID            (embed player)
  - https://player.vimeo.com/video/VIDEO_ID?h=HASH     (embed player, unlisted)
"""
import asyncio
import re
import tempfile
from pathlib import Path

import httpx
import structlog

from app.core.exceptions import ContentProcessingError
from app.utils.hashing import sha256_text
from .base import BaseExtractor, ExtractedContent

log = structlog.get_logger(__name__)

VIMEO_API_BASE = "https://api.vimeo.com"

# httpx timeouts: generous read timeout for downloading caption files
_API_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=5.0)

# Regex for extracting Vimeo video ID
_VIMEO_PATTERNS = [
    r"player\.vimeo\.com/video/(\d+)",   # embed player (check first — more specific)
    r"vimeo\.com/(?:video/)?(\d+)",       # standard + /video/ variant
]

# Showcase/album URL — the numeric part is a showcase ID, not a video ID.
# These cannot be fetched via the single-video API endpoints; we delegate to yt-dlp
# which natively handles Vimeo playlists/showcases.
_SHOWCASE_PATTERN = re.compile(r"vimeo\.com/showcase/(\d+)")


def _parse_vimeo_id(url: str) -> str | None:
    """Extract numeric Vimeo video ID from any supported URL format."""
    for pattern in _VIMEO_PATTERNS:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def _is_showcase_url(url: str) -> bool:
    """Return True if the URL is a Vimeo showcase/album, not a single video."""
    return bool(_SHOWCASE_PATTERN.search(url))


class VimeoExtractor(BaseExtractor):
    """
    Extracts a transcript from a Vimeo video URL.

    Returns ExtractedContent where:
      raw_text  — full concatenated transcript text (chunker → embedder)
      segments  — [{start_sec, end_sec, text}] (saved to Transcript table)
      extraction_metadata — video_id, duration_sec, caption_source, title, etc.
    """

    @property
    def supported_content_types(self) -> list[str]:
        return ["vimeo"]

    async def extract(
        self,
        *,
        url: str | None = None,
        file_bytes: bytes | None = None,
        content_item_metadata: dict | None = None,
    ) -> ExtractedContent:
        if not url:
            raise ContentProcessingError("VimeoExtractor requires a URL")

        meta = content_item_metadata or {}
        language = meta.get("language", "en")
        # Accept both key names for flexibility
        vimeo_token = (
            meta.get("vimeo_token")
            or meta.get("vimeo_access_token")
        )

        # Showcase URLs (vimeo.com/showcase/...) contain multiple videos and use
        # a different numeric ID space — they cannot be fetched via the single-video
        # API endpoints. We skip to yt-dlp which handles showcases as playlists.
        is_showcase = _is_showcase_url(url)

        video_id = _parse_vimeo_id(url)
        if not video_id:
            if is_showcase:
                # Extract showcase ID for logging only
                m = _SHOWCASE_PATTERN.search(url)
                video_id = f"showcase_{m.group(1)}" if m else "showcase_unknown"
            else:
                raise ContentProcessingError(
                    f"Cannot parse Vimeo video ID from URL: {url}"
                )

        log.info(
            "vimeo_extract_start",
            video_id=video_id,
            is_showcase=is_showcase,
            has_token=bool(vimeo_token),
            language=language,
        )

        # ── Strategy 1: Vimeo API (requires token, single video only) ─────────
        if vimeo_token and not is_showcase:
            try:
                segments, all_segs, video_meta = await self._fetch_via_api(
                    video_id=video_id,
                    token=vimeo_token,
                    language=language,
                )
                if segments:
                    log.info(
                        "vimeo_api_success",
                        video_id=video_id,
                        languages=list(all_segs.keys()),
                    )
                    return self._build_result(
                        video_id=video_id,
                        segments=segments,
                        all_segments=all_segs,
                        caption_source="api_captions",
                        url=url,
                        video_meta=video_meta,
                    )
            except ContentProcessingError:
                raise
            except Exception as e:
                log.warning("vimeo_api_failed", video_id=video_id, error=str(e))

        # ── Strategy 2: yt-dlp subtitle download ──────────────────────────────
        try:
            segments, all_segs = await self._fetch_via_ytdlp_subs(
                url=url, language=language, token=vimeo_token
            )
            if segments:
                log.info("vimeo_ytdlp_subs_success", video_id=video_id)
                return self._build_result(
                    video_id=video_id,
                    segments=segments,
                    all_segments=all_segs,
                    caption_source="api_captions",
                    url=url,
                )
        except ContentProcessingError:
            raise
        except Exception as e:
            log.warning("vimeo_ytdlp_subs_failed", video_id=video_id, error=str(e))

        # ── Strategy 3: yt-dlp audio + Whisper ────────────────────────────────
        try:
            segments, detected_lang = await self._fetch_via_whisper(url=url, token=vimeo_token)
            if segments:
                log.info("vimeo_whisper_success", video_id=video_id, detected_lang=detected_lang)
                return self._build_result(
                    video_id=video_id,
                    segments=segments,
                    all_segments={detected_lang: segments},
                    caption_source="whisper_local",
                    url=url,
                    detected_source_language=detected_lang,
                )
        except ContentProcessingError:
            raise
        except Exception as e:
            log.warning("vimeo_whisper_failed", video_id=video_id, error=str(e))

        raise ContentProcessingError(
            f"No transcript could be obtained for Vimeo video '{video_id}'. "
            "The video may have no captions. Provide a Vimeo token or install Whisper."
        )

    # ── Private: strategy implementations ──────────────────────────────────────

    async def _fetch_via_api(
        self, video_id: str, token: str, language: str
    ) -> tuple[list[dict], dict[str, list[dict]], dict]:
        """
        Fetch ALL text tracks from the Vimeo API.

        Flow:
          1. GET /videos/{id}/texttracks  →  list all available tracks
          2. Download EVERY track's VTT file (not just the best one)
          3. Choose primary track (matching language > English > any)
          4. GET /videos/{id}  →  fetch video metadata (duration, title)

        Returns:
          primary_segments — best match for requested language
          all_segments     — every track: {"en": [...], "fr": [...]}
          video_meta       — title, duration, etc.
        """
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.vimeo.*+json;version=3.4",
        }

        async with httpx.AsyncClient(timeout=_API_TIMEOUT, headers=headers) as client:
            # ── Fetch text tracks list ─────────────────────────────────────
            r = await client.get(f"{VIMEO_API_BASE}/videos/{video_id}/texttracks")

            if r.status_code == 401:
                raise ContentProcessingError(
                    f"Vimeo API authentication failed (401). "
                    f"Check that your token is valid and hasn't expired."
                )
            if r.status_code == 403:
                raise ContentProcessingError(
                    f"Vimeo API access denied for video {video_id} (403). "
                    f"The token may lack the required scope, or the video is not accessible."
                )
            if r.status_code == 404:
                raise ContentProcessingError(
                    f"Vimeo video {video_id} not found (404). "
                    f"Check the URL is correct and the video hasn't been deleted."
                )
            r.raise_for_status()

            tracks_data = r.json()
            tracks = tracks_data.get("data", [])

            if not tracks:
                log.info("vimeo_no_texttracks", video_id=video_id)
                return [], {}, {}

            # ── Download ALL tracks ────────────────────────────────────────
            all_segments: dict[str, list[dict]] = {}
            for track in tracks:
                track_link = track.get("link")
                track_lang = track.get("language", "unknown")
                if not track_link:
                    continue
                try:
                    vtt_response = await client.get(track_link)
                    vtt_response.raise_for_status()
                    segs = _vtt_to_segments(vtt_response.text)
                    if segs:
                        all_segments[track_lang] = segs
                except Exception as track_err:
                    log.debug(
                        "vimeo_track_download_failed",
                        video_id=video_id,
                        language=track_lang,
                        error=str(track_err),
                    )

            if not all_segments:
                return [], {}, {}

            # ── Select primary track (best language match) ─────────────────
            lang_priority = [language, "en", "en-US", "en-GB"]
            primary_lang = next((l for l in lang_priority if l in all_segments), None)
            if primary_lang is None:
                primary_lang = next(iter(all_segments))
            primary_segments = all_segments[primary_lang]

            log.info(
                "vimeo_api_fetched",
                video_id=video_id,
                primary_language=primary_lang,
                all_languages=list(all_segments.keys()),
                segments=len(primary_segments),
            )

            # ── Fetch video metadata (best-effort) ────────────────────────
            video_meta: dict = {}
            try:
                vm = await client.get(f"{VIMEO_API_BASE}/videos/{video_id}")
                if vm.status_code == 200:
                    vd = vm.json()
                    video_meta = {
                        "title": vd.get("name"),
                        "duration_sec": vd.get("duration", 0),
                        "description": vd.get("description"),
                        "width": vd.get("width"),
                        "height": vd.get("height"),
                        "privacy": vd.get("privacy", {}).get("view"),
                    }
            except Exception as vm_err:
                log.debug("vimeo_meta_fetch_failed", error=str(vm_err))

            return primary_segments, all_segments, video_meta

    async def _fetch_via_ytdlp_subs(
        self, url: str, language: str, token: str | None
    ) -> tuple[list[dict], dict[str, list[dict]]]:
        """
        Download ALL available subtitles via yt-dlp (no full video download).
        Downloads every available language track, returns primary + all.
        """
        loop = asyncio.get_running_loop()

        def _sync_download():
            try:
                import yt_dlp  # type: ignore
            except ImportError:
                raise ContentProcessingError("yt-dlp is not installed")

            with tempfile.TemporaryDirectory() as tmpdir:
                ydl_opts: dict = {
                    "skip_download": True,
                    "writesubtitles": True,
                    "writeautomaticsub": True,
                    "subtitleslangs": ["all"],   # all available tracks
                    "subtitlesformat": "vtt",
                    "outtmpl": f"{tmpdir}/%(id)s.%(ext)s",
                    "quiet": True,
                    "no_warnings": True,
                }

                if token:
                    ydl_opts["http_headers"] = {"Authorization": f"Bearer {token}"}

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)

                video_id = info.get("id", "video")

                # Parse every .vtt file — filename: {id}.{lang}.vtt
                all_segs: dict[str, list[dict]] = {}
                for vtt_file in Path(tmpdir).glob(f"{video_id}.*.vtt"):
                    parts = vtt_file.stem.split(".")
                    lang_code = parts[-1] if len(parts) >= 2 else "unknown"
                    try:
                        segs = _vtt_to_segments(vtt_file.read_text(encoding="utf-8"))
                        if segs:
                            all_segs[lang_code] = segs
                    except Exception:
                        pass

                return all_segs

        all_segs = await loop.run_in_executor(None, _sync_download)

        lang_priority = [language, "en", "en-US", "en-GB"]
        primary_lang = next((l for l in lang_priority if l in all_segs), None)
        if primary_lang is None and all_segs:
            primary_lang = next(iter(all_segs))
        primary_segments = all_segs.get(primary_lang, []) if primary_lang else []

        return primary_segments, all_segs

    async def _fetch_via_whisper(
        self, url: str, token: str | None
    ) -> tuple[list[dict], str]:
        """
        Download audio with yt-dlp and transcribe with local Whisper.
        Whisper auto-detects the audio language.

        Returns:
          segments          — [{start_sec, end_sec, text}]
          detected_language — BCP-47 language code detected by Whisper (e.g. "fr", "en")
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
                ydl_opts: dict = {
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

                if token:
                    ydl_opts["http_headers"] = {"Authorization": f"Bearer {token}"}

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

                audio_files = (
                    list(Path(tmpdir).glob("*.mp3"))
                    + list(Path(tmpdir).glob("*.m4a"))
                    + list(Path(tmpdir).glob("*.webm"))
                )
                if not audio_files:
                    raise ContentProcessingError(
                        "yt-dlp could not download audio from Vimeo. "
                        "The video may require authentication."
                    )

                from app.config import settings
                whisper_model = getattr(settings, "whisper_model", "base")
                model = whisper.load_model(whisper_model)
                result = model.transcribe(str(audio_files[0]))

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

        return await loop.run_in_executor(None, _sync_transcribe)

    def _build_result(
        self,
        video_id: str,
        segments: list[dict],
        all_segments: dict[str, list[dict]],
        caption_source: str,
        url: str,
        video_meta: dict | None = None,
        detected_source_language: str | None = None,
    ) -> ExtractedContent:
        raw_text = " ".join(
            seg["text"].strip() for seg in segments if seg.get("text", "").strip()
        )
        duration_sec = segments[-1]["end_sec"] if segments else 0.0
        content_hash = sha256_text(raw_text)
        word_count = len(raw_text.split())
        vm = video_meta or {}

        log.info(
            "vimeo_extracted",
            video_id=video_id,
            segments=len(segments),
            words=word_count,
            duration_sec=duration_sec,
            source=caption_source,
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
                "duration_sec": vm.get("duration_sec", duration_sec),
                "segment_count": len(segments),
                "caption_source": caption_source,
                "available_languages": list(all_segments.keys()),
                "title": vm.get("title"),
                "description": vm.get("description"),
                "width": vm.get("width"),
                "height": vm.get("height"),
                "privacy": vm.get("privacy"),
                "extractor": "vimeo",
            },
        )


# ── VTT parser ──────────────────────────────────────────────────────────────

def _vtt_to_segments(vtt_text: str) -> list[dict]:
    """
    Parse a WebVTT (.vtt) subtitle file into our [{start_sec, end_sec, text}] format.

    Handles:
    - Standard VTT timestamps: 00:00:01.000 --> 00:00:04.000
    - Short form:              01.000 --> 04.000
    - Positioning tags after timestamp: 00:00:01.000 --> 00:00:04.000 align:left
    - HTML-like inline tags in text: <b>Hello</b> → stripped to "Hello"
    """
    import re as _re

    segments = []
    lines = vtt_text.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Look for timestamp separator lines
        if "-->" in line:
            try:
                # Strip positioning/alignment cues after the end time
                arrow_part = line.split("-->")
                start_str = arrow_part[0].strip()
                end_str = arrow_part[1].strip().split()[0]  # first token only

                start_sec = _vtt_time_to_sec(start_str)
                end_sec = _vtt_time_to_sec(end_str)

                # Collect text lines until blank line or EOF
                i += 1
                text_parts = []
                while i < len(lines) and lines[i].strip():
                    text_parts.append(lines[i].strip())
                    i += 1

                # Join and strip HTML/VTT inline tags
                raw_text = " ".join(text_parts)
                clean_text = _re.sub(r"<[^>]+>", "", raw_text).strip()

                if clean_text:
                    segments.append({
                        "start_sec": round(start_sec, 2),
                        "end_sec": round(end_sec, 2),
                        "text": clean_text,
                    })
                continue

            except Exception:
                pass  # Skip malformed timestamp lines

        i += 1

    return segments


def _vtt_time_to_sec(time_str: str) -> float:
    """
    Convert VTT timestamp to seconds.
    Supports: HH:MM:SS.mmm and MM:SS.mmm
    """
    parts = time_str.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(parts[0])
