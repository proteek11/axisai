"""
Chapters generator — produces video chapters with seek timestamps.

Priority strategy (same pattern the transcript extractors use):
  1. Native platform chapters API   ← always tried first (free, zero tokens)
       • YouTube  — yt-dlp info dict (chapters set by video creator in description)
       • Vimeo    — GET /videos/{id}/chapters  (requires vimeo_token)
       • PeerTube — GET /api/v1/videos/{id}/chapters  (public for public videos)
  2. AI generation from timed transcript segments
       — only runs when (1) returns nothing
  3. Empty result with explanatory note
       — for non-video content (PDF, page) or video with no captions

Payload stored in AIOutput.payload:
{
  "chapters": [
    {
      "title": "Introduction and Overview",
      "start_sec": 0.0,
      "end_sec": 245.0,
      "summary": "Sets the scene and explains what will be covered."
    },
    ...
  ],
  "chapter_count": 8,
  "total_duration_sec": 3600.0,
  "content_type": "youtube",
  "language": "en",
  "chapters_source": "platform_api"  |  "ai_generated"  |  "none"
}
"""
import asyncio
import re
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx
import structlog

from app.models.output import OutputType
from app.services.ai.prompts.loader import build_messages
from .base import BaseGenerator

if TYPE_CHECKING:
    from app.models.content import ContentItem
    from app.services.ai.client import AIClient

log = structlog.get_logger(__name__)

# httpx timeout for platform chapter API calls
_API_TIMEOUT = httpx.Timeout(connect=8.0, read=20.0, write=5.0, pool=5.0)

# Group transcript segments into blocks of this duration before sending to AI.
BLOCK_DURATION_SEC = 30

# Hard cap on the timed-text string sent to AI (~15 k tokens)
MAX_SEGMENTS_CHARS = 60_000


