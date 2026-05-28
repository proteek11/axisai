"""
Abstract base extractor.
Every content type (PDF, YouTube, Vimeo, SCORM, etc.) implements this interface.

ExtractedContent is what every extractor returns — a normalized structure
that the rest of the pipeline (chunker, embedder) works with regardless
of where the content came from.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ExtractedContent:
    """
    Normalized output from any extractor.

    raw_text:         Full plain text, ready for chunking.
    content_hash:     SHA-256 of raw_text — used for change detection and
                      deterministic Qdrant IDs. Same content → same hash → upsert safely.
    page_count:       For PDFs. None for other types.
    word_count:       Approximate word count.
    segments:         Primary language transcript segments: [{start_sec, end_sec, text}].
                      Empty list for non-media content.
    all_segments:     ALL available transcript languages from the platform API.
                      dict keyed by BCP-47 language code, e.g.:
                        {"en": [...], "fr": [...], "de": [...]}
                      When empty, falls back to {primary_language: segments} in the pipeline.
    detected_source_language:
                      Language code detected automatically (Whisper result["language"]
                      for video, langdetect result for PDF). None if not detected.
                      Used to update content_item.language when the Moodle plugin sent
                      no language hint or sent "auto".
    extraction_metadata: Extractor-specific metadata stored verbatim in DB.
                      Examples:
                        PDF:     {pages: 12, has_images: true, pdf_version: "1.7"}
                        YouTube: {video_id: "abc", duration_sec: 300, caption_source: "api"}
                        SCORM:   {sco_count: 5, manifest_version: "2004"}
    """
    raw_text: str
    content_hash: str
    page_count: int | None = None
    word_count: int = 0
    segments: list[dict] = field(default_factory=list)        # primary language segments
    all_segments: dict[str, list[dict]] = field(default_factory=dict)  # {lang: segments}
    detected_source_language: str | None = None               # from Whisper/langdetect
    extraction_metadata: dict = field(default_factory=dict)


class BaseExtractor(ABC):
    """
    All extractors implement this interface.

    Usage pattern:
        extractor = PDFExtractor()
        result = await extractor.extract(url="https://...", content_item=item)
    """

    @abstractmethod
    async def extract(
        self,
        *,
        url: str | None = None,
        file_bytes: bytes | None = None,
        content_item_metadata: dict | None = None,
    ) -> ExtractedContent:
        """
        Extract text from the given source.

        Args:
            url:                  URL to download content from (most extractors).
            file_bytes:           Raw file bytes (when file was uploaded directly).
            content_item_metadata: Extra metadata from the ContentItem
                                  (title, language, Vimeo token, etc.)

        Returns:
            ExtractedContent with normalized text and metadata.

        Raises:
            ContentProcessingError on extraction failure.
        """
        ...

    @property
    @abstractmethod
    def supported_content_types(self) -> list[str]:
        """List of ContentType values this extractor handles."""
        ...
