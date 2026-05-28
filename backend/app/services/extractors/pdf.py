"""
PDF extractor using PyMuPDF (fitz).

Why PyMuPDF over pdfplumber/pypdf:
- Fastest Python PDF library (C extension)
- Best text extraction quality, handles complex layouts
- Built-in page coordinate data (useful for future structured extraction)
- Handles password-protected PDFs

Flow:
    URL/bytes → download (if URL) → fitz.open() → extract page text
    → join → langdetect (if no language hint) → compute hash → return ExtractedContent

Language detection:
    If the Moodle plugin did not send a language hint (or sent "auto"), langdetect
    is run on the first ~500 words of extracted text. The detected language is
    stored in ExtractedContent.detected_source_language so the pipeline can:
      1. Update ContentItem.language for future use.
      2. Use it as the output_language when no explicit output_language was requested.
"""
import io
import re
from pathlib import Path

import fitz  # PyMuPDF
import httpx
import structlog

from app.core.exceptions import ContentProcessingError
from app.utils.hashing import sha256_bytes, sha256_text
from .base import BaseExtractor, ExtractedContent

log = structlog.get_logger(__name__)

# Max PDF size we'll attempt to extract (100MB default, matches config)
MAX_PDF_BYTES = 100 * 1024 * 1024

# Approximate word count fed to langdetect for language identification.
# 500 words gives reliable detection; less may be unreliable for short docs.
_LANGDETECT_SAMPLE_WORDS = 500


def _detect_language(text: str) -> str | None:
    """
    Attempt to detect the dominant language of a text using langdetect.

    Returns a BCP-47 language code (e.g. "en", "fr", "de") or None if
    langdetect is not installed or detection fails.

    Only the first _LANGDETECT_SAMPLE_WORDS words are used to keep the call fast.
    """
    try:
        from langdetect import detect, LangDetectException  # type: ignore
        sample = " ".join(text.split()[:_LANGDETECT_SAMPLE_WORDS])
        if not sample.strip():
            return None
        return detect(sample)
    except ImportError:
        log.debug("langdetect_not_installed", hint="pip install langdetect")
        return None
    except Exception as e:
        log.debug("langdetect_failed", error=str(e))
        return None

# httpx timeout for downloading PDFs
DOWNLOAD_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)


