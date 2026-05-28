"""
PeerTube video transcript extractor.

PeerTube is a federated, self-hosted video platform used widely in universities.
Each institution runs its own PeerTube instance on its own domain, so the instance
URL is always derived from the video URL itself — not hardcoded.

Extraction strategy (priority order):
  1. PeerTube API captions — open for public videos; optional Bearer token for private.
     Fetches GET /api/v1/videos/{id}/captions, downloads the best VTT track.
     Fetches GET /api/v1/videos/{id} for metadata (title, duration, description).
  2. yt-dlp subtitle download — works for public PeerTube instances.
     yt-dlp has native PeerTube support; token passed as Authorization header
     so yt-dlp can reach private/restricted videos on the same instance.
  3. yt-dlp audio + Whisper — audio-only download then local transcription.
     Only active if openai-whisper is installed.

PeerTube URL formats supported:
  - https://{instance}/videos/watch/{uuid}          (standard watch URL)
  - https://{instance}/videos/watch/{shortUUID}     (short UUID watch URL)
  - https://{instance}/w/{shortUUID}                (compact share URL)

Because PeerTube is federated, any domain can host an instance.
The instance base URL is always extracted from the video URL.

Passing a PeerTube OAuth token (for private/unlisted videos):
  Include "peertube_token" in the ingest request's metadata field.
  Obtain a token via your instance's OAuth2 client credentials grant:
    POST https://{instance}/api/v1/users/token
      client_id=<your_client_id>
      client_secret=<your_client_secret>
      grant_type=password
      username=<user>
      password=<pass>
      response_type=code
  Then pass the access_token value here.

  POST /api/v1/ingest
  {
    "source_url": "https://openmedia.edunova.it/w/c3LtgepcoRqE2fHMaRoays",
    "content_type": "peertube",
    "metadata": {
      "peertube_token": "YOUR_OAUTH_ACCESS_TOKEN"   // only needed for private videos
    }
  }

  For public videos, omit the token entirely — metadata: {} is sufficient.
"""
import asyncio
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
import structlog

from app.core.exceptions import ContentProcessingError
from app.utils.hashing import sha256_text
from .base import BaseExtractor, ExtractedContent
from .vimeo import _vtt_to_segments  # Re-use shared VTT parser

log = structlog.get_logger(__name__)

# httpx timeouts: generous read timeout for caption file downloads
_API_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=5.0)

# Regex patterns for extracting (instance_base_url, video_id) from PeerTube URLs.
# PeerTube short UUIDs are base58-encoded and typically 22 characters.
# Full UUIDs follow standard UUID format (8-4-4-4-12).
_PEERTUBE_PATTERNS = [
    # /videos/watch/{uuid|shortUUID}
    r"(https?://[^/]+)/videos/watch/([a-zA-Z0-9_-]+)",
    # /w/{shortUUID}  — PeerTube compact share URL (min 15 chars to avoid false positives)
    r"(https?://[^/]+)/w/([a-zA-Z0-9_-]{15,})",
]


def _parse_peertube_info(url: str) -> tuple[str, str] | tuple[None, None]:
    """
    Extract (instance_base_url, video_id) from a PeerTube URL.

    Returns:
        (base_url, video_id) — e.g. ("https://openmedia.edunova.it", "c3LtgepcoRqE2fHMaRoays")
        (None, None)         — if the URL does not match any known PeerTube pattern
    """
    for pattern in _PEERTUBE_PATTERNS:
        m = re.search(pattern, url)
        if m:
            return m.group(1), m.group(2)
    return None, None