class ChaptersGenerator(BaseGenerator):
    output_type = OutputType.CHAPTERS
    prompt_name = "chapters"

    async def generate(
        self,
        content_item: "ContentItem",
        full_text: str,
        model: str,
        output_language: str = "en",
        segments: list[dict] | None = None,
    ) -> dict:
        """
        Generate video chapters.

        Priority:
          1. Try native platform chapter API (Vimeo / YouTube / PeerTube).
          2. Fall back to AI generation from timed transcript segments.
          3. Return empty if no segments available (non-video content).

        Args:
            content_item:    ContentItem (used for URL, content_type, stored token)
            full_text:       Full transcript text (unused here but kept for API parity)
            model:           LLM model for AI fallback
            output_language: BCP-47 language code for titles / summaries
            segments:        [{start_sec, end_sec, text}] timed transcript segments

        Returns:
            Payload dict ready to store in AIOutput.payload.
        """
        content_type = str(content_item.content_type)
        total_duration = (
            segments[-1].get("end_sec", 0.0)
            if segments else 0.0
        )

        # ── Step 1: Try native platform chapters API ───────────────────────────
        native_chapters = await self._try_native_chapters(content_item)

        if native_chapters:
            chapters = self._validate_and_fix_chapters(
                native_chapters, total_duration=total_duration, segments=segments
            )
            if chapters:
                log.info(
                    "chapters_from_platform_api",
                    content_item_id=str(content_item.id),
                    content_type=content_type,
                    chapter_count=len(chapters),
                )
                return {
                    "chapters": chapters,
                    "chapter_count": len(chapters),
                    "total_duration_sec": chapters[-1]["end_sec"] if chapters else total_duration,
                    "content_type": content_type,
                    "language": output_language,
                    "chapters_source": "platform_api",
                }

        # ── Step 2: AI generation from transcript segments ─────────────────────
        if not segments:
            log.info(
                "chapters_skipped_no_segments",
                content_item_id=str(content_item.id),
                content_type=content_type,
            )
            return {
                "chapters": [],
                "chapter_count": 0,
                "total_duration_sec": 0.0,
                "content_type": content_type,
                "language": output_language,
                "chapters_source": "none",
                "note": (
                    "Chapters require video content with timed transcript segments. "
                    "This content type does not provide timestamps."
                ),
            }

        timed_text = self._build_timed_text(segments)
        chapter_hint = self._chapter_count_hint(total_duration)

        messages, prompt_config = build_messages(
            self.prompt_name,
            variables={
                "title": content_item.title or "Untitled",
                "content_type": content_type,
                "language": output_language,
                "total_duration_sec": int(total_duration),
                "total_duration_fmt": self._fmt_duration(total_duration),
                "chapter_count_hint": chapter_hint,
                "timed_transcript": timed_text,
            },
        )

        response = await self.ai_client.complete(
            messages=messages,
            model=model,
            task_type="chapters",
            temperature=prompt_config["temperature"],
            max_tokens=prompt_config["max_tokens"],
        )

        response_text = response.choices[0].message.content
        raw_payload = self._parse_json_response(response_text)

        chapters = self._validate_and_fix_chapters(
            raw_payload.get("chapters", []),
            total_duration=total_duration,
            segments=segments,
        )

        payload = {
            "chapters": chapters,
            "chapter_count": len(chapters),
            "total_duration_sec": total_duration,
            "content_type": content_type,
            "language": output_language,
            "chapters_source": "ai_generated",
        }

        log.info(
            "chapters_ai_generated",
            content_item_id=str(content_item.id),
            chapter_count=len(chapters),
            total_duration_sec=total_duration,
        )
        return payload

    # ── Native chapters: router ────────────────────────────────────────────────

    async def _try_native_chapters(self, content_item: "ContentItem") -> list[dict]:
        """
        Route to the correct platform chapter fetcher.
        Returns [] if content type has no chapter API or if the call fails.
        """
        content_type = str(content_item.content_type)
        url = content_item.source_url or ""
        meta = content_item.moodle_metadata or {}

        try:
            if content_type == "vimeo":
                token = meta.get("vimeo_token") or meta.get("vimeo_access_token")
                if token:
                    return await self._fetch_vimeo_chapters(url, token)
                # No token → can't call the authenticated Vimeo chapters API

            elif content_type == "youtube":
                return await self._fetch_youtube_chapters(url)

            elif content_type == "peertube":
                token = meta.get("peertube_token")
                return await self._fetch_peertube_chapters(url, token)

        except Exception as e:
            log.debug(
                "native_chapters_fetch_failed",
                content_type=content_type,
                error=str(e),
            )

        return []

    # ── Native chapters: Vimeo ─────────────────────────────────────────────────

    async def _fetch_vimeo_chapters(self, url: str, token: str) -> list[dict]:
        """
        Fetch chapters from Vimeo's chapters API.

        Endpoint: GET https://api.vimeo.com/videos/{id}/chapters
        Response:
          {
            "data": [
              {"title": "Introduction", "timecode": 0, ...},
              {"title": "Main Topic",   "timecode": 185, ...}
            ],
            "total": 3,
            ...
          }

        timecode is in whole seconds.
        end_sec is derived from the next chapter's timecode (see _validate_and_fix_chapters).
        """
        video_id = _parse_vimeo_id(url)
        if not video_id:
            return []

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.vimeo.*+json;version=3.4",
        }

        async with httpx.AsyncClient(timeout=_API_TIMEOUT, headers=headers) as client:
            r = await client.get(
                f"https://api.vimeo.com/videos/{video_id}/chapters"
            )
            if r.status_code in (401, 403, 404):
                log.debug(
                    "vimeo_chapters_api_denied",
                    video_id=video_id,
                    status=r.status_code,
                )
                return []
            r.raise_for_status()

        data = r.json().get("data", [])
        if not data:
            return []

        chapters = [
            {
                "title": item.get("title", "").strip(),
                "start_sec": float(item.get("timecode", 0)),
                "end_sec": 0.0,   # filled by _validate_and_fix_chapters
            }
            for item in data
            if item.get("title", "").strip()
        ]
        log.info(
            "vimeo_chapters_fetched",
            video_id=video_id,
            count=len(chapters),
        )
        return chapters

    # ── Native chapters: YouTube ───────────────────────────────────────────────

    async def _fetch_youtube_chapters(self, url: str) -> list[dict]:
        """
        Fetch chapters from a YouTube video via yt-dlp (info-only, no download).

        YouTube creators embed chapters in the video description using a pattern like:
          0:00 Introduction
          5:23 Main Topic
          18:45 Conclusion

        yt-dlp parses these automatically and exposes them as info["chapters"]:
          [{"start_time": 0.0, "end_time": 323.0, "title": "Introduction"}, ...]

        This is a fast info-only extract (skip_download=True) — yt-dlp fetches
        the page metadata but does not download any video or audio.
        """
        loop = asyncio.get_running_loop()

        def _sync_fetch():
            try:
                import yt_dlp  # type: ignore
            except ImportError:
                return []

            ydl_opts = {
                "skip_download": True,
                "quiet": True,
                "no_warnings": True,
                "extract_flat": False,  # need full info for chapters
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            raw_chapters = info.get("chapters") or []
            return [
                {
                    "title": ch.get("title", "").strip(),
                    "start_sec": float(ch.get("start_time", 0.0)),
                    "end_sec": float(ch.get("end_time", 0.0)),
                }
                for ch in raw_chapters
                if ch.get("title", "").strip()
            ]

        chapters = await loop.run_in_executor(None, _sync_fetch)
        if chapters:
            log.info("youtube_chapters_fetched", url=url, count=len(chapters))
        return chapters

    # ── Native chapters: PeerTube ──────────────────────────────────────────────

    async def _fetch_peertube_chapters(
        self, url: str, token: str | None
    ) -> list[dict]:
        """
        Fetch chapters from the PeerTube chapters API (available since PeerTube 6.0).

        Endpoint: GET https://{instance}/api/v1/videos/{uuid}/chapters
        Response (PeerTube 6+):
          {
            "chapters": [
              {"timecode": 0,   "title": "Introduction"},
              {"timecode": 185, "title": "Main Topic"},
              ...
            ]
          }

        Public videos require no token.  Private/restricted videos need a Bearer token.
        Older PeerTube instances (<6.0) will return 404 — caught and returns [].
        """
        parsed = _parse_peertube_url(url)
        if not parsed:
            return []

        instance_url, video_id = parsed
        api_url = f"{instance_url}/api/v1/videos/{video_id}/chapters"

        headers: dict = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=_API_TIMEOUT, headers=headers) as client:
            r = await client.get(api_url)
            if r.status_code in (401, 403, 404):
                log.debug(
                    "peertube_chapters_api_unavailable",
                    instance=instance_url,
                    video_id=video_id,
                    status=r.status_code,
                )
                return []
            r.raise_for_status()

        raw = r.json().get("chapters", [])
        if not raw:
            return []

        chapters = [
            {
                "title": ch.get("title", "").strip(),
                "start_sec": float(ch.get("timecode", 0)),
                "end_sec": 0.0,
            }
            for ch in raw
            if ch.get("title", "").strip()
        ]
        log.info(
            "peertube_chapters_fetched",
            instance=instance_url,
            video_id=video_id,
            count=len(chapters),
        )
        return chapters

    # ── Shared helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _validate_and_fix_chapters(
        chapters: list,
        total_duration: float,
        segments: list[dict] | None = None,
    ) -> list[dict]:
        """
        Sanitise chapters from any source (platform API or AI):
        - Remove entries missing a title or with non-numeric start_sec
        - Sort by start_sec
        - Re-derive end_sec from next chapter's start_sec
        - Last chapter's end_sec = total_duration (or last segment end if available)
        """
        valid: list[dict] = []
        for ch in chapters:
            if not isinstance(ch, dict):
                continue
            try:
                start = float(ch.get("start_sec", 0.0))
            except (TypeError, ValueError):
                continue
            title = str(ch.get("title", "")).strip()
            if not title:
                continue
            valid.append({
                "title": title,
                "start_sec": round(start, 2),
                "end_sec": float(ch.get("end_sec", 0.0)),
                "summary": str(ch.get("summary", "")).strip(),
            })

        valid.sort(key=lambda c: c["start_sec"])

        # Determine best total duration
        dur = total_duration
        if not dur and segments:
            dur = segments[-1].get("end_sec", 0.0)

        # Re-derive end_sec from chapter boundaries
        for i, ch in enumerate(valid):
            if i + 1 < len(valid):
                ch["end_sec"] = valid[i + 1]["start_sec"]
            else:
                ch["end_sec"] = round(dur, 2) if dur > 0 else ch["start_sec"]

        return valid

    def _build_timed_text(self, segments: list[dict]) -> str:
        """
        Condense raw transcript segments into 30-second blocks for the AI prompt.
        Format: [MM:SS] block text
        """
        if not segments:
            return ""

        blocks: list[str] = []
        block_start: float | None = None
        block_texts: list[str] = []
        next_flush_at: float = BLOCK_DURATION_SEC

        for seg in segments:
            start = seg.get("start_sec", 0.0)
            text = seg.get("text", "").strip()
            if not text:
                continue

            if block_start is None:
                block_start = start
                next_flush_at = start + BLOCK_DURATION_SEC

            if start >= next_flush_at and block_texts:
                blocks.append(
                    f"[{self._fmt_time(block_start)}] {' '.join(block_texts)}"
                )
                block_start = start
                next_flush_at = start + BLOCK_DURATION_SEC
                block_texts = []

            block_texts.append(text)

        if block_texts and block_start is not None:
            blocks.append(
                f"[{self._fmt_time(block_start)}] {' '.join(block_texts)}"
            )

        timed_text = "\n".join(blocks)
        if len(timed_text) > MAX_SEGMENTS_CHARS:
            timed_text = (
                timed_text[:MAX_SEGMENTS_CHARS]
                + "\n...[transcript truncated for length]"
            )
        return timed_text

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        """Format seconds as MM:SS or H:MM:SS."""
        s = int(seconds)
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        if h > 0:
            return f"{h}:{m:02d}:{sec:02d}"
        return f"{m:02d}:{sec:02d}"

    @staticmethod
    def _fmt_duration(seconds: float) -> str:
        """Human-readable duration, e.g. '1h 23m 45s'."""
        s = int(seconds)
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        parts: list[str] = []
        if h:
            parts.append(f"{h}h")
        if m:
            parts.append(f"{m}m")
        if sec or not parts:
            parts.append(f"{sec}s")
        return " ".join(parts)

    @staticmethod
    def _chapter_count_hint(total_duration: float) -> str:
        """Suggest a chapter count range based on video length."""
        minutes = total_duration / 60
        if minutes < 5:
            return "3–5"
        elif minutes < 15:
            return "4–7"
        elif minutes < 30:
            return "6–10"
        elif minutes < 60:
            return "8–14"
        else:
            return "10–20"


# ── URL parsers (module-level, shared) ────────────────────────────────────────

_VIMEO_PATTERNS = [
    r"player\.vimeo\.com/video/(\d+)",
    r"vimeo\.com/(?:video/)?(\d+)",
]

_PEERTUBE_WATCH_PATTERNS = [
    r"/videos/watch/([a-zA-Z0-9_-]+)",
    r"/w/([a-zA-Z0-9_-]+)",
]


def _parse_vimeo_id(url: str) -> str | None:
    for pattern in _VIMEO_PATTERNS:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def _parse_peertube_url(url: str) -> tuple[str, str] | None:
    """
    Returns (instance_base_url, video_id) or None if URL doesn't match.
    e.g. "https://peertube.example.com/w/abc123" → ("https://peertube.example.com", "abc123")
    """
    parsed = urlparse(url)
    if not parsed.netloc:
        return None
    instance_url = f"{parsed.scheme}://{parsed.netloc}"
    for pattern in _PEERTUBE_WATCH_PATTERNS:
        m = re.search(pattern, parsed.path)
        if m:
            return instance_url, m.group(1)
    return None
