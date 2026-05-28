"""
Interactive Content API — Phase 14.

GET  /api/v1/content/{id}/interactions               → get interactions list (creator + learner)
PUT  /api/v1/content/{id}/interactions               → save/replace interactions (creator/admin)
POST /api/v1/content/{id}/interactions/respond       → submit a learner answer
GET  /api/v1/content/{id}/interactions/my-responses  → learner's own attempts
GET  /api/v1/content/{id}/interactions/responses     → all responses — creator analytics
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import aiofiles
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Security, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user, get_current_user_dep
from app.core.database import get_db
from app.models.content import ContentItem
from app.models.interaction import InteractionResponse

log = structlog.get_logger(__name__)
router = APIRouter(tags=["Interactive Content"])
_bearer = HTTPBearer()


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class InteractionItem(BaseModel):
    """Single interaction object stored in the interactions JSON array."""
    index: int
    timestamp: float          # seconds from start of video
    type: str                 # "mcq" | "truefalse" | "callout"
    question: str | None = None
    options: list[str] | None = None   # MCQ only — 4 options
    correct_index: int | None = None   # MCQ — 0-based index of correct option
    correct_answer: bool | None = None # T/F — True or False
    explanation: str | None = None     # shown after answer
    text: str | None = None            # callout text

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"mcq", "truefalse", "callout"}
        if v not in allowed:
            raise ValueError(f"type must be one of {allowed}")
        return v


class InteractionsSaveRequest(BaseModel):
    interactions: list[InteractionItem]
    title: Optional[str] = None   # if provided, updates content_item.title


class InteractionsResponse(BaseModel):
    content_item_id: str
    interactions: list[dict]


class RespondRequest(BaseModel):
    interaction_index: int
    selected_answer: str   # "0","1","2","3" for MCQ; "true"/"false" for T/F
    time_taken_seconds: int | None = None


class RespondResult(BaseModel):
    is_correct: bool | None
    correct_answer: str | None   # "0"/"1"/"2"/"3" or "true"/"false" — shown to learner
    explanation: str | None
    message: str


class MyResponseItem(BaseModel):
    interaction_index: int
    selected_answer: str
    is_correct: bool | None
    answered_at: datetime


class AnalyticsQuestion(BaseModel):
    interaction_index: int
    timestamp: float
    type: str
    question: str | None
    total_attempts: int
    correct_attempts: int
    pct_correct: float
    answer_distribution: dict[str, int]  # answer_value → count


class AnalyticsResponse(BaseModel):
    content_item_id: str
    total_learners: int
    questions: list[AnalyticsQuestion]


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_content_item(content_id: uuid.UUID, db: AsyncSession) -> ContentItem:
    result = await db.execute(
        select(ContentItem).where(ContentItem.id == content_id)
    )
    ci = result.scalar_one_or_none()
    if ci is None:
        raise HTTPException(status_code=404, detail="Content item not found")
    return ci


def _eval_answer(interaction: dict, selected_answer: str) -> tuple[bool | None, str | None]:
    """Return (is_correct, correct_answer_string) for an interaction."""
    itype = interaction.get("type")
    if itype == "callout":
        return None, None
    if itype == "mcq":
        correct_index = interaction.get("correct_index")
        if correct_index is None:
            return None, None
        is_correct = selected_answer == str(correct_index)
        return is_correct, str(correct_index)
    if itype == "truefalse":
        correct = interaction.get("correct_answer")
        if correct is None:
            return None, None
        correct_str = "true" if correct else "false"
        is_correct = selected_answer.lower() == correct_str
        return is_correct, correct_str
    return None, None


# ── GET interactions ───────────────────────────────────────────────────────────

@router.get("/content/{content_id}/interactions", response_model=InteractionsResponse)
async def get_interactions(
    content_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> InteractionsResponse:
    """Get the interactions list for a content item. Creator, admin, and learner."""
    await get_current_user(credentials.credentials, db)  # any authenticated user
    ci = await _get_content_item(content_id, db)
    return InteractionsResponse(
        content_item_id=str(ci.id),
        interactions=ci.interactions or [],
    )


# ── PUT interactions (creator/admin save) ──────────────────────────────────────

@router.put("/content/{content_id}/interactions", response_model=InteractionsResponse)
async def save_interactions(
    content_id: uuid.UUID,
    req: InteractionsSaveRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> InteractionsResponse:
    """
    Replace the full interactions list for a content item.
    Creator must own the space this content belongs to. Admin can update any.
    """
    user = await get_current_user(credentials.credentials, db)
    ci = await _get_content_item(content_id, db)

    # Permission: creator must own the space; admin always allowed
    if user.role == "learner":
        raise HTTPException(status_code=403, detail="Learners cannot edit interactions")
    if user.role == "creator":
        # Library items (space_id=None) are owned by tenant — allow any creator in tenant
        # Space-linked items: verify creator owns the space
        if ci.space_id is not None:
            from app.models.space import SpaceItem, LearningSpace
            result = await db.execute(
                select(LearningSpace)
                .join(SpaceItem, SpaceItem.space_id == LearningSpace.id)
                .where(SpaceItem.content_item_id == ci.id, LearningSpace.creator_id == user.id)
                .limit(1)
            )
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="You don't own this content item")

    # Re-index to ensure sequential, sorted by timestamp
    items = sorted(req.interactions, key=lambda x: x.timestamp)
    for i, item in enumerate(items):
        item.index = i

    ci.interactions = [item.model_dump() for item in items]
    if req.title is not None and req.title.strip():
        ci.title = req.title.strip()
    await db.commit()
    await db.refresh(ci)

    log.info("interactions_saved", content_id=str(ci.id), count=len(items), user=str(user.id))
    return InteractionsResponse(
        content_item_id=str(ci.id),
        interactions=ci.interactions,
    )


# ── POST respond ───────────────────────────────────────────────────────────────

@router.post("/content/{content_id}/interactions/respond", response_model=RespondResult)
async def submit_response(
    content_id: uuid.UUID,
    req: RespondRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> RespondResult:
    """
    Learner submits an answer to one interaction.
    Returns whether they were correct, the correct answer, and the explanation.
    Every attempt is stored (first attempt used for scoring in analytics).
    """
    user = await get_current_user(credentials.credentials, db)
    ci = await _get_content_item(content_id, db)

    interactions = ci.interactions or []
    matching = [i for i in interactions if i.get("index") == req.interaction_index]
    if not matching:
        raise HTTPException(
            status_code=404,
            detail=f"Interaction index {req.interaction_index} not found"
        )
    interaction = matching[0]

    is_correct, correct_answer = _eval_answer(interaction, req.selected_answer)
    explanation = interaction.get("explanation")

    # Store the attempt
    response = InteractionResponse(
        id=uuid.uuid4(),
        content_item_id=ci.id,
        user_id=user.id,
        interaction_index=req.interaction_index,
        selected_answer=req.selected_answer,
        is_correct=is_correct,
        time_taken_seconds=req.time_taken_seconds,
        answered_at=datetime.now(timezone.utc),
    )
    db.add(response)
    await db.commit()

    itype = interaction.get("type")
    if itype == "callout":
        message = "Callout noted."
    elif is_correct:
        message = "Correct! Well done."
    else:
        message = "Not quite — see the correct answer below."

    log.info(
        "interaction_responded",
        content_id=str(ci.id),
        user=str(user.id),
        index=req.interaction_index,
        is_correct=is_correct,
    )
    return RespondResult(
        is_correct=is_correct,
        correct_answer=correct_answer,
        explanation=explanation,
        message=message,
    )


# ── GET my-responses (learner) ─────────────────────────────────────────────────

@router.get(
    "/content/{content_id}/interactions/my-responses",
    response_model=list[MyResponseItem],
)
async def my_responses(
    content_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> list[MyResponseItem]:
    """Learner's own attempts for a content item — used to restore state on re-open."""
    user = await get_current_user(credentials.credentials, db)
    await _get_content_item(content_id, db)

    result = await db.execute(
        select(InteractionResponse)
        .where(
            InteractionResponse.content_item_id == content_id,
            InteractionResponse.user_id == user.id,
        )
        .order_by(InteractionResponse.answered_at.asc())
    )
    rows = result.scalars().all()
    return [
        MyResponseItem(
            interaction_index=r.interaction_index,
            selected_answer=r.selected_answer,
            is_correct=r.is_correct,
            answered_at=r.answered_at,
        )
        for r in rows
    ]