class PeerTubeExtractor(BaseExtractor):
    """
    Extracts a transcript from a PeerTube video URL.

    Works with any PeerTube instance — the instance domain is extracted from the URL.

    Returns ExtractedContent where:
      raw_text  — full concatenated transcript text (chunker → embedder)
      segments  — [{start_sec, end_sec, text}] (saved to Transcript table)
      extraction_metadata — video_id, instance_url, duration_sec, caption_source, etc.
    """

    @property
    def supported_content_types(self) -> list[str]:
        return ["peertube"]

    async def extract(
        self,
        *,
        url: str | None = None,
        file_bytes: bytes | None = None,
        content_item_metadata: dict | None = None,
    ) -> ExtractedContent:
        if not url:
            raise ContentProcessingError("PeerTubeExtractor requires a URL")

        meta = content_item_metadata or {}
        language = meta.get("language", "en")
        # Optional OAuth2 Bearer token — only needed for private/unlisted videos.
        # Accept both key names for flexibility.
        peertube_token = (
            meta.get("peertube_token")
            or meta.get("peertube_access_token")
        )

        # Parse instance base URL and video ID from the URL
        instance_url, video_id = _parse_peertube_info(url)

        # Allow per-request override of the instance URL (edge case: reverse proxies)
        if meta.get("peertube_instance_url"):
            instance_url = meta["peertube_instance_url"].rstrip("/")

        if not instance_url or not video_id:
            raise ContentProcessingError(
                f"Cannot parse PeerTube instance URL or video ID from URL: {url}"
            )

        log.info(
            "peertube_extract_start",
            video_id=video_id,
            instance_url=instance_url,
            has_token=bool(peertube_token),
            language=language,
        )

        # ── Strategy 1: PeerTube API ───────────────────────────────────────────
        try:
            segments, all_segs, video_meta = await self._fetch_via_api(
                instance_url=instance_url,
                video_id=video_id,
                language=language,
                token=peertube_token,
            )
            if segments:
                log.info(
                    "peertube_api_success",
                    video_id=video_id,
                    languages=list(all_segs.keys()),
                )
                return self._build_result(
                    video_id=video_id,
                    instance_url=instance_url,
                    segments=segments,
                    all_segments=all_segs,
                    caption_source="api_captions",
                    url=url,
                    video_meta=video_meta,
                )
        except ContentProcessingError:
            raise
        except Exception as e:
            log.warning("peertube_api_failed", video_id=video_id, error=str(e))

        # ── Strategy 2: yt-dlp subtitle download ──────────────────────────────
        try:
            segments, all_segs = await self._fetch_via_ytdlp_subs(
                url=url, language=language, token=peertube_token
            )
            if segments:
                log.info("peertube_ytdlp_subs_success", video_id=video_id)
                return self._build_result(
                    video_id=video_id,
                    instance_url=instance_url,
                    segments=segments,
                    all_segments=all_segs,
                    caption_source="api_captions",
                    url=url,
                )
        except ContentProcessingError:
            raise
        except Exception as e:
            log.warning("peertube_ytdlp_subs_failed", video_id=video_id, error=str(e))

        # ── Strategy 3: yt-dlp audio + Whisper ────────────────────────────────
        try:
            segments, detected_lang = await self._fetch_via_whisper(url=url, token=peertube_token)
            if segments:
                log.info("peertube_whisper_success", video_id=video_id, detected_lang=detected_lang)
                return self._build_result(
                    video_id=video_id,
                    instance_url=instance_url,
                    segments=segments,
                    all_segments={detected_lang: segments},
                    caption_source="whisper_local",
                    url=url,
                    detected_source_language=detected_lang,
                )
        except ContentProcessingError:
            raise
        except Exception as e:
            log.warning("peertube_whisper_failed", video_id=video_id, error=str(e))

        raise ContentProcessingError(
            f"No transcript could be obtained for PeerTube video '{video_id}' "
            f"on instance '{instance_url}'. "
            "The video may have no captions. Install Whisper for audio transcription."
        )

    # ── Private: strategy implementations ──────────────────────────────────────

    async def _fetch_via_api(
        self, instance_url: str, video_id: str, language: str, token: str | None = None
    ) -> tuple[list[dict], dict]:
        """
        Fetch captions from the PeerTube REST API.

        Flow:
          1. GET /api/v1/videos/{id}/captions  →  list available caption tracks
          2. Choose best track (matching language > English > any)
          3. GET {instance}{captionPath}        →  download VTT content
          4. GET /api/v1/videos/{id}            →  fetch video metadata (duration, title)

        Public videos: no auth needed.
        Private/unlisted videos: pass an OAuth2 Bearer token obtained from
          POST /api/v1/users/token on the instance.
        """
        api_base = f"{instance_url}/api/v1"

        # Build headers — add Authorization only when token is provided
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=_API_TIMEOUT, headers=headers) as client:
            # ── Fetch caption tracks list ──────────────────────────────────
            captions_url = f"{api_base}/videos/{video_id}/captions"
            r = await client.get(captions_url)

            if r.status_code == 404:
                raise ContentProcessingError(
                    f"PeerTube video '{video_id}' not found on {instance_url} (404). "
                    f"Check the URL is correct and the video hasn't been deleted."
                )
            if r.status_code == 403:
                raise ContentProcessingError(
                    f"PeerTube video '{video_id}' on {instance_url} is private or "
                    f"restricted (403). Only public videos can be accessed without auth."
                )
            r.raise_for_status()

            captions_data = r.json()
            tracks = captions_data.get("data", [])

            if not tracks:
                log.info("peertube_no_captions", video_id=video_id, instance_url=instance_url)
                return [], {}, {}

            # ── Download ALL caption tracks ────────────────────────────────
            all_segments: dict[str, list[dict]] = {}
            for track in tracks:
                caption_path = track.get("captionPath", "")
                track_lang = track.get("language", {}).get("id", "unknown")
                if not caption_path:
                    continue
                try:
                    caption_url = (
                        caption_path if caption_path.startswith("http")
                        else f"{instance_url}{caption_path}"
                    )
                    vtt_response = await client.get(caption_url)
                    vtt_response.raise_for_status()
                    segs = _vtt_to_segments(vtt_response.text)
                    if segs:
                        all_segments[track_lang] = segs
                except Exception as track_err:
                    log.debug(
                        "peertube_track_download_failed",
                        video_id=video_id,
                        language=track_lang,
                        error=str(track_err),
                    )

            if not all_segments:
                return [], {}, {}

            # ── Select primary track ───────────────────────────────────────
            lang_priority = [language, "en", "en-US", "en-GB"]
            primary_lang = next((l for l in lang_priority if l in all_segments), None)
            if primary_lang is None:
                primary_lang = next(iter(all_segments))
            primary_segments = all_segments[primary_lang]

            # ── Fetch video metadata (best-effort) ────────────────────────
            video_meta: dict = {}
            try:
                vm = await client.get(f"{api_base}/videos/{video_id}")
                if vm.status_code == 200:
                    vd = vm.json()
                    video_meta = {
                        "title": vd.get("name"),
                        "duration_sec": vd.get("duration", 0),
                        "description": vd.get("description"),
                        "channel": vd.get("channel", {}).get("displayName"),
                        "privacy": vd.get("privacy", {}).get("label"),
                        "views": vd.get("views", 0),
                        "likes": vd.get("likes", 0),
                    }
            except Exception as vm_err:
                log.debug("peertube_meta_fetch_failed", error=str(vm_err))

            log.info(
                "peertube_api_fetched",
                video_id=video_id,
                primary_language=primary_lang,
                all_languages=list(all_segments.keys()),
                segments=len(primary_segments),
            )
            return primary_segments, all_segments, video_meta

    async def _fetch_via_ytdlp_subs(
        self, url: str, language: str, token: str | None = None
    ) -> tuple[list[dict], dict[str, list[dict]]]:
        """
        Download ALL available subtitles via yt-dlp.
        Returns primary segments + all language tracks dict.
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
                    "subtitleslangs": ["all"],
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

    async def _fetch_via_whisper(self, url: str, token: str | None = None) -> tuple[list[dict], str]:
        """
        Download audio with yt-dlp and transcribe with local Whisper.
        Whisper auto-detects the audio language.

        Returns:
          segments          — [{start_sec, end_sec, text}]
          detected_language — BCP-47 code detected by Whisper (e.g. "fr", "it")
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
                        "yt-dlp could not download audio from PeerTube. "
                        "The video may require authentication or be unavailable."
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
        instance_url: str,
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
            "peertube_extracted",
            video_id=video_id,
            instance_url=instance_url,
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
                "instance_url": instance_url,
                "url": url,
                "duration_sec": vm.get("duration_sec", duration_sec),
                "segment_count": len(segments),
                "caption_source": caption_source,
                "available_languages": list(all_segments.keys()),
                "title": vm.get("title"),
                "description": vm.get("description"),
                "channel": vm.get("channel"),
                "privacy": vm.get("privacy"),
                "views": vm.get("views"),
                "extractor": "peertube",
            },
        )
