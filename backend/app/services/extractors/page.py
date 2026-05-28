"""
MoodlePageExtractor — extracts content from Moodle Page module (mod_page) and
                      generic web page URLs (mod_url pointing to external HTML).

content_type: "html_page"  (ContentType.HTML_PAGE)

Two operating modes:

  Mode A — Moodle Page module (mod_page):
    Moodle PHP plugin sends the full page HTML in metadata["html_content"].
    Strategy:
      1. Read html_content from metadata
      2. Strip HTML → clean plain text
      3. Detect embedded YouTube / Vimeo iframes
      4. For each video: delegate to YouTubeExtractor / VimeoExtractor
      5. Merge page text + video transcripts into one unified raw_text

  Mode B — Generic web URL (mod_url pointing to external HTML):
    No html_content in metadata; only source_url is available.
    Strategy:
      1. Fetch URL with httpx (async, 15 s timeout)
      2. Extract text + iframes from the fetched HTML → same pipeline as Mode A

content_hash = SHA-256 of the raw HTML (stable change detection).

The merged raw_text is treated as one document by the chunker / embedder.
No separate transcript record is created — video transcripts are baked into raw_text.

Ingest payload example (Mode A — Moodle Page):
  {
    "source_url": "https://moodle.example.com/mod/page/view.php?id=123",
    "content_type": "html_page",
    "moodle_cmid": 123,
    "moodle_course_id": 45,
    "title": "Week 3: Forces and Motion",
    "options": {"tasks": ["summary", "quiz"]},
    "metadata": {
      "html_content": "<h2>Forces</h2><p>Newton's laws...</p><iframe src=...></iframe>",
      "vimeo_token": "optional_token_for_private_vimeo_embeds"
    }
  }

Ingest payload example (Mode B — Generic URL):
  {
    "source_url": "https://example.com/article",
    "content_type": "html_page",
    "moodle_cmid": 456,
    "moodle_course_id": 45,
    "title": "Reference Article",
    "options": {"tasks": ["summary"]}
  }
"""
import hashlib
import re

import httpx
import structlog
from bs4 import BeautifulSoup

from app.core.exceptions import ContentProcessingError
from app.services.extractors.base import BaseExtractor, ExtractedContent

log = structlog.get_logger(__name__)

