"""
Teacher management CRUD endpoints.

All endpoints in this file are for teacher-facing management:
  - Summary edit
  - Glossary: list, add, edit, delete, regenerate
  - Flashcards: list, add, edit, delete, regenerate
  - Quiz questions: list, add, edit, delete, regenerate

URL pattern:  /api/v1/content/{content_item_id}/<resource>
All endpoints validate that the content_item belongs to the caller's tenant
via the API key header (same as existing content.py endpoints).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_tenant as get_tenant_from_api_key
from app.models.content import ContentItem
from app.models.flashcard import FlashcardItem
from app.models.glossary import GlossaryTerm
from app.models.output import AIOutput, OutputStatus, OutputType, QuizQuestion
from app.models.tenant import Tenant
from app.schemas.output import (
    FlashcardCreateRequest,
    FlashcardItemResponse,
    FlashcardPoolResponse,
    FlashcardUpdateRequest,
    GlossaryPoolResponse,
    GlossaryTermCreateRequest,
    GlossaryTermResponse,
    GlossaryTermUpdateRequest,
    PoolStats,
    QuizPoolResponse,
    QuizQuestionCreateRequest,
    QuizQuestionResponse,
    QuizQuestionUpdateRequest,
    RegenerateResponse,
    SummaryEditRequest,
    SummaryResponse,
)
from app.services.ai.client import AIClient
from app.services.regenerate import regenerate_flashcards, regenerate_quiz

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/content", tags=["teacher-management"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

async def _get_content_item(
    content_item_id: str,
    tenant: Tenant,
    db: AsyncSession,
) -> ContentItem:
    """Load ContentItem and verify it belongs to the caller's tenant."""
    try:
        cid = uuid.UUID(content_item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid content_item_id format")

    result = await db.execute(
        select(ContentItem)
        .where(ContentItem.id == cid)
        .where(ContentItem.tenant_id == tenant.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Content item not found")
    return item


def _build_pool_stats(rows: list, pool_max: int) -> PoolStats:
    active = sum(1 for r in rows if r.is_active)
    inactive = len(rows) - active
    source_breakdown = {}
    batch_set = set()
    for r in rows:
        src = getattr(r, "source", "generated")
        source_breakdown[src] = source_breakdown.get(src, 0) + 1
        batch_set.add(getattr(r, "generation_batch", 1))
    return PoolStats(
        total=len(rows),
        pool_max=pool_max,
        active=active,
        inactive=inactive,
        source_breakdown=source_breakdown,
        batch_count=len(batch_set),
    )


# ---------------------------------------------------------------------------
# Summary endpoints
# ---------------------------------------------------------------------------

@router.get("/{content_item_id}/summary", response_model=SummaryResponse)
async def get_summary(
    content_item_id: str,
    language: str = Query(default="en"),
    tenant: Tenant = Depends(get_tenant_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Get the summary for a content item.

    Returns the teacher-edited version if one exists, otherwise the AI-generated payload.
    """
    content_item = await _get_content_item(content_item_id, tenant, db)

    result = await db.execute(
        select(AIOutput)
        .where(AIOutput.content_item_id == content_item.id)
        .where(AIOutput.output_type == OutputType.SUMMARY)
        .where(AIOutput.language == language)
        .where(AIOutput.status == OutputStatus.ACTIVE)
        .order_by(AIOutput.created_at.desc())
        .limit(1)
    )
    output = result.scalar_one_or_none()
    if not output:
        raise HTTPException(status_code=404, detail=f"No summary found for language '{language}'")

    # Serve teacher edit if present, otherwise serve original payload
    effective_payload = output.edited_content if output.is_teacher_edited else output.payload

    return SummaryResponse(
        content_item_id=str(content_item.id),
        language=output.language,
        payload=effective_payload,
        is_teacher_edited=output.is_teacher_edited,
        last_edited_by=output.last_edited_by,
        last_edited_at=output.last_edited_at,
        model=output.model,
        prompt_version=output.prompt_version,
        created_at=output.created_at,
        updated_at=output.updated_at,
    )


async def edit_summary(
    content_item_id: str,
    body: SummaryEditRequest,
    language: str = Query(default="en"),
    tenant: Tenant = Depends(get_tenant_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Teacher edits the summary.

    Stores the edited version in `edited_content` — the original AI payload
    is preserved untouched for quality analysis.

    Accepts both PUT and POST (POST alias exists because Moodle's curl wrapper
    cannot reliably send PUT — CURLOPT_CUSTOMREQUEST is overridden by post()).
    """
    content_item = await _get_content_item(content_item_id, tenant, db)

    result = await db.execute(
        select(AIOutput)
        .where(AIOutput.content_item_id == content_item.id)
        .where(AIOutput.output_type == OutputType.SUMMARY)
        .where(AIOutput.language == language)
        .where(AIOutput.status == OutputStatus.ACTIVE)
        .order_by(AIOutput.created_at.desc())
        .limit(1)
    )
    output = result.scalar_one_or_none()
    if not output:
        raise HTTPException(status_code=404, detail=f"No summary found for language '{language}'")

    # Build the edited content structure
    edited = {
        "summary": body.summary,
    }
    if body.key_points is not None:
        edited["key_points"] = body.key_points
    if body.key_concepts is not None:
        edited["key_concepts"] = body.key_concepts
    if body.prerequisites is not None:
        edited["prerequisites"] = body.prerequisites

    output.edited_content = edited
    output.is_teacher_edited = True
    output.last_edited_by = body.moodle_user_id
    output.last_edited_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(output)

    log.info(
        "summary_edited",
        content_item_id=str(content_item.id),
        edited_by=body.moodle_user_id,
    )

    return SummaryResponse(
        content_item_id=str(content_item.id),
        language=output.language,
        payload=output.edited_content,
        is_teacher_edited=True,
        last_edited_by=output.last_edited_by,
        last_edited_at=output.last_edited_at,
        model=output.model,
        prompt_version=output.prompt_version,
        created_at=output.created_at,
        updated_at=output.updated_at,
    )


# Register edit_summary for both PUT (REST-correct) and POST (Moodle curl compat)
router.add_api_route(
    "/{content_item_id}/summary",
    edit_summary,
    methods=["PUT", "POST"],
    response_model=SummaryResponse,
    tags=["teacher-management"],
    summary="Teacher edits the summary (PUT or POST)",
)


# ---------------------------------------------------------------------------
# Glossary endpoints
# ---------------------------------------------------------------------------

@router.get("/{content_item_id}/glossary", response_model=GlossaryPoolResponse)
async def get_glossary(
    content_item_id: str,
    include_inactive: bool = Query(default=False),
    tenant: Tenant = Depends(get_tenant_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Get all glossary terms for a content item."""
    from app.services.regenerate import POOL_MAX_GLOSSARY

    content_item = await _get_content_item(content_item_id, tenant, db)

    query = (
        select(GlossaryTerm)
        .where(GlossaryTerm.content_item_id == content_item.id)
        .order_by(GlossaryTerm.term.asc())
    )
    if not include_inactive:
        query = query.where(GlossaryTerm.is_active == True)  # noqa: E712

    result = await db.execute(query)
    terms = result.scalars().all()

    # For pool stats we need all rows (including inactive)
    all_result = await db.execute(
        select(GlossaryTerm).where(GlossaryTerm.content_item_id == content_item.id)
    )
    all_terms = all_result.scalars().all()

    return GlossaryPoolResponse(
        content_item_id=str(content_item.id),
        pool=_build_pool_stats(all_terms, POOL_MAX_GLOSSARY),
        items=[GlossaryTermResponse.model_validate(t) for t in terms],
    )


@router.post("/{content_item_id}/glossary/terms", response_model=GlossaryTermResponse, status_code=201)
async def add_glossary_term(
    content_item_id: str,
    body: GlossaryTermCreateRequest,
    tenant: Tenant = Depends(get_tenant_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Teacher manually adds a glossary term."""
    content_item = await _get_content_item(content_item_id, tenant, db)

    # Determine next batch number
    batch_result = await db.execute(
        select(func.max(GlossaryTerm.generation_batch))
        .where(GlossaryTerm.content_item_id == content_item.id)
    )
    max_batch = batch_result.scalar() or 0

    term = GlossaryTerm(
        id=uuid.uuid4(),
        content_item_id=content_item.id,
        tenant_id=content_item.tenant_id,
        ai_output_id=None,
        term=body.term,
        definition=body.definition,
        context=body.context,
        related_terms=body.related_terms,
        category=body.category,
        source="manual",
        generation_batch=max_batch + 1,
        is_active=True,
        manually_added_by=body.moodle_user_id,
    )
    db.add(term)
    await db.commit()
    await db.refresh(term)

    log.info(
        "glossary_term_added_manual",
        content_item_id=str(content_item.id),
        term=body.term,
        added_by=body.moodle_user_id,
    )
    return GlossaryTermResponse.model_validate(term)


@router.put("/{content_item_id}/glossary/terms/{term_id}", response_model=GlossaryTermResponse)
async def update_glossary_term(
    content_item_id: str,
    term_id: str,
    body: GlossaryTermUpdateRequest,
    tenant: Tenant = Depends(get_tenant_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Teacher edits a glossary term (generated or manual)."""
    content_item = await _get_content_item(content_item_id, tenant, db)

    result = await db.execute(
        select(GlossaryTerm)
        .where(GlossaryTerm.id == uuid.UUID(term_id))
        .where(GlossaryTerm.content_item_id == content_item.id)
    )
    term = result.scalar_one_or_none()
    if not term:
        raise HTTPException(status_code=404, detail="Glossary term not found")

    if body.term is not None:
        term.term = body.term
    if body.definition is not None:
        term.definition = body.definition
    if body.context is not None:
        term.context = body.context
    if body.related_terms is not None:
        term.related_terms = body.related_terms
    if body.category is not None:
        term.category = body.category
    if body.is_active is not None:
        term.is_active = body.is_active

    await db.commit()
    await db.refresh(term)
    return GlossaryTermResponse.model_validate(term)


@router.delete("/{content_item_id}/glossary/terms/{term_id}", status_code=204)
async def delete_glossary_term(
    content_item_id: str,
    term_id: str,
    tenant: Tenant = Depends(get_tenant_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete a glossary term."""
    content_item = await _get_content_item(content_item_id, tenant, db)

    result = await db.execute(
        select(GlossaryTerm)
        .where(GlossaryTerm.id == uuid.UUID(term_id))
        .where(GlossaryTerm.content_item_id == content_item.id)
    )
    term = result.scalar_one_or_none()
    if not term:
        raise HTTPException(status_code=404, detail="Glossary term not found")

    await db.delete(term)
    await db.commit()
    log.info("glossary_term_deleted", term_id=term_id, content_item_id=str(content_item.id))


# ---------------------------------------------------------------------------
# Flashcard pool endpoints
# ---------------------------------------------------------------------------

@router.get("/{content_item_id}/flashcards", response_model=FlashcardPoolResponse)
async def get_flashcards(
    content_item_id: str,
    include_inactive: bool = Query(default=False),
    tenant: Tenant = Depends(get_tenant_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Get all flashcards in the pool for a content item."""
    from app.services.regenerate import POOL_MAX_FLASHCARDS

    content_item = await _get_content_item(content_item_id, tenant, db)

    query = (
        select(FlashcardItem)
        .where(FlashcardItem.content_item_id == content_item.id)
        .order_by(FlashcardItem.generation_batch.asc(), FlashcardItem.created_at.asc())
    )
    if not include_inactive:
        query = query.where(FlashcardItem.is_active == True)  # noqa: E712

    result = await db.execute(query)
    cards = result.scalars().all()

    all_result = await db.execute(
        select(FlashcardItem).where(FlashcardItem.content_item_id == content_item.id)
    )
    all_cards = all_result.scalars().all()

    return FlashcardPoolResponse(
        content_item_id=str(content_item.id),
        pool=_build_pool_stats(all_cards, POOL_MAX_FLASHCARDS),
        items=[FlashcardItemResponse.model_validate(c) for c in cards],
    )


@router.post("/{content_item_id}/flashcards", response_model=FlashcardItemResponse, status_code=201)
async def add_flashcard(
    content_item_id: str,
    body: FlashcardCreateRequest,
    tenant: Tenant = Depends(get_tenant_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Teacher manually adds a flashcard to the pool."""
    from app.services.regenerate import POOL_MAX_FLASHCARDS

    content_item = await _get_content_item(content_item_id, tenant, db)

    # Check pool cap
    count_result = await db.execute(
        select(func.count(FlashcardItem.id))
        .where(FlashcardItem.content_item_id == content_item.id)
        .where(FlashcardItem.is_active == True)  # noqa: E712
    )
    active_count = count_result.scalar() or 0
    if active_count >= POOL_MAX_FLASHCARDS:
        raise HTTPException(
            status_code=422,
            detail=f"Pool is at maximum capacity ({POOL_MAX_FLASHCARDS}). "
                   "Deactivate or delete existing cards to add more.",
        )

    batch_result = await db.execute(
        select(func.max(FlashcardItem.generation_batch))
        .where(FlashcardItem.content_item_id == content_item.id)
    )
    max_batch = batch_result.scalar() or 0

    card = FlashcardItem(
        id=uuid.uuid4(),
        content_item_id=content_item.id,
        tenant_id=content_item.tenant_id,
        ai_output_id=None,
        front=body.front,
        back=body.back,
        hint=body.hint,
        card_type=body.card_type,
        difficulty=body.difficulty,
        topic=body.topic,
        source="manual",
        generation_batch=max_batch + 1,
        is_active=True,
        manually_added_by=body.moodle_user_id,
    )
    db.add(card)
    await db.commit()
    await db.refresh(card)

    log.info(
        "flashcard_added_manual",
        content_item_id=str(content_item.id),
        added_by=body.moodle_user_id,
    )
    return FlashcardItemResponse.model_validate(card)


@router.put("/{content_item_id}/flashcards/{flashcard_id}", response_model=FlashcardItemResponse)
async def update_flashcard(
    content_item_id: str,
    flashcard_id: str,
    body: FlashcardUpdateRequest,
    tenant: Tenant = Depends(get_tenant_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Teacher edits a flashcard (generated or manual)."""
    content_item = await _get_content_item(content_item_id, tenant, db)

    result = await db.execute(
        select(FlashcardItem)
        .where(FlashcardItem.id == uuid.UUID(flashcard_id))
        .where(FlashcardItem.content_item_id == content_item.id)
    )
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Flashcard not found")

    if body.front is not None:
        card.front = body.front
    if body.back is not None:
        card.back = body.back
    if body.hint is not None:
        card.hint = body.hint
    if body.card_type is not None:
        card.card_type = body.card_type
    if body.difficulty is not None:
        card.difficulty = body.difficulty
    if body.topic is not None:
        card.topic = body.topic
    if body.is_active is not None:
        card.is_active = body.is_active

    await db.commit()
    await db.refresh(card)
    return FlashcardItemResponse.model_validate(card)


@router.delete("/{content_item_id}/flashcards/{flashcard_id}", status_code=204)
async def delete_flashcard(
    content_item_id: str,
    flashcard_id: str,
    tenant: Tenant = Depends(get_tenant_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete a flashcard from the pool."""
    content_item = await _get_content_item(content_item_id, tenant, db)

    result = await db.execute(
        select(FlashcardItem)
        .where(FlashcardItem.id == uuid.UUID(flashcard_id))
        .where(FlashcardItem.content_item_id == content_item.id)
    )
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Flashcard not found")

    await db.delete(card)
    await db.commit()
    log.info("flashcard_deleted", flashcard_id=flashcard_id, content_item_id=str(content_item.id))


@router.post("/{content_item_id}/flashcards/regenerate", response_model=RegenerateResponse)
async def regenerate_flashcards_endpoint(
    content_item_id: str,
    count: int = Query(default=10, ge=1, le=50),
    model: str = Query(default=None),
    tenant: Tenant = Depends(get_tenant_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Generate more flashcards and add them to the pool.

    Existing cards are preserved. New cards are deduplicated against existing
    ones (both at prompt level and semantic/vector level).
    Max pool size is 50 active cards.
    """
    content_item = await _get_content_item(content_item_id, tenant, db)

    from app.core.database import AsyncSessionFactory

    ai_client = AIClient(
        session_factory=AsyncSessionFactory,
        tenant_id=str(content_item.tenant_id),
        content_item_id=str(content_item.id),
    )

    result = await regenerate_flashcards(
        db=db,
        ai_client=ai_client,
        content_item=content_item,
        count=count,
        model=model,
    )

    return RegenerateResponse(**result)


# ---------------------------------------------------------------------------
# Quiz question pool endpoints
# ---------------------------------------------------------------------------

@router.get("/{content_item_id}/quiz-questions", response_model=QuizPoolResponse)
async def get_quiz_questions(
    content_item_id: str,
    include_inactive: bool = Query(default=False),
    blooms_level: str | None = Query(default=None),
    difficulty: str | None = Query(default=None),
    tenant: Tenant = Depends(get_tenant_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Get all quiz questions in the pool for a content item.

    Supports filtering by blooms_level and difficulty.
    """
    from app.services.regenerate import POOL_MAX_QUIZ

    content_item = await _get_content_item(content_item_id, tenant, db)

    query = (
        select(QuizQuestion)
        .where(QuizQuestion.content_item_id == content_item.id)
        .order_by(QuizQuestion.generation_batch.asc(), QuizQuestion.created_at.asc())
    )
    if not include_inactive:
        query = query.where(QuizQuestion.is_active == True)  # noqa: E712
    if blooms_level:
        query = query.where(QuizQuestion.blooms_level == blooms_level)
    if difficulty:
        query = query.where(QuizQuestion.difficulty_label == difficulty)

    result = await db.execute(query)
    questions = result.scalars().all()

    all_result = await db.execute(
        select(QuizQuestion).where(QuizQuestion.content_item_id == content_item.id)
    )
    all_questions = all_result.scalars().all()

    return QuizPoolResponse(
        content_item_id=str(content_item.id),
        pool=_build_pool_stats(all_questions, POOL_MAX_QUIZ),
        items=[QuizQuestionResponse.model_validate(q) for q in questions],
    )


@router.post("/{content_item_id}/quiz-questions", response_model=QuizQuestionResponse, status_code=201)
async def add_quiz_question(
    content_item_id: str,
    body: QuizQuestionCreateRequest,
    tenant: Tenant = Depends(get_tenant_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Teacher manually adds a quiz question to the pool."""
    from app.services.regenerate import POOL_MAX_QUIZ
    from app.models.output import QuestionType

    content_item = await _get_content_item(content_item_id, tenant, db)

    count_result = await db.execute(
        select(func.count(QuizQuestion.id))
        .where(QuizQuestion.content_item_id == content_item.id)
        .where(QuizQuestion.is_active == True)  # noqa: E712
    )
    active_count = count_result.scalar() or 0
    if active_count >= POOL_MAX_QUIZ:
        raise HTTPException(
            status_code=422,
            detail=f"Pool is at maximum capacity ({POOL_MAX_QUIZ}). "
                   "Deactivate or delete existing questions to add more.",
        )

    batch_result = await db.execute(
        select(func.max(QuizQuestion.generation_batch))
        .where(QuizQuestion.content_item_id == content_item.id)
    )
    max_batch = batch_result.scalar() or 0

    try:
        q_type = QuestionType(body.question_type)
    except ValueError:
        q_type = QuestionType.MULTICHOICE

    question = QuizQuestion(
        id=uuid.uuid4(),
        content_item_id=content_item.id,
        tenant_id=content_item.tenant_id,
        ai_output_id=None,
        question_type=q_type,
        question_text=body.question_text,
        options=body.options,
        correct_answer=body.correct_answer,
        explanation=body.explanation,
        blooms_level=body.blooms_level,
        difficulty_label=body.difficulty,
        topic_primary=body.topic_primary,
        topic_secondary=body.topic_secondary,
        learning_objective=body.learning_objective,
        source="manual",
        generation_batch=max_batch + 1,
        is_active=True,
        manually_added_by=body.moodle_user_id,
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)

    log.info(
        "quiz_question_added_manual",
        content_item_id=str(content_item.id),
        added_by=body.moodle_user_id,
    )
    return QuizQuestionResponse.model_validate(question)


@router.put("/{content_item_id}/quiz-questions/{question_id}", response_model=QuizQuestionResponse)
async def update_quiz_question(
    content_item_id: str,
    question_id: str,
    body: QuizQuestionUpdateRequest,
    tenant: Tenant = Depends(get_tenant_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Teacher edits a quiz question (generated or manual)."""
    content_item = await _get_content_item(content_item_id, tenant, db)

    result = await db.execute(
        select(QuizQuestion)
        .where(QuizQuestion.id == uuid.UUID(question_id))
        .where(QuizQuestion.content_item_id == content_item.id)
    )
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Quiz question not found")

    if body.question_text is not None:
        question.question_text = body.question_text
    if body.options is not None:
        question.options = body.options
    if body.correct_answer is not None:
        question.correct_answer = body.correct_answer
    if body.explanation is not None:
        question.explanation = body.explanation
    if body.blooms_level is not None:
        question.blooms_level = body.blooms_level
    if body.difficulty is not None:
        question.difficulty_label = body.difficulty
    if body.topic_primary is not None:
        question.topic_primary = body.topic_primary
    if body.topic_secondary is not None:
        question.topic_secondary = body.topic_secondary
    if body.learning_objective is not None:
        question.learning_objective = body.learning_objective
    if body.is_active is not None:
        question.is_active = body.is_active

    await db.commit()
    await db.refresh(question)
    return QuizQuestionResponse.model_validate(question)


@router.delete("/{content_item_id}/quiz-questions/{question_id}", status_code=204)
async def delete_quiz_question(
    content_item_id: str,
    question_id: str,
    tenant: Tenant = Depends(get_tenant_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete a quiz question from the pool."""
    content_item = await _get_content_item(content_item_id, tenant, db)

    result = await db.execute(
        select(QuizQuestion)
        .where(QuizQuestion.id == uuid.UUID(question_id))
        .where(QuizQuestion.content_item_id == content_item.id)
    )
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Quiz question not found")

    await db.delete(question)
    await db.commit()
    log.info("quiz_question_deleted", question_id=question_id, content_item_id=str(content_item.id))


@router.post("/{content_item_id}/quiz-questions/regenerate", response_model=RegenerateResponse)
async def regenerate_quiz_endpoint(
    content_item_id: str,
    count: int = Query(default=10, ge=1, le=50),
    model: str = Query(default=None),
    difficulty_distribution: str = Query(default="easy: 30%, medium: 50%, hard: 20%"),
    tenant: Tenant = Depends(get_tenant_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Generate more quiz questions and add them to the pool.

    Existing questions are preserved. New ones are deduplicated.
    Max pool size is 50 active questions.
    """
    content_item = await _get_content_item(content_item_id, tenant, db)

    from app.core.database import AsyncSessionFactory

    ai_client = AIClient(
        session_factory=AsyncSessionFactory,
        tenant_id=str(content_item.tenant_id),
        content_item_id=str(content_item.id),
    )

    result = await regenerate_quiz(
        db=db,
        ai_client=ai_client,
        content_item=content_item,
        count=count,
        model=model,
        difficulty_distribution=difficulty_distribution,
    )

    return RegenerateResponse(**result)


# ---------------------------------------------------------------------------
# Bulk-replace endpoints (Moodle teacher saves the full edited set at once)
# ---------------------------------------------------------------------------

class GlossaryBulkReplaceRequest(BaseModel):
    """Full set of glossary terms after teacher editing.  Replaces all active terms."""
    terms: list[dict]       # [{term, definition, context_note?}]
    moodle_user_id: int


class FlashcardBulkReplaceRequest(BaseModel):
    """Full set of flashcards after teacher editing.  Replaces all active cards."""
    cards: list[dict]       # [{front, back}]
    moodle_user_id: int


class BulkReplaceResponse(BaseModel):
    created: int


@router.post(
    "/{content_item_id}/glossary/bulk-replace",
    response_model=BulkReplaceResponse,
    summary="Replace all glossary terms with teacher-edited set (Moodle bulk save)",
)
async def bulk_replace_glossary(
    content_item_id: str,
    body: GlossaryBulkReplaceRequest,
    tenant: Tenant = Depends(get_tenant_from_api_key),
    db: AsyncSession = Depends(get_db),
) -> BulkReplaceResponse:
    """Deactivate all existing glossary terms then insert the teacher-provided set.

    Called by Moodle after the teacher saves edits in the content editor.
    The original generated terms are preserved as inactive for audit purposes.
    """
    content_item = await _get_content_item(content_item_id, tenant, db)

    # Soft-delete all currently active terms for this content item
    await db.execute(
        update(GlossaryTerm)
        .where(GlossaryTerm.content_item_id == content_item.id)
        .where(GlossaryTerm.is_active == True)  # noqa: E712
        .values(is_active=False)
    )

    # Insert the teacher's edited set
    now_dt = datetime.now(timezone.utc)
    for t in body.terms:
        term_text = str(t.get("term", "")).strip()[:255]
        if not term_text:
            continue
        db.add(GlossaryTerm(
            id=uuid.uuid4(),
            content_item_id=content_item.id,
            tenant_id=content_item.tenant_id,
            term=term_text,
            definition=str(t.get("definition", "")).strip(),
            context=str(t.get("context_note", "")).strip() or None,
            source="teacher_edit",
            generation_batch=0,
            is_active=True,
            manually_added_by=body.moodle_user_id,
            created_at=now_dt,
            updated_at=now_dt,
        ))

    await db.commit()
    log.info(
        "glossary_bulk_replaced",
        content_item_id=str(content_item.id),
        count=len(body.terms),
        by=body.moodle_user_id,
    )
    return BulkReplaceResponse(created=len(body.terms))


@router.post(
    "/{content_item_id}/flashcards/bulk-replace",
    response_model=BulkReplaceResponse,
    summary="Replace all flashcards with teacher-edited set (Moodle bulk save)",
)
async def bulk_replace_flashcards(
    content_item_id: str,
    body: FlashcardBulkReplaceRequest,
    tenant: Tenant = Depends(get_tenant_from_api_key),
    db: AsyncSession = Depends(get_db),
) -> BulkReplaceResponse:
    """Deactivate all existing flashcards then insert the teacher-provided set.

    Called by Moodle after the teacher saves edits in the content editor.
    """
    content_item = await _get_content_item(content_item_id, tenant, db)

    # Soft-delete all currently active cards for this content item
    await db.execute(
        update(FlashcardItem)
        .where(FlashcardItem.content_item_id == content_item.id)
        .where(FlashcardItem.is_active == True)  # noqa: E712
        .values(is_active=False)
    )

    # Insert the teacher's edited set
    now_dt = datetime.now(timezone.utc)
    for c in body.cards:
        front = str(c.get("front", "")).strip()
        back = str(c.get("back", "")).strip()
        if not front or not back:
            continue
        db.add(FlashcardItem(
            id=uuid.uuid4(),
            content_item_id=content_item.id,
            tenant_id=content_item.tenant_id,
            front=front,
            back=back,
            source="teacher_edit",
            generation_batch=0,
            is_active=True,
            manually_added_by=body.moodle_user_id,
            created_at=now_dt,
            updated_at=now_dt,
        ))

    await db.commit()
    log.info(
        "flashcards_bulk_replaced",
        content_item_id=str(content_item.id),
        count=len(body.cards),
        by=body.moodle_user_id,
    )
    return BulkReplaceResponse(created=len(body.cards))
