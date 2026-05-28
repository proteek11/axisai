"""
Interactive PDF API — PF-05.

Endpoints (all JWT-authed via axis_access cookie):

  GET  /api/v1/library/{id}/pdf-serve          → stream raw PDF bytes (for pdf.js)
  GET  /api/v1/library/{id}/pdf-annotations    → get learner's annotations for this PDF
  POST /api/v1/library/{id}/pdf-annotations    → create/update annotation
  DELETE /api/v1/library/{id}/pdf-annotations/{ann_id} → delete annotation
  POST /api/v1/library/{id}/pdf-respond        → submit answer to an embedded question
  GET  /api/v1/library/{id}/pdf-responses      → get learner's own responses
"""
import uuid
from pathlib import Path
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.jwt import decode_access_token
from app.models.content import ContentItem, ContentType
from app.models.interaction import InteractionResponse
from app.models.pdf_annotation import PDFAnnotation
from app.models.user import AxisUser

log = structlog.get_logger(__name__)
router = APIRouter(tags=["Interactive PDF"])
security = HTTPBearer()


# ── Auth helper ───────────────────────────────────────────────────────────────

async def _get_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> AxisUser:
    payload = decode_access_token(creds.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    r = await db.execute(select(AxisUser).where(AxisUser.id == uuid.UUID(payload["sub"])))
    user = r.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def _get_pdf_item(content_id: uuid.UUID, db: AsyncSession) -> ContentItem:
    r = await db.execute(select(ContentItem).where(ContentItem.id == content_id))
    ci = r.scalar_one_or_none()
    if not ci:
        raise HTTPException(status_code=404, detail="Content not found")
    if ci.content_type not in (ContentType.PDF, ContentType.INTERACTIVE_PDF):
        raise HTTPException(status_code=400, detail="Content is not a PDF")
    return ci


# ── Schemas ───────────────────────────────────────────────────────────────────

class AnnotationCreate(BaseModel):
    page_num: int
    annotation_type: str = "highlight"   # highlight | note | underline
    content: str
    position_data: dict = {}
    color: str = "#FFF176"


class AnnotationUpdate(BaseModel):
    content: Optional[str] = None
    color: Optional[str] = None


class PDFResponse(BaseModel):
    interaction_index: int
    selected_answer: str
    time_taken_seconds: Optional[int] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/library/{content_id}/pdf-serve")
async def serve_pdf(
    content_id: uuid.UUID,
    user: AxisUser = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Stream the raw PDF bytes for rendering in pdf.js.
    Reads from the local file:// path stored in source_url.
    """
    ci = await _get_pdf_item(content_id, db)

    source = ci.source_url or ""
    if source.startswith("file://"):
        file_path = Path(source[7:])
    else:
        # Not a local file — redirect or proxy-fetch
        raise HTTPException(status_code=400, detail="PDF is not a local upload")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on server")

    pdf_bytes = file_path.read_bytes()
    safe_title = (ci.title or "document").replace(" ", "_")[:40]

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{safe_title}.pdf"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/library/{content_id}/pdf-annotations")
async def list_annotations(
    content_id: uuid.UUID,
    user: AxisUser = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Get all annotations made by the logged-in learner on this PDF."""
    await _get_pdf_item(content_id, db)

    r = await db.execute(
        select(PDFAnnotation).where(
            PDFAnnotation.content_item_id == content_id,
            PDFAnnotation.user_id == user.id,
        ).order_by(PDFAnnotation.page_num, PDFAnnotation.created_at)
    )
    annotations = r.scalars().all()

    return [
        {
            "id": str(a.id),
            "page_num": a.page_num,
            "annotation_type": a.annotation_type,
            "content": a.content,
            "position_data": a.position_data,
            "color": a.color,
            "created_at": a.created_at.isoformat(),
        }
        for a in annotations
    ]


@router.post("/library/{content_id}/pdf-annotations", status_code=201)
async def create_annotation(
    content_id: uuid.UUID,
    body: AnnotationCreate,
    user: AxisUser = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Save a new highlight, underline, or note annotation."""
    await _get_pdf_item(content_id, db)

    ann = PDFAnnotation(
        user_id=user.id,
        content_item_id=content_id,
        page_num=body.page_num,
        annotation_type=body.annotation_type,
        content=body.content,
        position_data=body.position_data,
        color=body.color,
    )
    db.add(ann)
    await db.commit()
    await db.refresh(ann)

    return {
        "id": str(ann.id),
        "page_num": ann.page_num,
        "annotation_type": ann.annotation_type,
        "content": ann.content,
        "position_data": ann.position_data,
        "color": ann.color,
        "created_at": ann.created_at.isoformat(),
    }


@router.delete("/library/{content_id}/pdf-annotations/{ann_id}", status_code=204)
async def delete_annotation(
    content_id: uuid.UUID,
    ann_id: uuid.UUID,
    user: AxisUser = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an annotation (only the owner can delete)."""
    r = await db.execute(
        select(PDFAnnotation).where(
            PDFAnnotation.id == ann_id,
            PDFAnnotation.user_id == user.id,
            PDFAnnotation.content_item_id == content_id,
        )
    )
    ann = r.scalar_one_or_none()
    if not ann:
        raise HTTPException(status_code=404, detail="Annotation not found")

    await db.delete(ann)
    await db.commit()


@router.post("/library/{content_id}/pdf-respond", status_code=201)
async def submit_pdf_response(
    content_id: uuid.UUID,
    body: PDFResponse,
    user: AxisUser = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Submit a learner's answer to an embedded PDF question.
    Uses the same interaction_responses table as video IC.
    The interaction_index refers to index in content_items.interactions array.
    """
    ci = await _get_pdf_item(content_id, db)

    interactions = ci.interactions or []
    if body.interaction_index >= len(interactions):
        raise HTTPException(status_code=400, detail="Invalid interaction index")

    interaction = interactions[body.interaction_index]
    is_correct: Optional[bool] = None

    if interaction.get("type") == "mcq":
        correct_idx = interaction.get("correct_index")
        try:
            is_correct = int(body.selected_answer) == correct_idx
        except (ValueError, TypeError):
            is_correct = False
    elif interaction.get("type") == "truefalse":
        correct = interaction.get("correct_answer")
        is_correct = body.selected_answer.lower() == str(correct).lower()

    response = InteractionResponse(
        content_item_id=content_id,
        user_id=user.id,
        interaction_index=body.interaction_index,
        selected_answer=body.selected_answer,
        is_correct=is_correct,
        time_taken_seconds=body.time_taken_seconds,
    )
    db.add(response)
    await db.commit()
    await db.refresh(response)

    return {
        "id": str(response.id),
        "is_correct": is_correct,
        "correct_answer": (
            interaction.get("correct_index") if interaction.get("type") == "mcq"
            else interaction.get("correct_answer")
        ),
        "explanation": interaction.get("explanation"),
    }


@router.get("/library/{content_id}/pdf-responses")
async def get_pdf_responses(
    content_id: uuid.UUID,
    user: AxisUser = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Get the learner's own responses to embedded PDF questions."""
    await _get_pdf_item(content_id, db)

    r = await db.execute(
        select(InteractionResponse).where(
            InteractionResponse.content_item_id == content_id,
            InteractionResponse.user_id == user.id,
        ).order_by(InteractionResponse.answered_at)
    )
    responses = r.scalars().all()

    return [
        {
            "id": str(resp.id),
            "interaction_index": resp.interaction_index,
            "selected_answer": resp.selected_answer,
            "is_correct": resp.is_correct,
            "answered_at": resp.answered_at.isoformat(),
        }
        for resp in responses
    ]


# ── Creator: manage embedded interactions ─────────────────────────────────────

class InteractionItem(BaseModel):
    page_num: int
    type: str = "mcq"          # mcq | truefalse | callout
    question: Optional[str] = None
    options: Optional[list[str]] = None
    correct_index: Optional[int] = None
    correct_answer: Optional[bool] = None
    explanation: Optional[str] = None
    text: Optional[str] = None   # for callout type


class InteractionsPayload(BaseModel):
    interactions: list[InteractionItem]


@router.get("/library/{content_id}/pdf-interactions")
async def get_pdf_interactions(
    content_id: uuid.UUID,
    user: AxisUser = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Return the embedded interactions (questions/callouts) for an interactive PDF.
    Accessible to both creators and learners.
    """
    ci = await _get_pdf_item(content_id, db)

    interactions = ci.interactions or []
    # Add index field so frontend can reference by position
    indexed = [{"index": i, **item} if isinstance(item, dict) else item
               for i, item in enumerate(interactions)]
    return {"content_id": str(content_id), "interactions": indexed}


@router.put("/library/{content_id}/pdf-interactions")
async def update_pdf_interactions(
    content_id: uuid.UUID,
    body: InteractionsPayload,
    user: AxisUser = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Replace the full interactions array for an interactive PDF.
    Creator / admin only.
    """
    if user.role not in ("creator", "admin"):
        raise HTTPException(status_code=403, detail="Only creators and admins can edit interactions")

    ci = await _get_pdf_item(content_id, db)

    # Verify ownership (creator can only edit their own content)
    if user.role == "creator" and ci.tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized to edit this content")

    # Serialize to plain dicts
    interactions_data = [item.model_dump(exclude_none=True) for item in body.interactions]

    # Use direct SQL update to avoid Mapped[list] mutation tracking issues
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(ContentItem)
        .where(ContentItem.id == content_id)
        .values(interactions=interactions_data)
    )
    await db.commit()

    log.info("pdf_interactions_updated", content_id=str(content_id), count=len(interactions_data))
    return {"content_id": str(content_id), "interactions": interactions_data, "count": len(interactions_data)}
