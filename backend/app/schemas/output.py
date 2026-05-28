"""Output response schemas — what GET /content/{id}/{output_type} returns.

Also includes:
- GenerateRequest (updated with count + regenerate support)
- Pool response schemas for flashcard_items and quiz_questions
- CRUD request/response bodies for teacher management endpoints
- Summary + Glossary edit schemas
"""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Existing schemas (unchanged except GenerateRequest)
# ---------------------------------------------------------------------------

class AIOutputResponse(BaseModel):
    """Generic output response — payload varies by output_type."""
    content_item_id: str
    output_type: str
    language: str
    status: str
    # effective_payload = edited_content if set, else payload
    payload: dict
    model: str | None
    provider: str | None
    prompt_version: str | None
    prompt_tokens: int
    completion_tokens: int
    confidence: float | None
    quality_reviewed: bool
    quality_rating: float | None
    # Teacher edit info (None if not yet edited)
    is_teacher_edited: bool = False
    last_edited_by: int | None = None
    last_edited_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GenerateRequest(BaseModel):
    """POST /content/{id}/generate — request specific outputs."""
    tasks: list[str]
    language: str = "en"
    options: dict = {}
    force_regenerate: bool = False   # Re-run generation even if output already exists
    # Pool-specific params (only used when task is flashcards or quiz)
    count: int = Field(default=10, ge=1, le=50, description="How many items to generate")
    regenerate: bool = Field(
        default=False,
        description="If True, ADD more items to the existing pool instead of regenerating from scratch"
    )


class TranscriptSegment(BaseModel):
    """A single time-coded transcript segment."""
    start_sec: float
    end_sec: float
    text: str


class TranscriptResponse(BaseModel):
    """GET /content/{id}/transcript — full transcript with segments."""
    content_item_id: str
    language: str
    source: str           # api_captions | whisper_local | whisper_api | manual
    word_count: int
    segment_count: int
    full_text: str
    segments: list[TranscriptSegment]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Pool stats (shared by flashcard + quiz pool responses)
# ---------------------------------------------------------------------------

class PoolStats(BaseModel):
    """Summary of pool size and composition."""
    total: int
    pool_max: int
    active: int
    inactive: int
    source_breakdown: dict[str, int]   # {"generated": N, "manual": M}
    batch_count: int                   # how many generation passes have run


# ---------------------------------------------------------------------------
# Flashcard schemas
# ---------------------------------------------------------------------------

class FlashcardItemResponse(BaseModel):
    """A single flashcard item from the pool."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    content_item_id: UUID
    front: str
    back: str
    hint: str | None
    card_type: str | None
    difficulty: str | None
    topic: str | None
    source: str            # generated | manual
    generation_batch: int
    is_active: bool
    manually_added_by: int | None
    created_at: datetime
    updated_at: datetime


class FlashcardPoolResponse(BaseModel):
    """GET /content/{id}/flashcards — full pool with stats."""
    content_item_id: str
    pool: PoolStats
    items: list[FlashcardItemResponse]


class FlashcardCreateRequest(BaseModel):
    """POST /content/{id}/flashcards — teacher manually adds a card."""
    front: str = Field(..., min_length=1, max_length=1000)
    back: str = Field(..., min_length=1, max_length=2000)
    hint: str | None = None
    card_type: str | None = None
    difficulty: str | None = None
    topic: str | None = None
    moodle_user_id: int = Field(..., description="Teacher's Moodle user ID")


class FlashcardUpdateRequest(BaseModel):
    """PUT /content/{id}/flashcards/{fid} — teacher edits a card."""
    front: str | None = Field(None, min_length=1, max_length=1000)
    back: str | None = Field(None, min_length=1, max_length=2000)
    hint: str | None = None
    card_type: str | None = None
    difficulty: str | None = None
    topic: str | None = None
    is_active: bool | None = None
    moodle_user_id: int = Field(..., description="Teacher's Moodle user ID")


class RegenerateResponse(BaseModel):
    """Response from a pool regeneration request."""
    added: int
    skipped_dedup: int
    pool_total: int
    pool_max: int
    generation_batch: int
    items: list[dict]  # Newly added items (lightweight dicts)


# ---------------------------------------------------------------------------
# Quiz question schemas
# ---------------------------------------------------------------------------

class QuizQuestionResponse(BaseModel):
    """A single quiz question from the pool."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    content_item_id: UUID
    question_type: str
    question_text: str
    options: list[dict] | None
    correct_answer: str | None
    explanation: str | None
    blooms_level: str | None
    # ORM column is difficulty_label; exposed as difficulty in the API
    difficulty: str | None = Field(None, validation_alias="difficulty_label")
    topic_primary: str | None
    topic_secondary: str | None
    learning_objective: str | None
    cognitive_skill: str | None
    source: str            # generated | manual
    generation_batch: int
    is_active: bool
    manually_added_by: int | None
    moodle_question_id: int | None
    quality_rating: float | None
    created_at: datetime
    updated_at: datetime