# Patterns to match YouTube video IDs and Vimeo video IDs from any embed URL
_YT_RE = re.compile(
    r"(?:youtube\.com/(?:embed/|watch\?v=|v/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)
_VIMEO_RE = re.compile(
    r"vimeo\.com/(?:video/)?(\d+)"
)


def _canonical_youtube_url(src: str) -> str | None:
    """Return canonical watch URL if src contains a YouTube video ID."""
    m = _YT_RE.search(src)
    return f"https://www.youtube.com/watch?v={m.group(1)}" if m else None


def _canonical_vimeo_url(src: str) -> str | None:
    """Return canonical vimeo.com URL if src contains a Vimeo video ID."""
    m = _VIMEO_RE.search(src)
    return f"https://vimeo.com/{m.group(1)}" if m else None


def _html_to_text(html: str) -> str:
    """
    Strip HTML tags and return clean plain text.

    Removes: <script>, <style>, <noscript> blocks entirely.
    Uses newline separator to preserve heading/paragraph structure.
    Collapses excess whitespace.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    raw = soup.get_text(separator="\n")
    lines = [line.strip() for line in raw.splitlines()]
    non_empty = [ln for ln in lines if ln]
    return "\n\n".join(non_empty)


def _find_embedded_videos(html: str) -> list[dict]:
    """
    Scan HTML for YouTube / Vimeo iframes.

    Returns list of:
        {"platform": "youtube"|"vimeo", "url": "<canonical URL>"}

    Deduplicates by URL so the same video embedded twice is only processed once.
    """
    soup = BeautifulSoup(html, "html.parser")
    videos: list[dict] = []
    seen: set[str] = set()

    for iframe in soup.find_all("iframe"):
        src = iframe.get("src", "").strip()
        if not src:
            continue

        yt_url = _canonical_youtube_url(src)
        if yt_url and yt_url not in seen:
            videos.append({"platform": "youtube", "url": yt_url})
            seen.add(yt_url)
            continue

        vimeo_url = _canonical_vimeo_url(src)
        if vimeo_url and vimeo_url not in seen:
            videos.append({"platform": "vimeo", "url": vimeo_url})
            seen.add(vimeo_url)

    return videos


class MoodlePageExtractor(BaseExtractor):
    """
    Extracts unified content from a Moodle Page module.

    Combines plain page text + transcripts from embedded YouTube/Vimeo
    videos into a single ExtractedContent for downstream chunking and RAG.
    """

    @property
    def supported_content_types(self) -> list[str]:
        return ["html_page"]

    async def extract(
        self,
        *,
        url: str | None = None,
        file_bytes: bytes | None = None,
        content_item_metadata: dict | None = None,
    ) -> ExtractedContent:
        """
        Extract content from a Moodle Page (Mode A) or generic web URL (Mode B).

        Args:
            url:                   Page URL. In Mode A (mod_page) used as reference only.
                                   In Mode B (mod_url) the HTML is fetched from this URL.
            file_bytes:            Not used for page/web content.
            content_item_metadata: In Mode A: must contain 'html_content' (full page HTML).
                                   In Mode B: may be absent; URL is fetched automatically.
                                   May also contain 'language' and 'vimeo_token'.

        Returns:
            ExtractedContent with merged page text + video transcripts.

        Raises:
            ContentProcessingError if no html_content and URL fetch fails.
        """
        metadata = content_item_metadata or {}
        html_content = metadata.get("html_content", "")

        # ── Mode B: no HTML in metadata → fetch the URL ───────────────────
        fetch_mode = False
        if not html_content or not html_content.strip():
            if not url:
                raise ContentProcessingError(
                    "MoodlePageExtractor: no 'html_content' in metadata and no source_url. "
                    "For mod_page content, send html_content in metadata. "
                    "For mod_url external links, ensure source_url is set."
                )
            log.info("page_extractor_url_fetch_mode", url=url)
            html_content = await _fetch_url_html(url)
            fetch_mode = True

        language = metadata.get("language", "en")
        vimeo_token = metadata.get("vimeo_token")

        # content_hash is SHA-256 of the raw HTML — consistent with what
        # ingest.py computes for change detection on subsequent submissions.
        content_hash = hashlib.sha256(html_content.encode("utf-8")).hexdigest()

        # ── Step 1: Plain text from HTML ──────────────────────────────────
        page_text = _html_to_text(html_content)
        log.info(
            "page_text_extracted",
            page_url=url,
            page_text_words=len(page_text.split()),
        )

        # ── Step 2: Detect embedded videos ───────────────────────────────
        embedded_videos = _find_embedded_videos(html_content)
        log.info(
            "page_videos_detected",
            page_url=url,
            embedded_count=len(embedded_videos),
            videos=[v["url"] for v in embedded_videos],
        )

        # ── Step 3: Extract video transcripts ────────────────────────────
        video_sections: list[str] = []
        video_meta: list[dict] = []

        if embedded_videos:
            # Lazy import to avoid circular dependency at module load time
            from app.services.extractors.youtube import YouTubeExtractor
            from app.services.extractors.vimeo import VimeoExtractor

            yt_extractor = YouTubeExtractor()
            vimeo_extractor = VimeoExtractor()

            for video in embedded_videos:
                platform = video["platform"]
                video_url = video["url"]

                try:
                    if platform == "youtube":
                        video_extracted = await yt_extractor.extract(
                            url=video_url,
                            content_item_metadata={"language": language},
                        )
                    else:  # vimeo
                        video_extracted = await vimeo_extractor.extract(
                            url=video_url,
                            content_item_metadata={
                                "language": language,
                                "vimeo_token": vimeo_token,
                            },
                        )

                    # Use video title from extraction metadata if available
                    label = (
                        video_extracted.extraction_metadata.get("title")
                        or video_url
                    )
                    section = (
                        f"[EMBEDDED VIDEO: {label}]\n"
                        f"Source: {platform.title()} | {video_url}\n\n"
                        f"{video_extracted.raw_text}"
                    )
                    video_sections.append(section)
                    video_meta.append({
                        "platform": platform,
                        "url": video_url,
                        "word_count": video_extracted.word_count,
                        "caption_source": video_extracted.extraction_metadata.get(
                            "caption_source", "unknown"
                        ),
                    })
                    log.info(
                        "page_video_extracted",
                        platform=platform,
                        url=video_url,
                        words=video_extracted.word_count,
                    )

                except Exception as exc:
                    # Fail gracefully — a bad video embed shouldn't kill the page
                    log.warning(
                        "page_video_extraction_failed",
                        platform=platform,
                        url=video_url,
                        error=str(exc),
                    )
                    video_meta.append({
                        "platform": platform,
                        "url": video_url,
                        "error": str(exc),
                    })

        # ── Step 4: Merge into one document ──────────────────────────────
        parts: list[str] = []
        if page_text:
            parts.append(f"[PAGE CONTENT]\n\n{page_text}")
        for section in video_sections:
            parts.append(section)

        raw_text = "\n\n---\n\n".join(parts)
        word_count = len(raw_text.split())

        return ExtractedContent(
            raw_text=raw_text,
            content_hash=content_hash,
            page_count=None,
            word_count=word_count,
            segments=[],   # no time-coded segments; transcripts baked into raw_text
            extraction_metadata={
                "extractor": "moodle_page",
                "extraction_mode": "url_fetch" if fetch_mode else "html_content",
                "page_url": url,
                "page_text_words": len(page_text.split()) if page_text else 0,
                "embedded_video_count": len(embedded_videos),
                "videos_extracted": sum(1 for v in video_meta if "error" not in v),
                "embedded_videos": video_meta,
            },
        )


async def _fetch_url_html(url: str, timeout: float = 15.0) -> str:
    """
    Fetch HTML from an external URL (Mode B — mod_url generic web page).

    Uses httpx async client with a sensible browser User-Agent so basic
    anti-bot protections don't block us for legitimate course content.

    Returns the full response text (HTML).

    Raises:
        ContentProcessingError if the request fails or returns a non-2xx status.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; AxisAI-LMS-Crawler/1.0; "
            "+https://edzlms.com/bot)"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.text
    except httpx.HTTPStatusError as exc:
        raise ContentProcessingError(
            f"Failed to fetch web page (HTTP {exc.response.status_code}): {url}"
        ) from exc
    except httpx.RequestError as exc:
        raise ContentProcessingError(
            f"Network error fetching web page: {url} — {exc}"
        ) from exc
