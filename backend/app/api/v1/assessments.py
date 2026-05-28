"""
Assessment Builder API — Phase 15.

Creator endpoints:
  GET    /spaces/{space_id}/quiz-pool          → all quiz questions in a space (for question picker)
  POST   /spaces/{space_id}/assessments        → create a new assessment
  GET    /spaces/{space_id}/assessments        → list assessments in a space
  GET    /spaces/{space_id}/assessments/{id}   → get assessment detail
  PATCH  /spaces/{space_id}/assessments/{id}   → update assessment
  DELETE /spaces/{space_id}/assessments/{id}   → delete assessment
  POST   /spaces/{space_id}/assessments/{id}/publish → toggle publish

Learner endpoints:
  GET    /spaces/{space_id}/assessments/{id}/start   → get shuffled questions (no answers)
  POST   /spaces/{space_id}/assessments/{id}/submit  → submit attempt, get score
  GET    /spaces/{space_id}/assessments/{id}/my-attempts → learner's own attempts

Analytics (creator):
  GET    /spaces/{space_id}/assessments/{id}/analytics → all attempts + stats
"""
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.assessment import Assessment, AssessmentAttempt
from app.models.content import ContentItem, ContentOrigin, ContentStatus
from app.models.output import QuizQuestion
from app.models.space import LearningSpace, SpaceItem
from app.models.user import AxisUser

log = structlog.get_logger(__name__)
router = APIRouter(tags=["Assessments"])
_bearer = HTTPBearer()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class AssessmentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    question_ids: list[str]          # ordered list of quiz_question UUIDs
    time_limit_minutes: Optional[int] = None
    max_attempts: int = 1
    pass_pct: float = 70.0
    shuffle_questions: bool = True
    shuffle_options: bool = True
    show_answers_after: bool = True


class AssessmentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    question_ids: Optional[list[str]] = None
    time_limit_minutes: Optional[int] = None
    max_attempts: Optional[int] = None
    pass_pct: Optional[float] = None
    shuffle_questions: Optional[bool] = None
    shuffle_options: Optional[bool] = None
    show_answers_after: Optional[bool] = None


class SubmitAnswer(BaseModel):
    question_id: str
    selected_option_index: Optional[int] = None   # MCQ: 0-based
    selected_answer: Optional[str] = None          # T/F: "true"/"false"


class SubmitRequest(BaseModel):
    answers: list[SubmitAnswer]
    time_taken_seconds: Optional[int] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _require_creator(credentials: HTTPAuthorizationCredentials, db: AsyncSession) -> AxisUser:
    user = await get_current_user(credentials.credentials, db)
    if user.role not in ("admin", "creator"):
        raise HTTPException(status_code=403, detail="Creator or admin access required")
    return user


async def _get_space(space_id: uuid.UUID, db: AsyncSession) -> LearningSpace:
    r = await db.execute(select(LearningSpace).where(LearningSpace.id == space_id))
    space = r.scalar_one_or_none()
    if not space:
        raise HTTPException(status_code=404, detail="Space not found")
    return space


async def _get_assessment(assessment_id: uuid.UUID, space_id: uuid.UUID, db: AsyncSession) -> Assessment:
    r = await db.execute(
        select(Assessment).where(
            Assessment.id == assessment_id,
            Assessment.space_id == space_id,
        )
    )
    a = r.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return a