class QuizPoolResponse(BaseModel):
    """GET /content/{id}/quiz-questions — full pool with stats."""
    content_item_id: str
    pool: PoolStats
    items: list[QuizQuestionResponse]


class QuizQuestionCreateRequest(BaseModel):
    """POST /content/{id}/quiz-questions — teacher manually adds a question."""
    question_type: str = Field(default="multichoice", pattern="^(multichoice|truefalse|shortanswer|essay)$")
    question_text: str = Field(..., min_length=1, max_length=2000)
    options: list[dict] | None = None     # [{text, is_correct, feedback}]
    correct_answer: str | None = None
    explanation: str | None = None
    blooms_level: str | None = None
    difficulty: str | None = None
    topic_primary: str | None = None
    topic_secondary: str | None = None
    learning_objective: str | None = None
    moodle_user_id: int = Field(..., description="Teacher's Moodle user ID")


class QuizQuestionUpdateRequest(BaseModel):
    """PUT /content/{id}/quiz-questions/{qid} — teacher edits a question."""
    question_text: str | None = Field(None, min_length=1, max_length=2000)
    options: list[dict] | None = None
    correct_answer: str | None = None
    explanation: str | None = None
    blooms_level: str | None = None
    difficulty: str | None = None
    topic_primary: str | None = None
    topic_secondary: str | None = None
    learning_objective: str | None = None
    is_active: bool | None = None
    moodle_user_id: int = Field(..., description="Teacher's Moodle user ID")


# ---------------------------------------------------------------------------
# Summary edit schemas
# ---------------------------------------------------------------------------

class SummaryEditRequest(BaseModel):
    """PUT /content/{id}/summary — teacher edits the summary."""
    # Full summary structure — teacher can edit any field.
    # Unknown fields are stored as-is (JSONB); we only validate required ones.
    summary: str = Field(..., min_length=1, description="Main summary text")
    key_points: list[str] | None = None
    key_concepts: list[dict] | None = None   # [{term, definition}]
    prerequisites: list[str] | None = None
    moodle_user_id: int = Field(..., description="Teacher's Moodle user ID")


class SummaryResponse(BaseModel):
    """GET or PUT /content/{id}/summary — includes edit provenance."""
    content_item_id: str
    language: str
    # The effective content (edited_content if teacher has edited, else payload)
    payload: dict
    is_teacher_edited: bool
    last_edited_by: int | None
    last_edited_at: datetime | None
    model: str | None
    prompt_version: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Glossary schemas
# ---------------------------------------------------------------------------

