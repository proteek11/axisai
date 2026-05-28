"""
Content Library API — Phase 16 (LXP Catalogue).

Creators build a tenant-wide content library. Content is created independently
of Learning Spaces and can be attached to any number of spaces.

Visibility rules:
  is_public=False  → only the creator can see/use it (own content)
  is_public=True   → all creators in the tenant can browse and attach it

Endpoints:
  GET    /api/v1/library                      → list catalogue (own + public)
  POST   /api/v1/library/upload               → upload file to library (no space required)
  POST   /api/v1/library/upload-url           → ingest URL to library
  GET    /api/v1/library/{id}                 → get content detail
  PATCH  /api/v1/library/{id}                 → update title / visibility / experience_mode
  DELETE /api/v1/library/{id}                 → delete (blocked if attached to spaces)
  GET    /api/v1/library/{id}/spaces          → list spaces this content is attached to
  POST   /api/v1/library/{id}/spaces          → attach to a space
  DELETE /api/v1/library/{id}/spaces/{sid}    → detach from a space
  GET    /api/v1/library/{id}/outputs         → get AI outputs for a content item
  POST   /api/v1/library/{id}/progress        → update learner progress
  GET    /api/v1/library/{id}/progress        → get learner's own progress
"""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiofiles
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Security, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import and_, or_, select, func as sa_func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.config import settings
from app.models.content import ContentItem, ContentOrigin, ContentStatus, ContentType, UserContentProgress
from app.models.job import JobStatus, JobType, ProcessingJob
from app.models.space import LearningSpace, SpaceItem
from app.models.user import AxisUser
from app.models.output import AIOutput, OutputStatus
from app.schemas.ingest import IngestResponse

log = structlog.get_logger(__name__)
router = APIRouter(tags=["Content Library"])
_bearer = HTTPBearer()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _require_creator(creds: HTTPAuthorizationCredentials, db: AsyncSession) -> AxisUser:
    user = await get_current_user(creds.credentials, db)
    if user.role not in ("creator", "admin"):
        raise HTTPException(status_code=403, detail="Creator or admin role required.")
    return user


def _ci_to_dict(
    ci: ContentItem,
    creator_name: str | None = None,
    space_count: int = 0,
    already_attached: bool = False,
) -> dict:
    """Serialise a ContentItem to a catalogue card dict."""
    return {
        "id": str(ci.id),
        "title": ci.title,
        "content_type": ci.content_type,
        "experience_mode": ci.experience_mode or "standard",
        "is_public": ci.is_public,
        "status": ci.status,
        "source_url": ci.source_url,
        "language": ci.language,
        "word_count": ci.word_count,
        "chunk_count": ci.chunk_count,
        "creator_id": str(ci.creator_id) if ci.creator_id else None,
        "creator_name": creator_name,
        "space_count": space_count,
        "already_attached": already_attached,
        "created_at": ci.created_at.isoformat() if ci.created_at else None,
        "updated_at": ci.updated_at.isoformat() if ci.updated_at else None,
    }


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class LibraryItemUpdate(BaseModel):
    title: Optional[str] = None
    is_public: Optional[bool] = None
    experience_mode: Optional[str] = None   # "standard" | "interactive"


class LibraryUrlChangeRequest(BaseModel):
    source_url: str
    generate_outputs: Optional[list[str]] = None  # None = re-use previous tasks


class AttachToSpaceRequest(BaseModel):
    space_id: str
    position: Optional[int] = None
    visible_outputs: Optional[list[str]] = None


class ProgressUpdate(BaseModel):
    progress_pct: float          # 0-100
    completed: Optional[bool] = None
    time_spent_seconds: Optional[int] = None
    last_position: Optional[float] = None   # e.g. video timestamp seconds


# ── LIST catalogue ────────────────────────────────────────────────────────────

