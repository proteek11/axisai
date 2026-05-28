"""
Ingest request/response schemas.
POST /api/v1/ingest — submit a PDF URL or file for processing.
"""
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, BaseModel, Field


class IngestOptions(BaseModel):
    """Optional overrides for pipeline configuration."""
    chunking_strategy: Literal["recursive", "token", "semantic"] = "recursive"
    chunk_size: int = Field(default=1000, ge=100, le=8000)
    chunk_overlap: int = Field(default=200, ge=0, le=1000)
    tasks: list[str] = Field(
        default=["summary"],
        description="Which outputs to generate: summary, flashcards, quiz, glossary, mindmap, objectives, blooms"
    )
    language: str = Field(default="", max_length=10,
                          description="Source/hint language of the content (BCP-47, e.g. 'en', 'fr'). "
                                      "Empty or 'auto' = auto-detect from content.")
    output_language: str = Field(default="", max_length=10,
                                 description="Desired language for all AI outputs (BCP-47). "
                                             "Empty = same as source language.")
    # AI provider override for this job (optional)
    provider: str | None = None
    model: str | None = None


class IngestURLRequest(BaseModel):
    """
    Ingest content by URL.
    Works for: PDF URLs, YouTube URLs, Vimeo URLs (include token in metadata).
    """
    source_url: str = Field(..., description="URL of the content to process")
    content_type: str = Field(
        ...,
        description="Content type: pdf, youtube, vimeo, peertube, scorm, h5p, html_page",
        examples=["pdf", "youtube", "vimeo"],
    )
    moodle_course_id: int = Field(..., description="Moodle course ID")
    moodle_cmid: int = Field(..., description="Moodle course module ID")
    moodle_user_id: int | None = Field(None, description="Moodle user who triggered this")
    moodle_section_id: int | None = None
    title: str | None = Field(None, max_length=512, description="Content title")
    options: IngestOptions = Field(default_factory=IngestOptions)
    # Extra metadata passed to extractor (e.g., Vimeo access token, SCORM options)
    metadata: dict = Field(default_factory=dict)


class IngestResponse(BaseModel):
    """Returned immediately after POST /ingest. Poll /jobs/{job_id} for status."""
    content_item_id: str
    job_id: str
    status: str
    message: str = "Job queued. Poll /api/v1/jobs/{job_id} for status."


# ── Structured ingest (SCORM pre-extracted) ───────────────────────────────────

class StructuredChunk(BaseModel):
    """
    A single pre-extracted content chunk from SCORM/H5P/custom extraction.
    PHP Moodle plugin produces these from the SCORM extractor.
    """
    sequence: int = Field(..., description="Order of this chunk within the content")
    chunk_type: str = Field(
        "slide", description="slide|lesson|page|section|audio_transcript|embed"
    )
    title: str | None = Field(None, description="Title for this chunk (slide/lesson title)")
    text: str = Field(..., description="Main text content of this chunk")
    has_audio: bool = False
    audio_transcript: str | None = Field(
        None, description="Transcript of the audio/narration for this chunk"
    )
    embed_url: str | None = Field(
        None, description="Embedded video URL if present (for reference only)"
    )


class StructuredIngestRequest(BaseModel):
    """
    Ingest pre-extracted content from SCORM/H5P.
    PHP sends this after running its own extractor. No server-side extraction needed.
    Pipeline picks up at chunking → embedding → generation.
    """
    moodle_course_id: int
    moodle_cmid: int
    moodle_user_id: int | None = None
    moodle_section_id: int | None = None
    title: str = Field(..., max_length=512)
    content_type: str = Field(
        "scorm", description="scorm|h5p|page|book — type of source content"
    )
    language: str = Field("", description="Source language hint (empty = auto-detect from text)")
    output_language: str = Field("", description="Target language for AI outputs (empty = same as source)")
    chunks: list[StructuredChunk] = Field(
        ..., min_length=1,
        description="Pre-extracted content chunks in order"
    )
    options: IngestOptions = Field(default_factory=IngestOptions)
    metadata: dict = Field(
        default_factory=dict,
        description="Any extra metadata from the extractor (SCORM version, manifest data, etc.)"
    )
