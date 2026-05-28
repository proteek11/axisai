"""
Interactive Slides API — PF-03.

Endpoints:
  GET  /api/v1/library/{id}/slides           → list all slides (index, thumbnail_url, dimensions)
  GET  /api/v1/library/{id}/slides/{n}       → serve slide image at index n (PNG)
  GET  /api/v1/library/{id}/slides/{n}/thumb → serve thumbnail (JPEG)
  POST /api/v1/library/{id}/slide-respond    → submit answer to a per-slide quiz question
  GET  /api/v1/library/{id}/slide-responses  → get learner's own slide quiz responses
"""
import uuid
from pathlib import Path
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.jwt import decode_access_token
from app.models.content import ContentItem, ContentType
from app.models.interaction import InteractionResponse
from app.models.user import AxisUser

log = structlog.get_logger(__name__)
router = APIRouter(tags=["Interactive Slides"])
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


async def _get_slides_item(content_id: uuid.UUID, db: AsyncSession) -> ContentItem:
    r = await db.execute(select(ContentItem).where(ContentItem.id == content_id))
    ci = r.scalar_one_or_none()
    if not ci:
        raise HTTPException(status_code=404, detail="Content not found")
    if ci.content_type != ContentType.INTERACTIVE_SLIDES:
        raise HTTPException(status_code=400, detail="Content is not an Interactive Slides item")
    return ci


# ── Schemas ───────────────────────────────────────────────────────────────────

class SlideResponse(BaseModel):
    interaction_index: int
    selected_answer: str
    time_taken_seconds: Optional[int] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/library/{content_id}/slides")
async def list_slides(
    content_id: uuid.UUID,
    user: AxisUser = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Return slide list for the content item.

    Each slide entry:
      {index, image_url, thumbnail_url, width, height, interaction: {...} | null}
    """
    ci = await _get_slides_item(content_id, db)
    assets = ci.slide_assets or []
    interactions = ci.interactions or []

    # Build interaction map: slide_num (1-based) → interaction
    interaction_by_slide: dict[int, dict] = {}
    for ia in interactions:
        page = ia.get("page_num") or ia.get("slide_num")
        if page:
            interaction_by_slide[int(page)] = ia

    slides = []
    for asset in sorted(assets, key=lambda a: a["index"]):
        idx = asset["index"]
        slides.append({
            "index": idx,
            "image_url": f"/api/v1/library/{content_id}/slides/{idx}",
            "thumbnail_url": f"/api/v1/library/{content_id}/slides/{idx}/thumb",
            "width": asset.get("width", 1280),
            "height": asset.get("height", 720),
            "interaction": interaction_by_slide.get(idx),
        })

    return {
        "content_id": str(content_id),
        "title": ci.title,
        "slide_count": len(slides),
        "slides": slides,
    }


@router.get("/library/{content_id}/slides/{slide_index}")
async def serve_slide_image(
    content_id: uuid.UUID,
    slide_index: int,
    user: AxisUser = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Serve the full-resolution slide PNG at the given 1-based index."""
    ci = await _get_slides_item(content_id, db)
    assets = ci.slide_assets or []

    matching = next((a for a in assets if a["index"] == slide_index), None)
    if not matching:
        raise HTTPException(status_code=404, detail=f"Slide {slide_index} not found")

    img_path = Path(matching["path"])
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Slide image not found on disk")

    return FileResponse(
        str(img_path),
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/library/{content_id}/slides/{slide_index}/thumb")
async def serve_slide_thumbnail(
    content_id: uuid.UUID,
    slide_index: int,
    user: AxisUser = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Serve the thumbnail JPEG for a slide."""
    ci = await _get_slides_item(content_id, db)
    assets = ci.slide_assets or []

    matching = next((a for a in assets if a["index"] == slide_index), None)
    if not matching:
        raise HTTPException(status_code=404, detail=f"Slide {slide_index} thumbnail not found")

    thumb_path = Path(matching.get("thumbnail_path", matching["path"]))
    if not thumb_path.exists():
        # Fall back to full image
        thumb_path = Path(matching["path"])

    return FileResponse(
        str(thumb_path),
        media_type="image/jpeg" if str(thumb_path).endswith(".jpg") else "image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/library/{content_id}/slide-respond", status_code=201)
async def submit_slide_response(
    content_id: uuid.UUID,
    body: SlideResponse,
    user: AxisUser = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Submit a learner's answer to a per-slide quiz question.
    Reuses interaction_responses table (same as video IC and PDF IC).
    """
    ci = await _get_slides_item(content_id, db)
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


@router.get("/library/{content_id}/slide-responses")
async def get_slide_responses(
    content_id: uuid.UUID,
    user: AxisUser = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Get the learner's own responses to slide quiz questions."""
    await _get_slides_item(content_id, db)

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