def _assessment_to_dict(a: Assessment, include_question_ids: bool = True) -> dict:
    return {
        "id": str(a.id),
        "space_id": str(a.space_id),
        "title": a.title,
        "description": a.description,
        "question_count": len(a.question_ids or []),
        "question_ids": (a.question_ids or []) if include_question_ids else [],
        "time_limit_minutes": a.time_limit_minutes,
        "max_attempts": a.max_attempts,
        "pass_pct": a.pass_pct,
        "shuffle_questions": a.shuffle_questions,
        "shuffle_options": a.shuffle_options,
        "show_answers_after": a.show_answers_after,
        "is_published": a.is_published,
        "content_item_id": str(a.content_item_id) if a.content_item_id else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


# ── Creator: quiz question pool ───────────────────────────────────────────────

@router.get("/spaces/{space_id}/quiz-pool")
async def get_space_quiz_pool(
    space_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return all active quiz questions for all content items in this space.
    Used by the assessment builder question picker.
    """
    user = await _require_creator(credentials, db)
    space = await _get_space(space_id, db)
    if space.creator_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not your space")

    # Get all content_item_ids in this space
    si_result = await db.execute(
        select(SpaceItem).where(SpaceItem.space_id == space_id)
    )
    space_items = si_result.scalars().all()
    ci_ids = [si.content_item_id for si in space_items]
    if not ci_ids:
        return {"questions": [], "total": 0}

    # Load content item titles for grouping
    ci_result = await db.execute(
        select(ContentItem).where(ContentItem.id.in_(ci_ids))
    )
    ci_map = {str(ci.id): ci for ci in ci_result.scalars().all()}

    # Load all active quiz questions
    qq_result = await db.execute(
        select(QuizQuestion)
        .where(
            QuizQuestion.content_item_id.in_(ci_ids),
            QuizQuestion.is_active.is_(True),
        )
        .order_by(QuizQuestion.content_item_id, QuizQuestion.created_at)
    )
    questions = qq_result.scalars().all()

    return {
        "questions": [
            {
                "id": str(q.id),
                "content_item_id": str(q.content_item_id),
                "content_title": ci_map.get(str(q.content_item_id), None) and ci_map[str(q.content_item_id)].title,
                "question_type": q.question_type,
                "question_text": q.question_text,
                "options": q.options,
                "correct_answer": q.correct_answer,
                "explanation": q.explanation,
                "blooms_level": q.blooms_level,
                "difficulty_label": q.difficulty_label,
                "topic_primary": q.topic_primary,
            }
            for q in questions
        ],
        "total": len(questions),
    }


# ── Creator: CRUD ─────────────────────────────────────────────────────────────

@router.post("/spaces/{space_id}/assessments", status_code=201)
async def create_assessment(
    space_id: uuid.UUID,
    body: AssessmentCreate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new assessment in a space and register it as a ContentItem."""
    user = await _require_creator(credentials, db)
    space = await _get_space(space_id, db)
    if space.creator_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not your space")

    if not body.question_ids:
        raise HTTPException(status_code=400, detail="Select at least one question")

    # Create a ContentItem to represent the assessment in the space
    ci = ContentItem(
        id=uuid.uuid4(),
        origin=ContentOrigin.SPACE.value,
        tenant_id=space.tenant_id,
        space_id=space_id,
        asset_id=uuid.uuid4(),
        content_type="assessment",
        source_url=None,
        title=body.title,
        status=ContentStatus.READY.value,
        interactions=[],
        processing_config={},
        moodle_metadata={"assessment": True},
    )
    db.add(ci)
    await db.flush()

    # Add a SpaceItem for the ContentItem
    existing_count = await db.execute(
        select(func.count()).select_from(SpaceItem).where(SpaceItem.space_id == space_id)
    )
    position = (existing_count.scalar() or 0) + 1

    si = SpaceItem(
        id=uuid.uuid4(),
        space_id=space_id,
        content_item_id=ci.id,
        position=position,
        is_visible=True,
        visible_outputs=[],
    )
    db.add(si)

    # Create the Assessment record
    assessment = Assessment(
        id=uuid.uuid4(),
        space_id=space_id,
        creator_id=user.id,
        title=body.title,
        description=body.description,
        question_ids=body.question_ids,
        time_limit_minutes=body.time_limit_minutes,
        max_attempts=body.max_attempts,
        pass_pct=body.pass_pct,
        shuffle_questions=body.shuffle_questions,
        shuffle_options=body.shuffle_options,
        show_answers_after=body.show_answers_after,
        is_published=False,
        content_item_id=ci.id,
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)

    return _assessment_to_dict(assessment)


@router.get("/spaces/{space_id}/assessments")
async def list_assessments(
    space_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _require_creator(credentials, db)
    space = await _get_space(space_id, db)
    if space.creator_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not your space")

    r = await db.execute(
        select(Assessment)
        .where(Assessment.space_id == space_id)
        .order_by(Assessment.created_at.desc())
    )
    assessments = r.scalars().all()
    return {"assessments": [_assessment_to_dict(a, include_question_ids=False) for a in assessments]}


@router.get("/spaces/{space_id}/assessments/{assessment_id}")
async def get_assessment(
    space_id: uuid.UUID,
    assessment_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await get_current_user(credentials.credentials, db)
    space = await _get_space(space_id, db)
    assessment = await _get_assessment(assessment_id, space_id, db)

    # Creators see full question_ids; learners see only published + no answers
    if user.role in ("admin", "creator") and (space.creator_id == user.id or user.role == "admin"):
        return _assessment_to_dict(assessment)

    # Learner: only show if published
    if not assessment.is_published:
        raise HTTPException(status_code=404, detail="Assessment not available")

    d = _assessment_to_dict(assessment, include_question_ids=False)
    return d


@router.patch("/spaces/{space_id}/assessments/{assessment_id}")
async def update_assessment(
    space_id: uuid.UUID,
    assessment_id: uuid.UUID,
    body: AssessmentUpdate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _require_creator(credentials, db)
    space = await _get_space(space_id, db)
    if space.creator_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not your space")

    assessment = await _get_assessment(assessment_id, space_id, db)

    if body.title is not None:
        assessment.title = body.title
        # Also update the linked content item title
        if assessment.content_item_id:
            ci_r = await db.execute(
                select(ContentItem).where(ContentItem.id == assessment.content_item_id)
            )
            ci = ci_r.scalar_one_or_none()
            if ci:
                ci.title = body.title
    if body.description is not None:
        assessment.description = body.description
    if body.question_ids is not None:
        assessment.question_ids = body.question_ids
    if body.time_limit_minutes is not None:
        assessment.time_limit_minutes = body.time_limit_minutes
    if body.max_attempts is not None:
        assessment.max_attempts = body.max_attempts
    if body.pass_pct is not None:
        assessment.pass_pct = body.pass_pct
    if body.shuffle_questions is not None:
        assessment.shuffle_questions = body.shuffle_questions
    if body.shuffle_options is not None:
        assessment.shuffle_options = body.shuffle_options
    if body.show_answers_after is not None:
        assessment.show_answers_after = body.show_answers_after

    await db.commit()
    await db.refresh(assessment)
    return _assessment_to_dict(assessment)


@router.delete("/spaces/{space_id}/assessments/{assessment_id}", status_code=204)
async def delete_assessment(
    space_id: uuid.UUID,
    assessment_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    user = await _require_creator(credentials, db)
    space = await _get_space(space_id, db)
    if space.creator_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not your space")

    assessment = await _get_assessment(assessment_id, space_id, db)
    await db.delete(assessment)
    await db.commit()


@router.post("/spaces/{space_id}/assessments/{assessment_id}/publish")
async def toggle_publish(
    space_id: uuid.UUID,
    assessment_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _require_creator(credentials, db)
    space = await _get_space(space_id, db)
    if space.creator_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not your space")

    assessment = await _get_assessment(assessment_id, space_id, db)
    assessment.is_published = not assessment.is_published
    await db.commit()
    return {"is_published": assessment.is_published}


# ── Learner: start + submit ───────────────────────────────────────────────────

@router.get("/spaces/{space_id}/assessments/{assessment_id}/start")
async def start_assessment(
    space_id: uuid.UUID,
    assessment_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return shuffled questions (without correct answers) for a learner to answer.
    Checks attempt limits before starting.
    """
    user = await get_current_user(credentials.credentials, db)
    assessment = await _get_assessment(assessment_id, space_id, db)

    if not assessment.is_published and user.role not in ("admin", "creator"):
        raise HTTPException(status_code=404, detail="Assessment not available")

    # Check attempt count
    attempt_count_r = await db.execute(
        select(func.count()).select_from(AssessmentAttempt).where(
            AssessmentAttempt.assessment_id == assessment_id,
            AssessmentAttempt.user_id == user.id,
            AssessmentAttempt.submitted_at.isnot(None),
        )
    )
    completed = attempt_count_r.scalar() or 0
    if completed >= assessment.max_attempts and user.role not in ("admin", "creator"):
        raise HTTPException(
            status_code=403,
            detail=f"Maximum attempts ({assessment.max_attempts}) reached",
        )

    # Load questions
    q_ids = [uuid.UUID(qid) for qid in (assessment.question_ids or [])]
    if not q_ids:
        raise HTTPException(status_code=400, detail="Assessment has no questions")

    qq_result = await db.execute(
        select(QuizQuestion).where(QuizQuestion.id.in_(q_ids))
    )
    qq_map = {str(q.id): q for q in qq_result.scalars().all()}

    ordered = [qq_map[str(qid)] for qid in q_ids if str(qid) in qq_map]
    if assessment.shuffle_questions:
        random.shuffle(ordered)

    def _build_options(q: QuizQuestion) -> list[dict] | None:
        if not q.options:
            return None
        opts = [{"text": o["text"]} for o in q.options]   # strip is_correct
        if assessment.shuffle_options:
            random.shuffle(opts)
        return opts

    questions_out = [
        {
            "id": str(q.id),
            "question_type": q.question_type,
            "question_text": q.question_text,
            "options": _build_options(q),
            "topic_primary": q.topic_primary,
            "blooms_level": q.blooms_level,
            "difficulty_label": q.difficulty_label,
        }
        for q in ordered
    ]

    return {
        "assessment_id": str(assessment_id),
        "title": assessment.title,
        "description": assessment.description,
        "total_questions": len(questions_out),
        "time_limit_minutes": assessment.time_limit_minutes,
        "pass_pct": assessment.pass_pct,
        "attempts_used": completed,
        "max_attempts": assessment.max_attempts,
        "questions": questions_out,
    }


@router.post("/spaces/{space_id}/assessments/{assessment_id}/submit")
async def submit_assessment(
    space_id: uuid.UUID,
    assessment_id: uuid.UUID,
    body: SubmitRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Score an attempt and persist results. Returns score + pass/fail + per-question feedback.
    """
    user = await get_current_user(credentials.credentials, db)
    assessment = await _get_assessment(assessment_id, space_id, db)

    if not assessment.is_published and user.role not in ("admin", "creator"):
        raise HTTPException(status_code=404, detail="Assessment not available")

    # Count completed attempts
    attempt_count_r = await db.execute(
        select(func.count()).select_from(AssessmentAttempt).where(
            AssessmentAttempt.assessment_id == assessment_id,
            AssessmentAttempt.user_id == user.id,
            AssessmentAttempt.submitted_at.isnot(None),
        )
    )
    completed = attempt_count_r.scalar() or 0
    if completed >= assessment.max_attempts and user.role not in ("admin", "creator"):
        raise HTTPException(status_code=403, detail="Maximum attempts reached")

    # Load questions for scoring
    q_ids = [uuid.UUID(qid) for qid in (assessment.question_ids or [])]
    qq_result = await db.execute(
        select(QuizQuestion).where(QuizQuestion.id.in_(q_ids))
    )
    qq_map = {str(q.id): q for q in qq_result.scalars().all()}

    # Score each answer
    scored: list[dict] = []
    correct_count = 0

    for ans in body.answers:
        q = qq_map.get(ans.question_id)
        if not q:
            continue

        is_correct = False
        if q.question_type == "multichoice" and q.options and ans.selected_option_index is not None:
            idx = ans.selected_option_index
            if 0 <= idx < len(q.options):
                is_correct = bool(q.options[idx].get("is_correct", False))
        elif q.question_type == "truefalse" and ans.selected_answer is not None:
            is_correct = (ans.selected_answer.lower() == (q.correct_answer or "").lower())

        if is_correct:
            correct_count += 1

        row: dict = {
            "question_id": ans.question_id,
            "question_text": q.question_text,
            "selected_option_index": ans.selected_option_index,
            "selected_answer": ans.selected_answer,
            "is_correct": is_correct,
        }
        if assessment.show_answers_after:
            row["explanation"] = q.explanation
            if q.options:
                correct_idx = next(
                    (i for i, o in enumerate(q.options) if o.get("is_correct")), None
                )
                row["correct_option_index"] = correct_idx
                row["options"] = [{"text": o["text"]} for o in q.options]   # strip is_correct
            row["show_answers"] = True
        scored.append(row)

    total = len(q_ids)
    score_pct = round((correct_count / total) * 100, 1) if total else 0
    passed = score_pct >= assessment.pass_pct

    attempt = AssessmentAttempt(
        id=uuid.uuid4(),
        assessment_id=assessment_id,
        user_id=user.id,
        attempt_number=completed + 1,
        answers=scored,
        score_pct=score_pct,
        passed=passed,
        total_questions=total,
        correct_count=correct_count,
        submitted_at=datetime.now(timezone.utc),
        time_taken_seconds=body.time_taken_seconds,
    )
    db.add(attempt)
    await db.commit()

    return {
        "attempt_id": str(attempt.id),
        "attempt_number": completed + 1,
        "score_pct": score_pct,
        "passed": passed,
        "correct_count": correct_count,
        "total_questions": total,
        "pass_pct": assessment.pass_pct,
        "time_taken_seconds": body.time_taken_seconds,
        "results": scored if assessment.show_answers_after else [],
        "attempts_used": completed + 1,
        "max_attempts": assessment.max_attempts,
    }


@router.get("/spaces/{space_id}/assessments/{assessment_id}/my-attempts")
async def get_my_attempts(
    space_id: uuid.UUID,
    assessment_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the current learner's attempts for this assessment."""
    user = await get_current_user(credentials.credentials, db)
    assessment = await _get_assessment(assessment_id, space_id, db)

    r = await db.execute(
        select(AssessmentAttempt)
        .where(
            AssessmentAttempt.assessment_id == assessment_id,
            AssessmentAttempt.user_id == user.id,
        )
        .order_by(AssessmentAttempt.attempt_number)
    )
    attempts = r.scalars().all()

    return {
        "assessment_id": str(assessment_id),
        "title": assessment.title,
        "pass_pct": assessment.pass_pct,
        "max_attempts": assessment.max_attempts,
        "attempts": [
            {
                "attempt_number": a.attempt_number,
                "score_pct": a.score_pct,
                "passed": a.passed,
                "correct_count": a.correct_count,
                "total_questions": a.total_questions,
                "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
                "time_taken_seconds": a.time_taken_seconds,
            }
            for a in attempts
        ],
        "best_score": max((a.score_pct or 0) for a in attempts) if attempts else None,
        "ever_passed": any(a.passed for a in attempts),
    }


# ── Creator analytics ─────────────────────────────────────────────────────────

@router.get("/spaces/{space_id}/assessments/{assessment_id}/analytics")
async def get_assessment_analytics(
    space_id: uuid.UUID,
    assessment_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return all attempt data + aggregate stats for a creator.
    """
    user = await _require_creator(credentials, db)
    space = await _get_space(space_id, db)
    if space.creator_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not your space")

    assessment = await _get_assessment(assessment_id, space_id, db)

    r = await db.execute(
        select(AssessmentAttempt)
        .where(AssessmentAttempt.assessment_id == assessment_id)
        .where(AssessmentAttempt.submitted_at.isnot(None))
        .order_by(AssessmentAttempt.submitted_at.desc())
    )
    attempts = r.scalars().all()

    scores = [a.score_pct for a in attempts if a.score_pct is not None]
    pass_count = sum(1 for a in attempts if a.passed)
    unique_learners = len(set(a.user_id for a in attempts))

    return {
        "assessment_id": str(assessment_id),
        "title": assessment.title,
        "total_attempts": len(attempts),
        "unique_learners": unique_learners,
        "pass_count": pass_count,
        "fail_count": len(attempts) - pass_count,
        "pass_rate_pct": round((pass_count / len(attempts)) * 100, 1) if attempts else 0,
        "avg_score_pct": round(sum(scores) / len(scores), 1) if scores else 0,
        "highest_score": max(scores) if scores else 0,
        "lowest_score": min(scores) if scores else 0,
        "pass_threshold": assessment.pass_pct,
        "attempts": [
            {
                "user_id": a.user_id,
                "attempt_number": a.attempt_number,
                "score_pct": a.score_pct,
                "passed": a.passed,
                "correct_count": a.correct_count,
                "total_questions": a.total_questions,
                "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
                "time_taken_seconds": a.time_taken_seconds,
            }
            for a in attempts
        ],
    }


# ── Lookup by content_item_id (for learner content page routing) ──────────────

@router.get("/spaces/{space_id}/content/{content_item_id}/assessment-info")
async def get_assessment_by_content(
    space_id: uuid.UUID,
    content_item_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Look up the assessment linked to a content item. Used by the learner content page."""
    user = await get_current_user(credentials.credentials, db)
    r = await db.execute(
        select(Assessment).where(
            Assessment.space_id == space_id,
            Assessment.content_item_id == content_item_id,
        )
    )
    assessment = r.scalar_one_or_none()
    if not assessment:
        raise HTTPException(status_code=404, detail="No assessment linked to this content item")
    if not assessment.is_published and user.role not in ("admin", "creator"):
        raise HTTPException(status_code=404, detail="Assessment not available")
    return {
        "assessment_id": str(assessment.id),
        "title": assessment.title,
        "description": assessment.description,
        "question_count": len(assessment.question_ids or []),
        "time_limit_minutes": assessment.time_limit_minutes,
        "max_attempts": assessment.max_attempts,
        "pass_pct": assessment.pass_pct,
        "is_published": assessment.is_published,
    }


# ── Learner: all assessment history in a space (for progress page) ────────────

@router.get("/spaces/{space_id}/me/assessment-history")
async def get_my_assessment_history(
    space_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return all published assessments in a space with the learner's own attempts for each."""
    user = await get_current_user(credentials.credentials, db)

    # All published assessments in this space
    r = await db.execute(
        select(Assessment)
        .where(Assessment.space_id == space_id, Assessment.is_published == True)
        .order_by(Assessment.created_at)
    )
    assessments = r.scalars().all()

    if not assessments:
        return {"space_id": str(space_id), "assessments": []}

    assessment_ids = [a.id for a in assessments]

    # All learner's attempts for assessments in this space
    r2 = await db.execute(
        select(AssessmentAttempt)
        .where(
            AssessmentAttempt.assessment_id.in_(assessment_ids),
            AssessmentAttempt.user_id == user.id,
        )
        .order_by(AssessmentAttempt.submitted_at)
    )
    all_attempts = r2.scalars().all()

    # Group attempts by assessment_id
    from collections import defaultdict
    attempt_map: dict = defaultdict(list)
    for attempt in all_attempts:
        attempt_map[attempt.assessment_id].append(attempt)

    result = []
    for a in assessments:
        my_attempts = attempt_map.get(a.id, [])
        scores = [at.score_pct for at in my_attempts if at.score_pct is not None]
        result.append({
            "assessment_id": str(a.id),
            "title": a.title,
            "description": a.description,
            "question_count": len(a.question_ids or []),
            "time_limit_minutes": a.time_limit_minutes,
            "max_attempts": a.max_attempts,
            "pass_pct": a.pass_pct,
            "content_item_id": str(a.content_item_id) if a.content_item_id else None,
            "attempts": [
                {
                    "attempt_number": at.attempt_number,
                    "score_pct": at.score_pct,
                    "passed": at.passed,
                    "correct_count": at.correct_count,
                    "total_questions": at.total_questions,
                    "submitted_at": at.submitted_at.isoformat() if at.submitted_at else None,
                    "time_taken_seconds": at.time_taken_seconds,
                }
                for at in my_attempts
            ],
            "best_score": max(scores) if scores else None,
            "ever_passed": any(at.passed for at in my_attempts),
            "attempt_count": len(my_attempts),
        })

    return {"space_id": str(space_id), "assessments": result}


# ── Creator: all assessments with analytics in one call (for report page) ─────

@router.get("/spaces/{space_id}/assessments-analytics")
async def get_assessments_analytics_overview(
    space_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return all assessments in a space with aggregate analytics. Creator/admin only."""
    user = await _require_creator(credentials, db)
    space = await _get_space(space_id, db)
    if space.creator_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not your space")

    r = await db.execute(
        select(Assessment)
        .where(Assessment.space_id == space_id)
        .order_by(Assessment.created_at)
    )
    assessments = r.scalars().all()

    if not assessments:
        return {"space_id": str(space_id), "assessments": []}

    assessment_ids = [a.id for a in assessments]

    r2 = await db.execute(
        select(AssessmentAttempt)
        .where(
            AssessmentAttempt.assessment_id.in_(assessment_ids),
            AssessmentAttempt.submitted_at.isnot(None),
        )
    )
    all_attempts = r2.scalars().all()

    from collections import defaultdict
    attempt_map: dict = defaultdict(list)
    for attempt in all_attempts:
        attempt_map[attempt.assessment_id].append(attempt)

    result = []
    for a in assessments:
        attempts = attempt_map.get(a.id, [])
        scores = [at.score_pct for at in attempts if at.score_pct is not None]
        pass_count = sum(1 for at in attempts if at.passed)
        unique = len(set(at.user_id for at in attempts))
        result.append({
            "assessment_id": str(a.id),
            "title": a.title,
            "is_published": a.is_published,
            "question_count": len(a.question_ids or []),
            "time_limit_minutes": a.time_limit_minutes,
            "pass_pct": a.pass_pct,
            "max_attempts": a.max_attempts,
            "content_item_id": str(a.content_item_id) if a.content_item_id else None,
            "total_attempts": len(attempts),
            "unique_learners": unique,
            "pass_count": pass_count,
            "fail_count": len(attempts) - pass_count,
            "pass_rate_pct": round((pass_count / len(attempts)) * 100, 1) if attempts else 0,
            "avg_score_pct": round(sum(scores) / len(scores), 1) if scores else 0,
        })

    return {"space_id": str(space_id), "assessments": result}


# ── Adaptive Learning — Phase A: recommendations after failed attempt ──────────

@router.get("/spaces/{space_id}/assessments/{assessment_id}/recommendations")
async def get_assessment_recommendations(
    space_id: uuid.UUID,
    assessment_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return content sections the learner should review based on their wrong answers.

    Logic:
      1. Find the learner's most recent submitted attempt.
      2. Collect question_ids where is_correct == False.
      3. Join to quiz_questions → get content_item_id + blooms_level per question.
      4. Group by content_item_id, count wrongs, gather Bloom's levels.
      5. Return ordered list (most wrongs first) with content item title + link hint.
    """
    user = await get_current_user(credentials.credentials, db)

    # Verify assessment exists in this space
    r = await db.execute(
        select(Assessment).where(
            Assessment.id == assessment_id,
            Assessment.space_id == space_id,
        )
    )
    assessment = r.scalars().first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    # Get learner's most recent completed attempt
    r2 = await db.execute(
        select(AssessmentAttempt)
        .where(
            AssessmentAttempt.assessment_id == assessment_id,
            AssessmentAttempt.user_id == user.id,
            AssessmentAttempt.submitted_at.isnot(None),
        )
        .order_by(AssessmentAttempt.submitted_at.desc())
        .limit(1)
    )
    attempt = r2.scalars().first()
    if not attempt:
        return {"recommendations": [], "attempt_score_pct": None, "passed": None}

    # If they passed, return empty (no nudge needed)
    if attempt.passed:
        return {
            "recommendations": [],
            "attempt_score_pct": attempt.score_pct,
            "passed": True,
        }

    # Collect wrong question IDs
    wrong_ids: list[uuid.UUID] = []
    for ans in (attempt.answers or []):
        if not ans.get("is_correct", True):
            try:
                wrong_ids.append(uuid.UUID(ans["question_id"]))
            except (KeyError, ValueError):
                pass

    if not wrong_ids:
        return {
            "recommendations": [],
            "attempt_score_pct": attempt.score_pct,
            "passed": False,
        }

    # Fetch those quiz questions
    r3 = await db.execute(
        select(QuizQuestion).where(QuizQuestion.id.in_(wrong_ids))
    )
    wrong_questions = r3.scalars().all()

    # Group by content_item_id
    from collections import defaultdict
    grouped: dict[str, dict] = defaultdict(lambda: {
        "wrong_count": 0,
        "blooms_levels": set(),
        "difficulty_labels": set(),
        "question_texts": [],
    })
    ci_ids: set[uuid.UUID] = set()

    for q in wrong_questions:
        key = str(q.content_item_id)
        grouped[key]["wrong_count"] += 1
        if q.blooms_level:
            grouped[key]["blooms_levels"].add(q.blooms_level)
        if q.difficulty_label:
            grouped[key]["difficulty_labels"].add(q.difficulty_label)
        grouped[key]["question_texts"].append(q.question_text[:120])
        ci_ids.add(q.content_item_id)

    # Fetch content item titles
    r4 = await db.execute(
        select(ContentItem).where(ContentItem.id.in_(ci_ids))
    )
    ci_map = {str(ci.id): ci for ci in r4.scalars().all()}

    # Build recommendations sorted by wrong_count desc
    recommendations = []
    for ci_id, data in sorted(grouped.items(), key=lambda x: -x[1]["wrong_count"]):
        ci = ci_map.get(ci_id)
        if not ci:
            continue
        recommendations.append({
            "content_item_id": ci_id,
            "title": ci.title,
            "wrong_count": data["wrong_count"],
            "blooms_levels": sorted(data["blooms_levels"]),
            "difficulty_labels": sorted(data["difficulty_labels"]),
            "sample_questions": data["question_texts"][:2],
        })

    return {
        "recommendations": recommendations,
        "attempt_score_pct": attempt.score_pct,
        "passed": False,
        "wrong_total": len(wrong_ids),
        "content_sections_affected": len(recommendations),
    }
