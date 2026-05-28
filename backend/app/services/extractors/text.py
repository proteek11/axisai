"""
Plain-text extractor for .txt and similar plain-text files.

Handles file:// and http(s):// URLs, plus raw bytes.
Treats the entire file as a single block of text — no page splitting.
"""
import re

import httpx
import structlog

from app.core.exceptions import ContentProcessingError
from app.utils.hashing import sha256_text
from .base import BaseExtractor, ExtractedContent

log = structlog.get_logger(__name__)

MAX_TEXT_BYTES = 100 * 1024 * 1024  # 100 MB
DOWNLOAD_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)


def _detect_language(text: str) -> str | None:
    try:
        from langdetect import detect, LangDetectException  # type: ignore
        sample = " ".join(text.split()[:500])
        if not sample.strip():
            return None
        return detect(sample)
    except Exception:
        return None


class TextExtractor(BaseExtractor):
    """Extracts text from plain .txt files (URL or raw bytes)."""

    @property
    def supported_content_types(self) -> list[str]:
        return ["text"]

    async def extract(
        self,
        *,
        url: str | None = None,
        file_bytes: bytes | None = None,
        content_item_metadata: dict | None = None,
    ) -> ExtractedContent:
        meta = content_item_metadata or {}
        language_hint = (meta.get("language", "") or "").strip().lower()

        # ── Acquire bytes ─────────────────────────────────────────────────
        if file_bytes is None:
            if url is None:
                raise ContentProcessingError("TextExtractor requires url or file_bytes")
            file_bytes = await self._download(url)

        if len(file_bytes) > MAX_TEXT_BYTES:
            raise ContentProcessingError(
                f"Text file too large: {len(file_bytes) / 1024 / 1024:.1f}MB. "
                f"Maximum is {MAX_TEXT_BYTES / 1024 / 1024:.0f}MB"
            )

        # ── Decode ───────────────────────────────────────────────────────
        for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
            try:
                raw_text = file_bytes.decode(encoding)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        else:
            raise ContentProcessingError("Could not decode text file (tried utf-8, latin-1, cp1252)")

        # ── Clean ────────────────────────────────────────────────────────
        raw_text = self._clean_text(raw_text)
        word_count = len(raw_text.split())
        content_hash = sha256_text(raw_text)

        # ── Language detection ────────────────────────────────────────────
        detected_language: str | None = None
        if (not language_hint or language_hint == "auto") and raw_text:
            detected_language = _detect_language(raw_text)

        log.info(
            "text_extracted",
            words=word_count,
            size_kb=len(file_bytes) // 1024,
            detected_language=detected_language,
        )

        return ExtractedContent(
            raw_text=raw_text,
            content_hash=content_hash,
            page_count=None,
            word_count=word_count,
            segments=[],
            all_segments={},
            detected_source_language=detected_language,
            extraction_metadata={
                "extractor": "text",
                "size_bytes": len(file_bytes),
            },
        )

    async def _download(self, url: str) -> bytes:
        # Handle file:// URLs (local uploads)
        if url.startswith("file://"):
            path = url[7:]
            try:
                with open(path, "rb") as fh:
                    return fh.read()
            except OSError as e:
                raise ContentProcessingError(f"Cannot read local file {path}: {e}")

        log.info("text_downloading", url=url)
        try:
            async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.content
        except httpx.TimeoutException:
            raise ContentProcessingError(f"Timeout downloading text file from {url}")
        except httpx.HTTPStatusError as e:
            raise ContentProcessingError(f"HTTP {e.response.status_code} downloading from {url}")
        except ContentProcessingError:
            raise
        except Exception as e:
            raise ContentProcessingError(f"Failed to download text file: {str(e)}")

    def _clean_text(self, text: str) -> str:
        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # Collapse 3+ blank lines → 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