@router.get("/library")
async def list_library(
    search: str = "",
    content_type: str = "",
    experience_mode: str = "",
    visibility: str = "",          # "own" | "public" | "" (all)
    page: int = 1,
    page_size: int = 30,
    space_id: Optional[str] = None,   # when set, marks items already attached to this space
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    List content library items visible to the current creator.

    Returns own content (any visibility) + public content from other creators.
    Supports search, type filter, experience mode filter, visibility filter.
    Pass space_id to get already_attached=True on items already in that space.
    """
    user = await _require_creator(credentials, db)

    # Base filter: own content OR (public content in same tenant by others)
    base_filter = and_(
        ContentItem.tenant_id == user.tenant_id,
        or_(
            ContentItem.creator_id == user.id,      # always see own
            and_(                                   # or public from others
                ContentItem.is_public == True,
                ContentItem.creator_id != user.id,
            ),
        ),
        # Only library-origin items (origin='space' with no space_id, OR explicitly library)
        ContentItem.origin == ContentOrigin.SPACE.value,
        ContentItem.moodle_cmid.is_(None),          # exclude Moodle-ingested items
    )

    filters = [base_filter]

    if search:
        filters.append(ContentItem.title.ilike(f"%{search}%"))
    if content_type:
        filters.append(ContentItem.content_type == content_type)
    if experience_mode:
        filters.append(ContentItem.experience_mode == experience_mode)
    if visibility == "own":
        filters.append(ContentItem.creator_id == user.id)
    elif visibility == "public":
        filters.append(ContentItem.is_public == True)

    where_clause = and_(*filters)

    # Count total
    count_r = await db.execute(
        select(sa_func.count()).select_from(ContentItem).where(where_clause)
    )
    total = count_r.scalar() or 0

    # Fetch page
    offset = (page - 1) * page_size
    r = await db.execute(
        select(ContentItem)
        .where(where_clause)
        .order_by(ContentItem.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = r.scalars().all()

    if not items:
        return {"items": [], "total": total, "page": page, "page_size": page_size}

    # Fetch creator names
    creator_ids = list({ci.creator_id for ci in items if ci.creator_id})
    creator_map: dict[str, str] = {}
    if creator_ids:
        ur = await db.execute(
            select(AxisUser.id, AxisUser.full_name, AxisUser.email)
            .where(AxisUser.id.in_(creator_ids))
        )
        for row in ur:
            creator_map[str(row.id)] = row.full_name or row.email

    # Count spaces each item is attached to
    ci_ids = [ci.id for ci in items]
    sc_r = await db.execute(
        select(SpaceItem.content_item_id, sa_func.count(SpaceItem.id).label("cnt"))
        .where(SpaceItem.content_item_id.in_(ci_ids))
        .group_by(SpaceItem.content_item_id)
    )
    space_count_map = {str(row.content_item_id): row.cnt for row in sc_r}

    # Compute already_attached set when caller passes a space_id
    attached_set: set[str] = set()
    if space_id:
        try:
            sid_uuid = uuid.UUID(space_id)
            att_r = await db.execute(
                select(SpaceItem.content_item_id)
                .where(
                    SpaceItem.space_id == sid_uuid,
                    SpaceItem.content_item_id.in_(ci_ids),
                )
            )
            attached_set = {str(row.content_item_id) for row in att_r}
        except ValueError:
            pass  # malformed UUID — ignore

    return {
        "items": [
            _ci_to_dict(
                ci,
                creator_name=creator_map.get(str(ci.creator_id)),
                space_count=space_count_map.get(str(ci.id), 0),
                already_attached=str(ci.id) in attached_set,
            )
            for ci in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


# ── UPLOAD file to library ────────────────────────────────────────────────────

@router.post("/library/upload", response_model=IngestResponse, status_code=202)
async def library_upload_file(
    file: UploadFile = File(...),
    content_type: str = Form(default="pdf"),
    title: str | None = Form(None),
    generate_outputs: str = Form(default='["summary"]'),
    language: str = Form(default="en"),
    is_public: str = Form(default="false"),
    experience_mode: str = Form(default="standard"),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    """Upload a file to the content library (no space_id required)."""
    user = await _require_creator(credentials, db)

    # Parse outputs
    try:
        tasks: list[str] = json.loads(generate_outputs)
        if not isinstance(tasks, list):
            tasks = ["summary"]
    except (json.JSONDecodeError, TypeError):
        tasks = [t.strip() for t in generate_outputs.split(",") if t.strip()] or ["summary"]

    # File size check
    from app.api.v1.axis_admin import get_upload_limit_bytes
    file_bytes = await file.read()
    max_bytes = await get_upload_limit_bytes(db)
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum: {max_bytes // (1024 * 1024)} MB.",
        )

    # Save file
    upload_dir = getattr(settings, "upload_dir", "/tmp/axis_uploads")
    os.makedirs(upload_dir, exist_ok=True)
    temp_filename = f"{uuid.uuid4()}_{file.filename}"
    temp_path = os.path.join(upload_dir, temp_filename)
    async with aiofiles.open(temp_path, "wb") as fh:
        await fh.write(file_bytes)

    # Resolve content type
    file_ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    effective_ct = content_type.lower()
    if file_ext == "txt":
        effective_ct = "text"
    ct_map = {
        "pdf": ContentType.PDF,
        "text": ContentType.TEXT,
        "video_upload": ContentType.VIDEO_UPLOAD,
        "audio": ContentType.AUDIO,
        "interactive_pdf": ContentType.INTERACTIVE_PDF,
        "interactive_slides": ContentType.INTERACTIVE_SLIDES,
    }
    resolved_ct = ct_map.get(effective_ct, ContentType.PDF)

    new_asset_id = uuid.uuid4()
    pub = is_public.lower() in ("true", "1", "yes")
    exp_mode = experience_mode if experience_mode in ("standard", "interactive") else "standard"

    content_item = ContentItem(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        origin=ContentOrigin.SPACE.value,
        space_id=None,                    # library-origin: no space
        asset_id=new_asset_id,
        creator_id=user.id,
        moodle_course_id=None,
        moodle_cmid=None,
        content_type=resolved_ct.value,
        source_url=f"file://{temp_path}",
        title=title or file.filename,
        status=ContentStatus.PENDING.value,
        content_hash=str(new_asset_id),
        is_public=pub,
        experience_mode=exp_mode,
        processing_config={"tasks": tasks, "options": {"language": language}},
        moodle_metadata={"uploaded_by": str(user.id), "origin": "library"},
    )
    db.add(content_item)

    job = ProcessingJob(
        id=uuid.uuid4(),
        content_item_id=content_item.id,
        tenant_id=user.tenant_id,
        job_type=JobType.FULL_PIPELINE,
        status=JobStatus.QUEUED,
        progress=0,
        progress_message="Queued",
        job_config={"tasks": tasks, "options": {"language": language}},
    )
    db.add(job)
    await db.flush()

    from app.tasks.celery_app import celery_app
    celery_app.send_task(
        "app.tasks.process_content.run_pipeline",
        kwargs={
            "job_id": str(job.id),
            "content_item_id": str(content_item.id),
            "tenant_id": str(user.tenant_id),
            "job_config": job.job_config,
            "axis_user_id": str(user.id),
        },
        queue="default",
    )
    await db.commit()

    log.info("library_upload_queued", content_item_id=str(content_item.id), user_id=str(user.id))
    return IngestResponse(
        content_item_id=str(content_item.id),
        job_id=str(job.id),
        status="queued",
        message=f"Job queued. Poll /api/v1/jobs/{job.id} for status.",
    )


# ── UPLOAD URL to library ─────────────────────────────────────────────────────

class LibraryURLRequest(BaseModel):
    source_url: str
    content_type: str = "youtube"
    title: Optional[str] = None
    generate_outputs: list[str] = ["summary"]
    language: str = "en"
    is_public: bool = False
    experience_mode: str = "standard"
    metadata: dict = {}


@router.post("/library/upload-url", response_model=IngestResponse, status_code=202)
async def library_upload_url(
    request: LibraryURLRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    """Ingest a URL (YouTube, Vimeo, PDF URL, etc.) into the content library."""
    user = await _require_creator(credentials, db)

    ct_map = {
        "youtube": ContentType.YOUTUBE, "vimeo": ContentType.VIMEO,
        "peertube": ContentType.PEERTUBE, "pdf": ContentType.PDF,
        "html_page": ContentType.HTML_PAGE,
    }
    resolved_ct = ct_map.get(request.content_type.lower(), ContentType.YOUTUBE)
    new_asset_id = uuid.uuid4()
    exp_mode = request.experience_mode if request.experience_mode in ("standard", "interactive") else "standard"

    content_item = ContentItem(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        origin=ContentOrigin.SPACE.value,
        space_id=None,
        asset_id=new_asset_id,
        creator_id=user.id,
        moodle_course_id=None,
        moodle_cmid=None,
        content_type=resolved_ct.value,
        source_url=request.source_url,
        title=request.title or request.source_url,
        status=ContentStatus.PENDING.value,
        content_hash=str(new_asset_id),
        is_public=request.is_public,
        experience_mode=exp_mode,
        processing_config={
            "tasks": request.generate_outputs,
            "options": {"language": request.language},
        },
        moodle_metadata={"uploaded_by": str(user.id), "origin": "library", **request.metadata},
    )
    db.add(content_item)

    job = ProcessingJob(
        id=uuid.uuid4(),
        content_item_id=content_item.id,
        tenant_id=user.tenant_id,
        job_type=JobType.FULL_PIPELINE,
        status=JobStatus.QUEUED,
        progress=0,
        progress_message="Queued",
        job_config={
            "tasks": request.generate_outputs,
            "options": {"language": request.language},
        },
    )
    db.add(job)
    await db.flush()

    from app.tasks.celery_app import celery_app
    celery_app.send_task(
        "app.tasks.process_content.run_pipeline",
        kwargs={
            "job_id": str(job.id),
            "content_item_id": str(content_item.id),
            "tenant_id": str(user.tenant_id),
            "job_config": job.job_config,
            "axis_user_id": str(user.id),
        },
        queue="default",
    )
    await db.commit()

    log.info("library_url_queued", content_item_id=str(content_item.id), url=request.source_url)
    return IngestResponse(
        content_item_id=str(content_item.id),
        job_id=str(job.id),
        status="queued",
        message=f"Job queued. Poll /api/v1/jobs/{job.id} for status.",
    )


# ── GET single catalogue item ─────────────────────────────────────────────────

@router.get("/library/{content_id}")
async def get_library_item(
    content_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _require_creator(credentials, db)
    ci = await _get_accessible_item(content_id, user, db)

    # Creator name
    creator_name = None
    if ci.creator_id:
        ur = await db.execute(
            select(AxisUser.full_name, AxisUser.email).where(AxisUser.id == ci.creator_id)
        )
        row = ur.first()
        if row:
            creator_name = row.full_name or row.email

    # Space count
    sc_r = await db.execute(
        select(sa_func.count(SpaceItem.id)).where(SpaceItem.content_item_id == ci.id)
    )
    space_count = sc_r.scalar() or 0

    return {**_ci_to_dict(ci, creator_name, space_count), "interactions": ci.interactions or []}


# ── PATCH catalogue item ──────────────────────────────────────────────────────

@router.patch("/library/{content_id}")
async def update_library_item(
    content_id: uuid.UUID,
    body: LibraryItemUpdate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _require_creator(credentials, db)
    ci = await _get_owned_item(content_id, user, db)

    if body.title is not None:
        ci.title = body.title
    if body.is_public is not None:
        ci.is_public = body.is_public
    if body.experience_mode is not None and body.experience_mode in ("standard", "interactive"):
        ci.experience_mode = body.experience_mode

    await db.commit()
    return {"id": str(ci.id), "title": ci.title, "is_public": ci.is_public, "experience_mode": ci.experience_mode}


# ── DELETE catalogue item ─────────────────────────────────────────────────────

# ── Change URL + re-ingest ────────────────────────────────────────────────────

URL_TYPES = {"youtube", "vimeo", "html_page", "page", "text"}

@router.post("/library/{content_id}/change-url")
async def change_library_url(
    content_id: uuid.UUID,
    body: LibraryUrlChangeRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Change the source URL for a URL-based content item (YouTube, Vimeo, Web page)
    and re-trigger the full ingestion pipeline.

    Supported content types: youtube, vimeo, html_page, page, text
    Not supported: pdf, scorm, video_upload, interactive_pdf, interactive_slides
    (use the file replace endpoint instead).
    """
    user = await _require_creator(credentials, db)
    ci = await _get_owned_item(content_id, user, db)

    ct = str(ci.content_type.value) if hasattr(ci.content_type, "value") else str(ci.content_type)
    if ct not in URL_TYPES:
        raise HTTPException(
            400,
            f"URL change is only supported for URL-based content types ({', '.join(URL_TYPES)}). "
            f"This item is '{ct}' — use the file replace endpoint."
        )

    if not body.source_url.strip():
        raise HTTPException(400, "source_url cannot be empty")

    # Decide output tasks
    tasks = body.generate_outputs or (ci.processing_config or {}).get("tasks", ["summary"])

    # Reset content item
    ci.source_url = body.source_url.strip()
    ci.status = ContentStatus.PENDING.value
    ci.content_hash = None     # force re-extraction
    ci.word_count = None
    ci.chunk_count = 0
    ci.extracted_at = None

    job = ProcessingJob(
        id=uuid.uuid4(),
        content_item_id=ci.id,
        tenant_id=user.tenant_id,
        job_type=JobType.FULL_PIPELINE,
        status=JobStatus.QUEUED,
        progress=0,
        progress_message="Queued for URL change re-ingestion",
        job_config={"tasks": tasks, "options": {"language": "en"}},
    )
    db.add(job)
    await db.flush()

    from app.tasks.celery_app import celery_app
    celery_app.send_task(
        "app.tasks.process_content.run_pipeline",
        kwargs={
            "job_id": str(job.id),
            "content_item_id": str(ci.id),
            "tenant_id": str(user.tenant_id),
            "job_config": job.job_config,
            "axis_user_id": str(user.id),
        },
        queue="default",
    )
    await db.commit()

    log.info("library_url_changed", content_item_id=str(ci.id), new_url=body.source_url, user_id=str(user.id))
    return {
        "content_item_id": str(ci.id),
        "job_id": str(job.id),
        "status": "queued",
        "message": f"URL updated. Re-ingestion queued. Poll /api/v1/jobs/{job.id} for status.",
    }



@router.delete("/library/{content_id}", status_code=204)
async def delete_library_item(
    content_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    user = await _require_creator(credentials, db)
    ci = await _get_owned_item(content_id, user, db)

    # Block deletion if attached to any spaces
    sc_r = await db.execute(
        select(SpaceItem.space_id).where(SpaceItem.content_item_id == ci.id).limit(10)
    )
    attached_space_ids = [str(row.space_id) for row in sc_r]
    if attached_space_ids:
        # Fetch space titles for the error message
        sr = await db.execute(
            select(LearningSpace.id, LearningSpace.title)
            .where(LearningSpace.id.in_([uuid.UUID(sid) for sid in attached_space_ids]))
        )
        space_names = [row.title for row in sr]
        raise HTTPException(
            status_code=409,
            detail={
                "error": "content_attached_to_spaces",
                "message": (
                    "This content is attached to one or more spaces. "
                    "Detach it from all spaces before deleting."
                ),
                "spaces": space_names,
            },
        )

    await db.delete(ci)
    await db.commit()
    log.info("library_item_deleted", content_id=str(content_id), user_id=str(user.id))


# ── GET spaces this item is attached to ──────────────────────────────────────

@router.get("/library/{content_id}/spaces")
async def get_item_spaces(
    content_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _require_creator(credentials, db)
    await _get_accessible_item(content_id, user, db)

    r = await db.execute(
        select(SpaceItem, LearningSpace)
        .join(LearningSpace, SpaceItem.space_id == LearningSpace.id)
        .where(SpaceItem.content_item_id == content_id)
        .order_by(LearningSpace.title)
    )
    rows = r.all()

    return {
        "content_item_id": str(content_id),
        "spaces": [
            {
                "space_id": str(space.id),
                "title": space.title,
                "is_published": space.is_published,
                "position": si.position,
                "space_item_id": str(si.id),
            }
            for si, space in rows
        ],
    }


# ── ATTACH to a space ─────────────────────────────────────────────────────────

@router.post("/library/{content_id}/spaces", status_code=201)
async def attach_to_space(
    content_id: uuid.UUID,
    body: AttachToSpaceRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Attach a catalogue item to a Learning Space."""
    user = await _require_creator(credentials, db)
    ci = await _get_accessible_item(content_id, user, db)

    space_id = uuid.UUID(body.space_id)
    space_r = await db.execute(
        select(LearningSpace).where(
            LearningSpace.id == space_id,
            LearningSpace.tenant_id == user.tenant_id,
        )
    )
    space = space_r.scalar_one_or_none()
    if not space:
        raise HTTPException(status_code=404, detail="Space not found.")
    if space.creator_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="You don't own this space.")

    # Check not already attached
    existing_r = await db.execute(
        select(SpaceItem).where(
            SpaceItem.space_id == space_id,
            SpaceItem.content_item_id == content_id,
        )
    )
    if existing_r.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Content is already attached to this space.")

    # Get current item count for position
    count_r = await db.execute(
        select(sa_func.count(SpaceItem.id)).where(SpaceItem.space_id == space_id)
    )
    current_count = count_r.scalar() or 0

    default_outputs = ["summary", "glossary", "flashcards", "quiz"]
    si = SpaceItem(
        id=uuid.uuid4(),
        space_id=space_id,
        content_item_id=content_id,
        position=body.position if body.position is not None else current_count,
        is_visible=True,
        visible_outputs=body.visible_outputs or default_outputs,
    )
    db.add(si)
    await db.commit()

    log.info("library_item_attached", content_id=str(content_id), space_id=str(space_id), user_id=str(user.id))
    return {
        "space_item_id": str(si.id),
        "content_item_id": str(content_id),
        "space_id": str(space_id),
        "position": si.position,
    }


# ── DETACH from a space ───────────────────────────────────────────────────────

@router.delete("/library/{content_id}/spaces/{space_id}", status_code=204)
async def detach_from_space(
    content_id: uuid.UUID,
    space_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    user = await _require_creator(credentials, db)

    # Must own the space OR be admin
    space_r = await db.execute(
        select(LearningSpace).where(
            LearningSpace.id == space_id,
            LearningSpace.tenant_id == user.tenant_id,
        )
    )
    space = space_r.scalar_one_or_none()
    if not space:
        raise HTTPException(status_code=404, detail="Space not found.")
    if space.creator_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="You don't own this space.")

    r = await db.execute(
        select(SpaceItem).where(
            SpaceItem.content_item_id == content_id,
            SpaceItem.space_id == space_id,
        )
    )
    si = r.scalar_one_or_none()
    if not si:
        raise HTTPException(status_code=404, detail="Content is not attached to this space.")

    await db.delete(si)
    await db.commit()
    log.info("library_item_detached", content_id=str(content_id), space_id=str(space_id))


# ── GET AI outputs for a library item ────────────────────────────────────────

@router.get("/library/{content_id}/outputs")
async def get_library_item_outputs(
    content_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> list:
    """
    Return all ACTIVE AI outputs for a library content item.
    Uses JWT auth (same as rest of library API) — no tenant API key needed.
    """
    user = await _require_creator(credentials, db)
    # Verify the item is accessible to this user
    await _get_accessible_item(content_id, user, db)

    r = await db.execute(
        select(AIOutput).where(
            AIOutput.content_item_id == content_id,
            AIOutput.status == OutputStatus.ACTIVE,
        ).order_by(AIOutput.output_type)
    )
    outputs = r.scalars().all()

    def _serialise_output(o: AIOutput) -> dict:
        # Serve teacher-edited version if present
        payload = o.edited_content if o.is_teacher_edited and o.edited_content else o.payload
        return {
            "id": str(o.id),
            "output_type": o.output_type,
            "language": o.language,
            "status": o.status,
            "payload": payload,
            "model": o.model,
            "prompt_version": o.prompt_version,
            "is_teacher_edited": o.is_teacher_edited,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "updated_at": o.updated_at.isoformat() if o.updated_at else None,
        }

    return [_serialise_output(o) for o in outputs]


# ── REGENERATE AI outputs for a library item ──────────────────────────────────

class RegenerateRequest(BaseModel):
    output_types: list[str]     # e.g. ["summary", "quiz", "flashcards"]
    language: str = "en"


@router.post("/library/{content_id}/regenerate", status_code=202)
async def regenerate_library_outputs(
    content_id: uuid.UUID,
    body: RegenerateRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Queue a new pipeline job to regenerate specific AI output types.
    Uses JWT auth (same as rest of library API).
    """
    user = await _require_creator(credentials, db)
    ci = await _get_accessible_item(content_id, user, db)

    if not body.output_types:
        raise HTTPException(status_code=422, detail="At least one output_type is required.")

    valid_types = {"summary", "quiz", "flashcards", "glossary", "faq", "infographic", "mindmap", "objectives", "blooms", "chapters"}
    invalid = [t for t in body.output_types if t not in valid_types]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Invalid output types: {invalid}")

    job = ProcessingJob(
        id=uuid.uuid4(),
        content_item_id=ci.id,
        tenant_id=user.tenant_id,
        job_type=JobType.FULL_PIPELINE,
        status=JobStatus.QUEUED,
        progress=0,
        progress_message="Queued for regeneration",
        job_config={
            "tasks": body.output_types,
            "options": {"language": body.language},
            "skip_extraction": True,    # Re-use existing chunks, only re-run generators
        },
    )
    db.add(job)
    await db.flush()

    from app.tasks.celery_app import celery_app
    celery_app.send_task(
        "app.tasks.process_content.run_pipeline",
        kwargs={
            "job_id": str(job.id),
            "content_item_id": str(ci.id),
            "tenant_id": str(user.tenant_id),
            "job_config": job.job_config,
            "axis_user_id": str(user.id),
        },
        queue="default",
    )
    await db.commit()

    log.info("library_regenerate_queued", content_id=str(content_id), types=body.output_types)
    return {
        "job_id": str(job.id),
        "content_item_id": str(content_id),
        "status": "queued",
        "output_types": body.output_types,
        "message": f"Regeneration queued. Poll /api/v1/jobs/{job.id} for status.",
    }


# ── Progress tracking ─────────────────────────────────────────────────────────

@router.post("/library/{content_id}/progress")
async def update_progress(
    content_id: uuid.UUID,
    body: ProgressUpdate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update learner's content-level progress."""
    user = await get_current_user(credentials.credentials, db)

    # Verify content exists and learner has access
    ci_r = await db.execute(
        select(ContentItem).where(
            ContentItem.id == content_id,
            ContentItem.tenant_id == user.tenant_id,
        )
    )
    ci = ci_r.scalar_one_or_none()
    if not ci:
        raise HTTPException(status_code=404, detail="Content not found.")

    # Upsert progress
    r = await db.execute(
        select(UserContentProgress).where(
            UserContentProgress.user_id == user.id,
            UserContentProgress.content_item_id == content_id,
        )
    )
    prog = r.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    extra = {}
    if body.time_spent_seconds is not None:
        extra["time_spent_seconds"] = body.time_spent_seconds
    if body.last_position is not None:
        extra["last_position"] = body.last_position

    if not prog:
        prog = UserContentProgress(
            id=uuid.uuid4(),
            user_id=user.id,
            content_item_id=content_id,
            tenant_id=user.tenant_id,
            progress_pct=min(100.0, body.progress_pct),
            started_at=now,
            completion_data=extra,
        )
        db.add(prog)
    else:
        prog.progress_pct = min(100.0, body.progress_pct)
        if extra:
            prog.completion_data = {**(prog.completion_data or {}), **extra}

    completed = body.completed if body.completed is not None else (body.progress_pct >= 100)
    newly_completed = completed and not prog.completed_at
    if completed and not prog.completed_at:
        prog.completed_at = now
    elif not completed:
        prog.completed_at = None

    await db.commit()

    # Fire skill-award task when item is newly completed
    if newly_completed:
        try:
            from app.tasks.skills_tasks import award_skills
            award_skills.delay(str(user.id), str(content_id), str(user.tenant_id))
        except Exception:
            pass  # Non-critical — never block progress save

    return {
        "content_item_id": str(content_id),
        "progress_pct": prog.progress_pct,
        "completed": prog.completed_at is not None,
        "started_at": prog.started_at.isoformat(),
        "completed_at": prog.completed_at.isoformat() if prog.completed_at else None,
    }


@router.get("/library/{content_id}/progress")
async def get_progress(
    content_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get learner's own progress for a content item."""
    user = await get_current_user(credentials.credentials, db)

    r = await db.execute(
        select(UserContentProgress).where(
            UserContentProgress.user_id == user.id,
            UserContentProgress.content_item_id == content_id,
        )
    )
    prog = r.scalar_one_or_none()
    if not prog:
        return {"content_item_id": str(content_id), "progress_pct": 0, "completed": False, "started_at": None, "completed_at": None}

    return {
        "content_item_id": str(content_id),
        "progress_pct": prog.progress_pct,
        "completed": prog.completed_at is not None,
        "started_at": prog.started_at.isoformat(),
        "completed_at": prog.completed_at.isoformat() if prog.completed_at else None,
        "completion_data": prog.completion_data,
    }


# ── Private helpers ───────────────────────────────────────────────────────────

async def _get_accessible_item(content_id: uuid.UUID, user: AxisUser, db: AsyncSession) -> ContentItem:
    """Fetch a ContentItem the user is allowed to read (own OR public-in-tenant)."""
    r = await db.execute(
        select(ContentItem).where(
            ContentItem.id == content_id,
            ContentItem.tenant_id == user.tenant_id,
            or_(
                ContentItem.creator_id == user.id,
                ContentItem.is_public == True,
            ),
        )
    )
    ci = r.scalar_one_or_none()
    if not ci:
        raise HTTPException(status_code=404, detail="Content not found or not accessible.")
    return ci


async def _get_owned_item(content_id: uuid.UUID, user: AxisUser, db: AsyncSession) -> ContentItem:
    """Fetch a ContentItem the user owns (edit/delete access)."""
    r = await db.execute(
        select(ContentItem).where(
            ContentItem.id == content_id,
            ContentItem.tenant_id == user.tenant_id,
        )
    )
    ci = r.scalar_one_or_none()
    if not ci:
        raise HTTPException(status_code=404, detail="Content not found.")
    if ci.creator_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="You don't own this content.")
    return ci




# ── Replace uploaded file ─────────────────────────────────────────────────────

@router.post("/library/{content_id}/replace-file", response_model=IngestResponse, status_code=202)
async def replace_library_file(
    content_id: uuid.UUID,
    file: UploadFile = File(...),
    generate_outputs: str = Form(default=""),   # comma or JSON list; empty = keep existing types
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    """
    Replace the uploaded file for an existing library content item and re-run the
    full pipeline (extraction + AI generation).

    • The old file on disk is NOT deleted immediately (handled by cleanup jobs).
    • generate_outputs: if blank, the backend re-uses the content_item's processing_config
      so all previously requested output types are regenerated automatically.
    """
    user = await _require_creator(credentials, db)
    ci = await _get_owned_item(content_id, user, db)

    # File size check
    from app.api.v1.axis_admin import get_upload_limit_bytes
    file_bytes = await file.read()
    max_bytes = await get_upload_limit_bytes(db)
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum: {max_bytes // (1024 * 1024)} MB.",
        )

    # Save new file
    upload_dir = getattr(settings, "upload_dir", "/tmp/axis_uploads")
    os.makedirs(upload_dir, exist_ok=True)
    new_filename = f"{uuid.uuid4()}_{file.filename}"
    new_path = os.path.join(upload_dir, new_filename)
    async with aiofiles.open(new_path, "wb") as fh:
        await fh.write(file_bytes)

    # Decide which output types to generate
    if generate_outputs.strip():
        try:
            tasks: list[str] = json.loads(generate_outputs)
            if not isinstance(tasks, list):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            tasks = [t.strip() for t in generate_outputs.split(",") if t.strip()]
    else:
        # Re-use previously requested tasks from processing_config
        tasks = (ci.processing_config or {}).get("tasks", ["summary"])

    # Update source_url + reset status
    ci.source_url = f"file://{new_path}"
    ci.status = ContentStatus.PENDING.value
    ci.content_hash = str(uuid.uuid4())  # force re-process (hash change detection)

    job = ProcessingJob(
        id=uuid.uuid4(),
        content_item_id=ci.id,
        tenant_id=user.tenant_id,
        job_type=JobType.FULL_PIPELINE,
        status=JobStatus.QUEUED,
        progress=0,
        progress_message="Queued for file replacement",
        job_config={"tasks": tasks, "options": {"language": "en"}},
    )
    db.add(job)
    await db.flush()

    from app.tasks.celery_app import celery_app
    celery_app.send_task(
        "app.tasks.process_content.run_pipeline",
        kwargs={
            "job_id": str(job.id),
            "content_item_id": str(ci.id),
            "tenant_id": str(user.tenant_id),
            "job_config": job.job_config,
            "axis_user_id": str(user.id),
        },
        queue="default",
    )
    await db.commit()

    log.info("library_file_replaced", content_item_id=str(ci.id), user_id=str(user.id))
    return IngestResponse(
        content_item_id=str(ci.id),
        job_id=str(job.id),
        status="queued",
        message=f"File replaced. Pipeline re-running. Poll /api/v1/jobs/{job.id} for status.",
    )

# ── File serving ──────────────────────────────────────────────────────────────

@router.get("/library/files/{content_id}")
async def serve_library_file(
    content_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """
    Stream an uploaded file (PDF, PPTX, video, etc.) to authenticated users.

    Works for any content whose source_url was stored as file:///path/to/file.
    Auth: user must be authenticated and belong to the same tenant as the content.
    """
    user = await get_current_user(credentials.credentials, db)

    # Content must belong to same tenant — no creator check so learners can also fetch
    r = await db.execute(
        select(ContentItem).where(
            ContentItem.id == content_id,
            ContentItem.tenant_id == user.tenant_id,
        )
    )
    ci = r.scalar_one_or_none()
    if not ci:
        raise HTTPException(status_code=404, detail="Content not found.")

    if not ci.source_url:
        raise HTTPException(status_code=404, detail="No file associated with this content.")

    # Resolve source_url → either serve locally or redirect to remote storage
    from app.core.storage import get_local_path, is_remote_url, get_download_url
    from fastapi.responses import RedirectResponse

    if is_remote_url(ci.source_url):
        # S3 / CDN backend — issue a redirect so the browser fetches directly.
        # For private buckets this generates a presigned URL (valid 1 h).
        try:
            redirect_url = get_download_url(ci.source_url)
        except Exception as exc:
            log.error("serve_file_remote_url_failed", content_id=str(content_id), error=str(exc))
            raise HTTPException(status_code=502, detail="Could not resolve remote file URL.")
        log.info("serve_library_file_redirect", content_id=str(content_id), user_id=str(user.id))
        return RedirectResponse(url=redirect_url, status_code=302)

    # Local file:// path
    file_path = get_local_path(ci.source_url)
    if not file_path:
        raise HTTPException(status_code=404, detail="This content is not a locally uploaded file.")

    if not os.path.exists(file_path):
        log.error("serve_file_missing_on_disk", content_id=str(content_id), path=file_path)
        raise HTTPException(status_code=404, detail="File not found on disk — it may have been cleaned up.")

    log.info("serve_library_file", content_id=str(content_id), user_id=str(user.id))
    return FileResponse(file_path)