class PDFExtractor(BaseExtractor):
    """Extracts text from PDF files (by URL or raw bytes)."""

    @property
    def supported_content_types(self) -> list[str]:
        return ["pdf"]

    async def extract(
        self,
        *,
        url: str | None = None,
        file_bytes: bytes | None = None,
        content_item_metadata: dict | None = None,
    ) -> ExtractedContent:
        """
        Extract all text from a PDF.

        If `url` is provided, downloads first.
        If `file_bytes` is provided, uses directly.

        Returns ExtractedContent with full text and per-page metadata.
        Sets detected_source_language when the language was auto-detected.
        """
        meta = content_item_metadata or {}
        # Language hint from Moodle — empty or "auto" triggers auto-detection
        language_hint = meta.get("language", "") or ""

        # ── Acquire PDF bytes ─────────────────────────────────────────────
        if file_bytes is None:
            if url is None:
                raise ContentProcessingError("PDFExtractor requires url or file_bytes")
            file_bytes = await self._download(url)

        if len(file_bytes) > MAX_PDF_BYTES:
            raise ContentProcessingError(
                f"PDF too large: {len(file_bytes) / 1024 / 1024:.1f}MB. "
                f"Maximum is {MAX_PDF_BYTES / 1024 / 1024:.0f}MB"
            )

        # ── Extract text ──────────────────────────────────────────────────
        try:
            raw_text, extraction_meta = self._extract_text(file_bytes)
        except Exception as e:
            log.error("pdf_extraction_failed", error=str(e))
            raise ContentProcessingError(
                f"Failed to extract PDF text: {str(e)}",
                detail={"url": url},
            )

        # ── Post-process ──────────────────────────────────────────────────
        raw_text = self._clean_text(raw_text)
        word_count = len(raw_text.split())
        content_hash = sha256_text(raw_text)

        # ── Language detection ────────────────────────────────────────────
        # Run langdetect when Moodle provided no language hint (or "auto").
        # This populates detected_source_language so the pipeline can tag
        # the ContentItem and use the correct output language for generators.
        detected_language: str | None = None
        needs_detection = not language_hint or language_hint.strip().lower() == "auto"
        if needs_detection and raw_text:
            detected_language = _detect_language(raw_text)
            if detected_language:
                log.info(
                    "pdf_language_detected",
                    detected=detected_language,
                    sample_words=min(word_count, _LANGDETECT_SAMPLE_WORDS),
                )

        log.info(
            "pdf_extracted",
            pages=extraction_meta.get("page_count"),
            words=word_count,
            size_kb=len(file_bytes) // 1024,
            detected_language=detected_language,
        )

        return ExtractedContent(
            raw_text=raw_text,
            content_hash=content_hash,
            page_count=extraction_meta.get("page_count"),
            word_count=word_count,
            segments=[],  # PDFs have no time segments
            all_segments={},  # PDFs have no caption tracks
            detected_source_language=detected_language,
            extraction_metadata=extraction_meta,
        )

    async def _download(self, url: str) -> bytes:
        """Download PDF from URL with timeout and size checks."""
        # Handle file:// URLs (local uploads saved by the spaces upload endpoint)
        if url.startswith("file://"):
            path = url[7:]
            try:
                with open(path, "rb") as fh:
                    return fh.read()
            except OSError as e:
                raise ContentProcessingError(f"Cannot read local file {path}: {e}")

        log.info("pdf_downloading", url=url)
        try:
            async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                content_length = int(response.headers.get("content-length", 0))

                if content_length > MAX_PDF_BYTES:
                    raise ContentProcessingError(
                        f"PDF too large: {content_length / 1024 / 1024:.1f}MB"
                    )

                data = response.content
                log.info("pdf_downloaded", size_kb=len(data) // 1024, content_type=content_type)
                return data

        except httpx.TimeoutException:
            raise ContentProcessingError(f"Timeout downloading PDF from {url}")
        except httpx.HTTPStatusError as e:
            raise ContentProcessingError(
                f"HTTP {e.response.status_code} downloading PDF from {url}"
            )
        except ContentProcessingError:
            raise
        except Exception as e:
            raise ContentProcessingError(f"Failed to download PDF: {str(e)}")

    def _extract_text(self, pdf_bytes: bytes) -> tuple[str, dict]:
        """
        Extract text from PDF bytes using PyMuPDF.
        Returns (full_text, metadata_dict).
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        page_texts: list[str] = []
        page_word_counts: list[int] = []
        has_images = False
        has_tables = False

        for page_num, page in enumerate(doc):
            # Extract text with layout preservation
            text = page.get_text("text")  # "text" mode: plain text, reading order

            # Track images (useful for future OCR decision)
            image_list = page.get_images()
            if image_list:
                has_images = True

            word_count = len(text.split())
            page_texts.append(text)
            page_word_counts.append(word_count)

        doc.close()

        full_text = "\n\n".join(page_texts)

        metadata = {
            "page_count": len(page_texts),
            "page_word_counts": page_word_counts,
            "has_images": has_images,
            "has_tables": has_tables,
            "pdf_version": doc.pdf_version() if hasattr(doc, "pdf_version") else None,
            "is_encrypted": False,  # We only process non-encrypted PDFs here
            "extractor": "pymupdf",
        }

        return full_text, metadata

    def _clean_text(self, text: str) -> str:
        """
        Clean extracted PDF text:
        - Remove excessive whitespace/blank lines
        - Fix hyphenation artifacts (word- \nbreak → wordbr eak)
        - Normalize unicode
        """
        # Fix PDF hyphenation (word split across lines)
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

        # Normalize line breaks — collapse 3+ newlines to 2
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Remove lines that are just page numbers or whitespace
        lines = text.split("\n")
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # Skip lines that are just a number (page number) or very short noise
            if stripped and not re.match(r"^\d+$", stripped):
                cleaned_lines.append(stripped)
            elif not stripped:
                cleaned_lines.append("")  # Preserve blank lines as paragraph breaks

        text = "\n".join(cleaned_lines)

        # Final cleanup
        text = text.strip()
        return text