class GlossaryTermResponse(BaseModel):
    """A single glossary term."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    content_item_id: UUID
    term: str
    definition: str
    context: str | None
    related_terms: list[str] | None
    category: str | None
    source: str            # generated | manual
    generation_batch: int
    is_active: bool
    manually_added_by: int | None
    created_at: datetime
    updated_at: datetime


class GlossaryPoolResponse(BaseModel):
    """GET /content/{id}/glossary — all terms with stats."""
    content_item_id: str
    pool: PoolStats
    items: list[GlossaryTermResponse]


class GlossaryTermCreateRequest(BaseModel):
    """POST /content/{id}/glossary/terms — teacher manually adds a term."""
    term: str = Field(..., min_length=1, max_length=255)
    definition: str = Field(..., min_length=1)
    context: str | None = None
    related_terms: list[str] | None = None
    category: str | None = None
    moodle_user_id: int = Field(..., description="Teacher's Moodle user ID")


class GlossaryTermUpdateRequest(BaseModel):
    """PUT /content/{id}/glossary/terms/{term_id} — teacher edits a term."""
    term: str | None = Field(None, min_length=1, max_length=255)
    definition: str | None = Field(None, min_length=1)
    context: str | None = None
    related_terms: list[str] | None = None
    category: str | None = None
    is_active: bool | None = None
    moodle_user_id: int = Field(..., description="Teacher's Moodle user ID")


# ---------------------------------------------------------------------------
# Chapters schemas
# ---------------------------------------------------------------------------

class ChapterItem(BaseModel):
    """A single AI-generated video chapter with seek timestamp."""
    title: str = Field(..., description="Short chapter title (3–8 words)")
    start_sec: float = Field(..., description="Chapter start time in seconds — seek to this value")
    end_sec: float = Field(..., description="Chapter end time in seconds")
    summary: str = Field(default="", description="1–2 sentence description of what the chapter covers")

    @property
    def start_fmt(self) -> str:
        """Human-readable start time (MM:SS or H:MM:SS)."""
        s = int(self.start_sec)
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        if h > 0:
            return f"{h}:{m:02d}:{sec:02d}"
        return f"{m:02d}:{sec:02d}"

    @property
    def duration_sec(self) -> float:
        """Chapter duration in seconds."""
        return max(0.0, self.end_sec - self.start_sec)


class ChaptersResponse(BaseModel):
    """
    GET /content/{id}/chapters — full chapters list ready for learner navigation.

    The frontend should render each chapter as a clickable row that calls
    the video player's seek() method with chapter.start_sec.
    """
    content_item_id: str
    language: str
    chapter_count: int
    total_duration_sec: float
    content_type: str
    chapters: list[ChapterItem]
    # Generation provenance
    model: str | None
    prompt_version: str | None
    is_teacher_edited: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# FAQ schemas
# ---------------------------------------------------------------------------

class FAQItem(BaseModel):
    """A single FAQ entry."""
    question: str = Field(..., description="The question a learner would ask")
    answer: str = Field(..., description="Clear, accurate answer to the question")
    topic: str = Field(default="", description="Subtopic this FAQ belongs to")
    difficulty: str = Field(
        default="beginner",
        description="One of: beginner, intermediate, advanced",
    )


class FAQResponse(BaseModel):
    """GET /content/{id}/faq — full FAQ list."""
    content_item_id: str
    language: str
    faq_count: int
    content_type: str
    faqs: list[FAQItem]
    model: str | None
    prompt_version: str | None
    is_teacher_edited: bool = False
    last_edited_by: int | None = None
    last_edited_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Infographic schemas
# ---------------------------------------------------------------------------

class ColourPalette(BaseModel):
    """Colour palette used in the generated infographic."""
    primary: str = Field(default="#1a7a8a", description="Primary colour (hex)")
    accent1: str = Field(default="#f0a500", description="First accent colour (hex)")
    accent2: str = Field(default="#e8f4f8", description="Second accent colour (hex)")


class InfographicResponse(BaseModel):
    """
    GET /content/{id}/infographic — JSON wrapper around the HTML infographic.

    Use GET /content/{id}/infographic/html to receive the HTML document
    directly as text/html (ideal for iframe src or direct download).
    """
    content_item_id: str
    language: str
    content_type: str
    title: str
    sections: list[str] = Field(
        default_factory=list,
        description="Visual section types included, e.g. ['key_statistics', 'core_concepts']",
    )
    colour_palette: ColourPalette = Field(default_factory=ColourPalette)
    html: str = Field(..., description="Complete self-contained HTML document")
    html_char_count: int = Field(default=0, description="Length of the HTML string")
    model: str | None
    prompt_version: str | None
    is_teacher_edited: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
