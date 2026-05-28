"""
Regenerate service — extends an existing pool of flashcards or quiz questions
without duplicating items already in the pool.

Flow:
1. Fetch current pool (active items) from DB for the content_item
2. Check pool has room (current < POOL_MAX)
3. Embed existing items into axis_question_intelligence Qdrant collection
   (only those not yet embedded — qdrant_id is NULL)
4. Call generator with existing items injected into prompt (prompt-level dedup)
5. For each new AI-generated item, do semantic similarity check against Qdrant
   (vector-level dedup — catches paraphrases the prompt didn't catch)
6. Insert only genuinely new items with incremented generation_batch
7. Return the new items added + updated pool stats

Pool max caps (configurable; these are global defaults):
- Flashcards:      50
- Quiz questions:  50
- Glossary terms: 100  (glossary benefits from larger pools)
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.flashcard import FlashcardItem
from app.models.glossary import GlossaryTerm
from app.models.output import AIOutput, OutputStatus, OutputType, QuizQuestion
from app.services.generators.flashcards import FlashcardsGenerator
from app.services.generators.quiz import QuizGenerator
from app.services.vector.embedder import Embedder

if TYPE_CHECKING:
    from app.services.ai.client import AIClient

log = structlog.get_logger(__name__)

POOL_MAX_FLASHCARDS = 50
POOL_MAX_QUIZ = 50
POOL_MAX_GLOSSARY = 100

# Cosine similarity threshold: items above this are considered duplicates.
# 0.88 catches near-paraphrases while allowing genuinely different questions
# on similar topics to co-exist.
DEDUP_SIMILARITY_THRESHOLD = 0.88

# Qdrant collection used for question/card similarity
QUESTION_COLLECTION = "axis_question_intelligence"


# ---------------------------------------------------------------------------
# Flashcard regeneration
# ---------------------------------------------------------------------------

async def regenerate_flashcards(
    db: AsyncSession,
    ai_client: "AIClient",
    content_item: ContentItem,
    count: int = 10,
    model: str | None = None,
) -> dict:
    """
    Add `count` more flashcards to the pool for `content_item`.

    Returns:
        {
            "added": <int>,          # how many new cards were inserted
            "skipped_dedup": <int>,  # how many AI-generated cards were dropped as duplicates
            "pool_total": <int>,     # total active cards in pool after this pass
            "pool_max": 50,
            "generation_batch": <int>,
            "items": [...]           # the newly added FlashcardItem rows (as dicts)
        }
    """
    # 1. Load current active pool
    result = await db.execute(
        select(FlashcardItem)
        .where(FlashcardItem.content_item_id == content_item.id)
        .where(FlashcardItem.is_active == True)  # noqa: E712
        .order_by(FlashcardItem.generation_batch, FlashcardItem.created_at)
    )
    existing_rows = result.scalars().all()
    current_count = len(existing_rows)

    if current_count >= POOL_MAX_FLASHCARDS:
        log.info(
            "flashcard_pool_at_max",
            content_item_id=str(content_item.id),
            current=current_count,
            max=POOL_MAX_FLASHCARDS,
        )
        return {
            "added": 0,
            "skipped_dedup": 0,
            "pool_total": current_count,
            "pool_max": POOL_MAX_FLASHCARDS,
            "generation_batch": _next_batch(existing_rows),
            "items": [],
        }

    # Cap the requested count so we don't exceed pool max
    slots_available = POOL_MAX_FLASHCARDS - current_count
    effective_count = min(count, slots_available)

    # 2. Build existing_items list for prompt injection
    existing_for_prompt = [
        {"front": r.front, "back": r.back} for r in existing_rows
    ]

    # 3. Determine next generation batch
    next_batch = _next_batch(existing_rows)

    # 4. Get extracted text for generation
    from app.models.content import ExtractedContent
    ec_result = await db.execute(
        select(ExtractedContent).where(ExtractedContent.content_item_id == content_item.id)
    )
    extracted = ec_result.scalar_one_or_none()
    if not extracted:
        raise ValueError(f"No extracted content for content_item {content_item.id}")

    # 5. Call generator
    generator = FlashcardsGenerator(ai_client=ai_client)
    _model = model or "gpt-4o-mini"
    payload = await generator.generate(
        content_item=content_item,
        full_text=extracted.raw_text,
        model=_model,
        count=effective_count,
        existing_items=existing_for_prompt,
    )

    new_cards = payload.get("cards", [])

    # 6. Semantic deduplication via Qdrant
    #    Embed existing fronts that don't have qdrant_ids yet, then check
    #    each new card against the full existing embedding space.
    new_cards, skipped = await _dedup_flashcards(
        ai_client=ai_client,
        existing_rows=existing_rows,
        new_cards=new_cards,
    )

    if not new_cards:
        return {
            "added": 0,
            "skipped_dedup": skipped,
            "pool_total": current_count,
            "pool_max": POOL_MAX_FLASHCARDS,
            "generation_batch": next_batch,
            "items": [],
        }

    # 7. Find or create a parent AIOutput record for this regenerate batch
    ai_output = await _get_or_create_ai_output(
        db=db,
        content_item=content_item,
        output_type=OutputType.FLASHCARDS,
        model=_model,
        batch=next_batch,
    )

    # 8. Save new rows
    fake_payload = {"cards": new_cards}
    saved = await generator.save_cards_to_db(
        db=db,
        content_item=content_item,
        ai_output=ai_output,
        payload=fake_payload,
        generation_batch=next_batch,
    )

    log.info(
        "flashcard_regenerate_complete",
        content_item_id=str(content_item.id),
        added=len(saved),
        skipped_dedup=skipped,
        new_pool_total=current_count + len(saved),
        batch=next_batch,
    )

    return {
        "added": len(saved),
        "skipped_dedup": skipped,
        "pool_total": current_count + len(saved),
        "pool_max": POOL_MAX_FLASHCARDS,
        "generation_batch": next_batch,
        "items": [_flashcard_to_dict(f) for f in saved],
    }


# ---------------------------------------------------------------------------
# Quiz regeneration
# ---------------------------------------------------------------------------

async def regenerate_quiz(
    db: AsyncSession,
    ai_client: "AIClient",
    content_item: ContentItem,
    count: int = 10,
    model: str | None = None,
    difficulty_distribution: str = "easy: 30%, medium: 50%, hard: 20%",
) -> dict:
    """
    Add `count` more quiz questions to the pool for `content_item`.
    """
    result = await db.execute(
        select(QuizQuestion)
        .where(QuizQuestion.content_item_id == content_item.id)
        .where(QuizQuestion.is_active == True)  # noqa: E712
        .order_by(QuizQuestion.generation_batch, QuizQuestion.created_at)
    )
    existing_rows = result.scalars().all()
    current_count = len(existing_rows)

    if current_count >= POOL_MAX_QUIZ:
        return {
            "added": 0,
            "skipped_dedup": 0,
            "pool_total": current_count,
            "pool_max": POOL_MAX_QUIZ,
            "generation_batch": _next_batch(existing_rows),
            "items": [],
        }

    slots_available = POOL_MAX_QUIZ - current_count
    effective_count = min(count, slots_available)

    existing_for_prompt = [
        {"question_text": r.question_text} for r in existing_rows
    ]
    next_batch = _next_batch(existing_rows)

    from app.models.content import ExtractedContent
    ec_result = await db.execute(
        select(ExtractedContent).where(ExtractedContent.content_item_id == content_item.id)
    )
    extracted = ec_result.scalar_one_or_none()
    if not extracted:
        raise ValueError(f"No extracted content for content_item {content_item.id}")

    generator = QuizGenerator(ai_client=ai_client)
    _model = model or "gpt-4o-mini"
    payload = await generator.generate(
        content_item=content_item,
        full_text=extracted.raw_text,
        model=_model,
        question_count=effective_count,
        difficulty_distribution=difficulty_distribution,
        existing_items=existing_for_prompt,
    )

    new_questions = payload.get("questions", [])

    # Semantic dedup
    new_questions, skipped = await _dedup_quiz_questions(
        ai_client=ai_client,
        existing_rows=existing_rows,
        new_questions=new_questions,
    )

    if not new_questions:
        return {
            "added": 0,
            "skipped_dedup": skipped,
            "pool_total": current_count,
            "pool_max": POOL_MAX_QUIZ,
            "generation_batch": next_batch,
            "items": [],
        }

    ai_output = await _get_or_create_ai_output(
        db=db,
        content_item=content_item,
        output_type=OutputType.QUIZ,
        model=_model,
        batch=next_batch,
    )

    fake_payload = {"questions": new_questions}
    saved = await generator.save_questions_to_db(
        db=db,
        content_item=content_item,
        ai_output=ai_output,
        payload=fake_payload,
        model=_model,
        generation_batch=next_batch,
    )

    log.info(
        "quiz_regenerate_complete",
        content_item_id=str(content_item.id),
        added=len(saved),
        skipped_dedup=skipped,
        new_pool_total=current_count + len(saved),
        batch=next_batch,
    )

    return {
        "added": len(saved),
        "skipped_dedup": skipped,
        "pool_total": current_count + len(saved),
        "pool_max": POOL_MAX_QUIZ,
        "generation_batch": next_batch,
        "items": [_quiz_question_to_dict(q) for q in saved],
    }


# ---------------------------------------------------------------------------
# Semantic deduplication helpers
# ---------------------------------------------------------------------------

async def _dedup_flashcards(
    ai_client: "AIClient",
    existing_rows: list[FlashcardItem],
    new_cards: list[dict],
) -> tuple[list[dict], int]:
    """
    Filter `new_cards` to remove semantic duplicates of `existing_rows`.

    Strategy: embed the front of each new card, then cosine-compare against
    all existing fronts. Items above DEDUP_SIMILARITY_THRESHOLD are dropped.

    If the Qdrant/embedding call fails for any reason, we fall back gracefully
    and return all new cards (prompt-level dedup is still active).
    """
    if not existing_rows or not new_cards:
        return new_cards, 0

    try:
        embedder = Embedder(ai_client=ai_client)

        # Embed existing fronts
        existing_texts = [r.front for r in existing_rows]
        existing_embeddings = await embedder.embed(existing_texts)

        # Embed new card fronts
        new_texts = [c.get("front", "") for c in new_cards]
        new_embeddings = await embedder.embed(new_texts)

        accepted = []
        skipped = 0
        for card, emb in zip(new_cards, new_embeddings):
            if _is_duplicate(emb, existing_embeddings):
                skipped += 1
                log.debug(
                    "flashcard_dedup_skip",
                    front=card.get("front", "")[:60],
                )
            else:
                accepted.append(card)
                # Add the new embedding to existing set so subsequent
                # cards in this same batch are also deduped against it
                existing_embeddings.append(emb)

        return accepted, skipped

    except Exception as exc:
        log.warning(
            "flashcard_dedup_fallback",
            error=str(exc),
            note="Returning all AI-generated cards without vector dedup",
        )
        return new_cards, 0


async def _dedup_quiz_questions(
    ai_client: "AIClient",
    existing_rows: list[QuizQuestion],
    new_questions: list[dict],
) -> tuple[list[dict], int]:
    """Filter new quiz questions to remove semantic duplicates of existing rows."""
    if not existing_rows or not new_questions:
        return new_questions, 0

    try:
        embedder = Embedder(ai_client=ai_client)

        existing_texts = [r.question_text for r in existing_rows]
        existing_embeddings = await embedder.embed(existing_texts)

        new_texts = [q.get("question_text", "") for q in new_questions]
        new_embeddings = await embedder.embed(new_texts)

        accepted = []
        skipped = 0
        for question, emb in zip(new_questions, new_embeddings):
            if _is_duplicate(emb, existing_embeddings):
                skipped += 1
                log.debug(
                    "quiz_dedup_skip",
                    question=question.get("question_text", "")[:60],
                )
            else:
                accepted.append(question)
                existing_embeddings.append(emb)

        return accepted, skipped

    except Exception as exc:
        log.warning(
            "quiz_dedup_fallback",
            error=str(exc),
            note="Returning all AI-generated questions without vector dedup",
        )
        return new_questions, 0


def _is_duplicate(
    candidate_embedding: list[float],
    existing_embeddings: list[list[float]],
) -> bool:
    """Return True if cosine similarity to any existing embedding exceeds threshold."""
    import math

    def cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    for existing_emb in existing_embeddings:
        if cosine(candidate_embedding, existing_emb) >= DEDUP_SIMILARITY_THRESHOLD:
            return True
    return False


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _next_batch(existing_rows: list) -> int:
    """Return the next generation_batch number."""
    if not existing_rows:
        return 1
    max_batch = max((getattr(r, "generation_batch", 1) or 1) for r in existing_rows)
    return max_batch + 1


async def _get_or_create_ai_output(
    db: AsyncSession,
    content_item: ContentItem,
    output_type: OutputType,
    model: str,
    batch: int,
) -> AIOutput:
    """
    Find the latest ACTIVE AIOutput for this content + type, or create a
    lightweight new one to serve as the parent for pool rows added in this
    regenerate batch.

    We do NOT supersede the existing output — the pool table is the source
    of truth; the AIOutput here is just a provenance anchor.
    """
    result = await db.execute(
        select(AIOutput)
        .where(AIOutput.content_item_id == content_item.id)
        .where(AIOutput.output_type == output_type)
        .where(AIOutput.status == OutputStatus.ACTIVE)
        .order_by(AIOutput.created_at.desc())
        .limit(1)
    )
    existing_output = result.scalar_one_or_none()

    if existing_output:
        return existing_output

    # No existing output — create a minimal one (shouldn't happen in normal
    # flow, but handles edge cases like manual additions before first generation)
    new_output = AIOutput(
        id=uuid.uuid4(),
        content_item_id=content_item.id,
        tenant_id=content_item.tenant_id,
        output_type=output_type,
        language=content_item.language or "en",
        status=OutputStatus.ACTIVE,
        payload={"note": f"Pool anchor — batch {batch}", "cards": [], "questions": []},
        model=model,
        prompt_version="v1",
        prompt_tokens=0,
        completion_tokens=0,
    )
    db.add(new_output)
    await db.flush()
    return new_output


def _flashcard_to_dict(f: FlashcardItem) -> dict:
    return {
        "id": str(f.id),
        "front": f.front,
        "back": f.back,
        "hint": f.hint,
        "card_type": f.card_type,
        "difficulty": f.difficulty,
        "topic": f.topic,
        "source": f.source,
        "generation_batch": f.generation_batch,
        "is_active": f.is_active,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


def _quiz_question_to_dict(q: QuizQuestion) -> dict:
    return {
        "id": str(q.id),
        "question_text": q.question_text,
        "question_type": q.question_type,
        "options": q.options,
        "correct_answer": q.correct_answer,
        "explanation": q.explanation,
        "blooms_level": q.blooms_level,
        "difficulty": q.difficulty_label,
        "topic_primary": q.topic_primary,
        "topic_secondary": q.topic_secondary,
        "source": q.source,
        "generation_batch": q.generation_batch,
        "is_active": q.is_active,
        "created_at": q.created_at.isoformat() if q.created_at else None,
    }