# ── GET responses (creator analytics) ─────────────────────────────────────────

@router.get(
    "/content/{content_id}/interactions/responses",
    response_model=AnalyticsResponse,
)
async def get_analytics(
    content_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsResponse:
    """
    Creator/admin analytics: per-question response stats.
    Only first attempt per learner per question is counted.
    """
    user = await get_current_user(credentials.credentials, db)
    if user.role == "learner":
        raise HTTPException(status_code=403, detail="Learners cannot view analytics")

    ci = await _get_content_item(content_id, db)
    interactions = ci.interactions or []

    # Fetch all responses for this content item
    result = await db.execute(
        select(InteractionResponse)
        .where(InteractionResponse.content_item_id == content_id)
        .order_by(InteractionResponse.answered_at.asc())
    )
    all_responses = result.scalars().all()

    # Keep only first attempt per (user, interaction_index)
    seen: set[tuple] = set()
    first_attempts: list[InteractionResponse] = []
    for r in all_responses:
        key = (r.user_id, r.interaction_index)
        if key not in seen:
            seen.add(key)
            first_attempts.append(r)

    total_learners = len({r.user_id for r in first_attempts})

    questions: list[AnalyticsQuestion] = []
    for interaction in interactions:
        idx = interaction.get("index", 0)
        itype = interaction.get("type", "")
        if itype == "callout":
            continue  # callouts have no right/wrong

        q_responses = [r for r in first_attempts if r.interaction_index == idx]
        total = len(q_responses)
        correct = sum(1 for r in q_responses if r.is_correct)

        # Answer distribution
        dist: dict[str, int] = {}
        for r in q_responses:
            dist[r.selected_answer] = dist.get(r.selected_answer, 0) + 1

        questions.append(AnalyticsQuestion(
            interaction_index=idx,
            timestamp=interaction.get("timestamp", 0),
            type=itype,
            question=interaction.get("question"),
            total_attempts=total,
            correct_attempts=correct,
            pct_correct=round(correct / total * 100, 1) if total > 0 else 0.0,
            answer_distribution=dist,
        ))

    return AnalyticsResponse(
        content_item_id=str(ci.id),
        total_learners=total_learners,
        questions=questions,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /interactive/library — list all content items that have interactions
# ─────────────────────────────────────────────────────────────────────────────

class LibraryItem(BaseModel):
    content_item_id: str
    title: Optional[str]
    content_type: str
    source_url: Optional[str]
    interaction_count: int
    space_id: Optional[str]
    space_title: Optional[str]
    created_at: str
    updated_at: str


class LibraryResponse(BaseModel):
    items: list[LibraryItem]


@router.get("/interactive/library", response_model=LibraryResponse)
async def get_interactive_library(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> LibraryResponse:
    """
    Return all content items that have at least one interaction attached,
    scoped to the current user's tenant.
    """
    from app.models.space import LearningSpace
    from sqlalchemy import func as _func

    user = await get_current_user(credentials.credentials, db)

    # Content items with non-empty interactions JSONB array
    result = await db.execute(
        select(ContentItem)
        .where(
            ContentItem.tenant_id == user.tenant_id,
            ContentItem.interactions.isnot(None),
            func.jsonb_array_length(ContentItem.interactions) > 0,
        )
        .order_by(ContentItem.updated_at.desc())
    )
    items = result.scalars().all()

    # Collect space IDs to resolve titles
    space_ids = {str(ci.space_id) for ci in items if ci.space_id}
    space_map: dict[str, str] = {}
    if space_ids:
        space_rows = (
            await db.execute(
                select(LearningSpace.id, LearningSpace.title).where(
                    LearningSpace.id.in_([uuid.UUID(s) for s in space_ids])
                )
            )
        ).all()
        space_map = {str(r.id): r.title for r in space_rows}

    return LibraryResponse(
        items=[
            LibraryItem(
                content_item_id=str(ci.id),
                title=ci.title,
                content_type=str(ci.content_type.value) if hasattr(ci.content_type, "value") else str(ci.content_type),
                source_url=ci.source_url,
                interaction_count=len(ci.interactions) if ci.interactions else 0,
                space_id=str(ci.space_id) if ci.space_id else None,
                space_title=space_map.get(str(ci.space_id)) if ci.space_id else None,
                created_at=ci.created_at.isoformat() if ci.created_at else "",
                updated_at=ci.updated_at.isoformat() if ci.updated_at else "",
            )
            for ci in items
        ]
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /interactive/create — create a fresh IC content item (no space link)
# ─────────────────────────────────────────────────────────────────────────────

class CreateInteractivePayload(BaseModel):
    source_url: str
    content_type: str   # "youtube" | "vimeo" | "direct"
    title: Optional[str] = None
    interactions: list[dict] = []


class CreateInteractiveResponse(BaseModel):
    content_item_id: str
    title: Optional[str]


_CT_MAP = {
    "youtube": "youtube",
    "vimeo":   "vimeo",
    "direct":  "video_upload",
}


@router.post(
    "/interactive/create",
    response_model=CreateInteractiveResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_interactive_content(
    payload: CreateInteractivePayload,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> CreateInteractiveResponse:
    """
    Create a brand-new ContentItem that holds interactive annotations.
    The item is NOT linked to any space (space_id=None) — creators attach
    it to a space later from the Learning Space page.
    """
    from app.models.content import ContentItem, ContentOrigin, ContentStatus

    user = await get_current_user(credentials.credentials, db)
    if user.role not in ("admin", "creator"):
        raise HTTPException(status_code=403, detail="Creator or admin access required")

    ct_value = _CT_MAP.get(payload.content_type, "youtube")
    title = payload.title or payload.source_url

    new_item = ContentItem(
        id=uuid.uuid4(),
        origin=ContentOrigin.SPACE.value,
        tenant_id=user.tenant_id,
        space_id=None,
        asset_id=uuid.uuid4(),          # unique dedup key for space-origin
        content_type=ct_value,
        source_url=payload.source_url,
        title=title,
        status=ContentStatus.READY.value,
        interactions=payload.interactions,
        processing_config={},
        moodle_metadata={},
    )
    db.add(new_item)
    await db.commit()
    await db.refresh(new_item)

    return CreateInteractiveResponse(
        content_item_id=str(new_item.id),
        title=new_item.title,
    )


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /content/{content_id}/interactions — clear all interactions
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/content/{content_id}/interactions", status_code=204)
async def delete_interactions(
    content_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Clear all interactions from a content item (keeps the item itself)."""
    user = await get_current_user(credentials.credentials, db)
    if user.role not in ("admin", "creator"):
        raise HTTPException(status_code=403, detail="Creator or admin access required")

    ci = await _get_content_item(content_id, db)
    ci.interactions = []
    await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# IC Video Upload — POST /interactive/upload-video
# ─────────────────────────────────────────────────────────────────────────────

from app.api.v1.axis_admin import get_upload_limit_bytes
_IC_UPLOAD_DIR = os.getenv("IC_UPLOAD_DIR", "/data/ic_uploads")
_IC_UPLOAD_URL_BASE = os.getenv("IC_UPLOAD_URL_BASE", "https://axisai.edzlms.com/ic-uploads")
_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi"}
_MAX_VIDEO_BYTES = 500 * 1024 * 1024  # 500 MB


class VideoUploadResponse(BaseModel):
    content_item_id: str
    title: str
    source_url: str
    file_size_mb: float


@router.post(
    "/interactive/upload-video",
    response_model=VideoUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_ic_video(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> VideoUploadResponse:
    """
    Upload a local video file for use as interactive content source.

    Accepts MP4, MOV, WebM, MKV, AVI (max 500 MB).
    Creates a ContentItem with content_type=video_upload and stores the file
    under /data/ic_uploads/<uuid>.<ext>. Returns a playable URL pointing to
    https://axisai.edzlms.com/ic-uploads/<uuid>.<ext>.
    """
    from app.models.content import ContentItem, ContentOrigin, ContentStatus

    user = await get_current_user(credentials.credentials, db)
    if user.role not in ("admin", "creator"):
        raise HTTPException(status_code=403, detail="Creator or admin access required")

    # Validate extension
    original_name = file.filename or "video"
    _, ext = os.path.splitext(original_name.lower())
    if ext not in _ALLOWED_VIDEO_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(_ALLOWED_VIDEO_EXTS)}",
        )

    # Read content (stream to avoid memory spike)
    os.makedirs(_IC_UPLOAD_DIR, exist_ok=True)
    file_id = str(uuid.uuid4())
    filename = f"{file_id}{ext}"
    dest = os.path.join(_IC_UPLOAD_DIR, filename)

    total_bytes = 0
    async with aiofiles.open(dest, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)  # 1 MB chunks
            if not chunk:
                break
            total_bytes += len(chunk)
            _max_video_bytes = await get_upload_limit_bytes(db)
            if total_bytes > _max_video_bytes:
                out.close()
                os.remove(dest)
                raise HTTPException(status_code=413, detail=f"File too large (max {_max_video_bytes // 1024 // 1024} MB). Ask your admin to increase the upload limit.")
            await out.write(chunk)

    source_url = f"{_IC_UPLOAD_URL_BASE}/{filename}"
    item_title = title.strip() or original_name

    new_item = ContentItem(
        id=uuid.uuid4(),
        origin=ContentOrigin.SPACE.value,
        tenant_id=user.tenant_id,
        space_id=None,
        asset_id=uuid.uuid4(),
        content_type="video_upload",
        source_url=source_url,
        title=item_title,
        status=ContentStatus.READY.value,
        interactions=[],
        processing_config={},
        moodle_metadata={"uploaded_filename": filename, "file_size_bytes": total_bytes},
    )
    db.add(new_item)
    await db.commit()
    await db.refresh(new_item)

    log.info(
        "ic_video_uploaded",
        content_item_id=str(new_item.id),
        filename=filename,
        size_mb=round(total_bytes / 1024 / 1024, 2),
        user_id=user.id,
    )

    return VideoUploadResponse(
        content_item_id=str(new_item.id),
        title=item_title,
        source_url=source_url,
        file_size_mb=round(total_bytes / 1024 / 1024, 2),
    )


@router.get("/ic-uploads/{filename}", include_in_schema=False)
async def serve_ic_upload(filename: str) -> FileResponse:
    """Serve an uploaded IC video file (no auth — URL is opaque UUID)."""
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = os.path.join(_IC_UPLOAD_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Video not found")
    ext = filename.rsplit(".", 1)[-1].lower()
    media_type = {
        "mp4": "video/mp4",
        "mov": "video/quicktime",
        "webm": "video/webm",
        "mkv": "video/x-matroska",
        "avi": "video/x-msvideo",
    }.get(ext, "video/mp4")
    return FileResponse(path, media_type=media_type)


# ─────────────────────────────────────────────────────────────────────────────
# AI: suggest questions for interactive PDF / slides
# ─────────────────────────────────────────────────────────────────────────────

class SuggestQuestionsRequest(BaseModel):
    count: int = 5   # number of questions to generate; creator-controlled


@router.post("/content/{item_id}/suggest-questions")
async def suggest_questions(
    item_id: uuid.UUID,
    req: SuggestQuestionsRequest = SuggestQuestionsRequest(),
    user=Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    POST /api/v1/content/{item_id}/suggest-questions
    Body (optional): {"count": 5}   — number of questions to generate (1-25)

    Requires: admin or creator role.

    Reads the extracted text for the content item and calls the configured
    AI fast-model to generate MCQ questions suitable for embedding in the
    interactive PDF or slides.

    Returns:
        {
          "questions": [
            {
              "page_num": int,
              "type": "mcq",
              "question": str,
              "options": [str, str, str, str],
              "correct_index": int,
              "explanation": str
            },
            ...
          ],
          "total": int,
          "model_used": str
        }
    """
    if user.role not in ("admin", "creator"):
        raise HTTPException(status_code=403, detail="Creator or admin role required")

    # Clamp count to a safe range
    count = max(1, min(25, req.count))

    # Fetch content item
    r = await db.execute(select(ContentItem).where(ContentItem.id == item_id))
    item = r.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Content item not found")

    # Fetch extracted text
    from app.models.content import ExtractedContent
    ec_r = await db.execute(
        select(ExtractedContent).where(ExtractedContent.content_item_id == item_id)
    )
    ec = ec_r.scalar_one_or_none()
    if not ec or not ec.raw_text:
        raise HTTPException(
            status_code=422,
            detail="No extracted text found. Process the content first.",
        )

    # Truncate to ~12 000 chars to stay within context limits
    text_snippet = ec.raw_text[:12_000]

    # ── Resolve AI model from admin settings (never hardcode) ────────────────
    from app.api.v1.axis_admin import get_current_ai_models as _get_ai_models
    _main_model, fast_model = await _get_ai_models(db)

    prompt = f"""You are an expert instructional designer. Generate exactly {count} multiple-choice questions
based on the following content. The content has multiple pages; estimate which page each question
relates to (use page 1 if uncertain).

For each question produce:
- page_num (integer, 1-based)
- question (concise, testing understanding — not recall of trivial facts)
- options (array of exactly 4 strings — one correct, three plausible distractors)
- correct_index (0-based integer pointing to the correct option)
- explanation (1-2 sentences explaining why the answer is correct)

Respond ONLY with valid JSON in this exact schema — no markdown fences, no extra keys:
{{
  "questions": [
    {{
      "page_num": 1,
      "question": "...",
      "options": ["A", "B", "C", "D"],
      "correct_index": 0,
      "explanation": "..."
    }}
  ]
}}

CONTENT:
{text_snippet}
"""

    import litellm
    import json as _json

    try:
        response = await litellm.acompletion(
            model=fast_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=300 * count,   # ~300 tokens per question
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        data = _json.loads(raw)
        questions = data.get("questions", [])

        # Normalise: enforce type + safe page_num
        for q in questions:
            q["type"] = "mcq"
            q["page_num"] = max(1, int(q.get("page_num", 1)))

        return {"questions": questions, "total": len(questions), "model_used": fast_model}

    except Exception as exc:
        log.error("suggest_questions_failed", item_id=str(item_id), model=fast_model, error=str(exc))
        raise HTTPException(status_code=500, detail=f"AI generation failed: {exc}")
