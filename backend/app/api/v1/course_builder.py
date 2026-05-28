"""
Auto-Course Builder — Phase 17.

Creator uploads a PDF → AI drafts lesson plan → creator reviews →
system generates a full Learning Space (summaries, quizzes, flashcards,
glossary) for every chapter in parallel.

Routes (JWT auth):
  POST /course-builder/analyze         — PDF → lesson plan JSON + redis_token
  GET  /course-builder/youtube         — YouTube search for video suggestions
  POST /course-builder/generate        — Create space + kick off all chapter jobs
  GET  /course-builder/progress/{sid}  — Poll job statuses for all items in a space
"""
from __future__ import annotations

import json
import os
import secrets
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import pdfplumber
import structlog
import yaml
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from slugify import slugify

from app.api.v1.auth import get_current_user_dep as get_current_user
from app.api.v1.axis_admin import get_current_ai_models
from app.core.database import get_db
from app.core.redis import get_redis
from app.config import settings
from app.models.content import ContentItem, ContentOrigin, ContentStatus, ContentType
from app.models.job import JobStatus, JobType, ProcessingJob
from app.models.space import LearningSpace, SpaceItem
from app.models.user import AxisUser

log = structlog.get_logger(__name__)
router = APIRouter()

# ── Config ────────────────────────────────────────────────────────────────────
_REDIS_TTL = 7200           # 2 h — lesson plan token TTL
_MAX_PDF_PAGES = 300
_MAX_TEXT_CHARS = 200_000   # ~150 K tokens — fits GPT-4o 128 K context with margin
# Resolved at runtime from settings so it can be overridden via COURSE_BUILDER_TMP_DIR env var
def _get_tmp_dir() -> Path:
    return Path(settings.course_builder_tmp_dir)
_YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _unique_slug(base: str) -> str:
    slug = slugify(base)[:200]
    suffix = secrets.token_hex(4)
    return f"{slug}-{suffix}"


def _load_course_analysis_prompt() -> dict:
    prompt_path = (
        Path(__file__).parent.parent.parent
        / "services/ai/prompts/course_analysis.yaml"
    )
    with open(prompt_path) as f:
        return yaml.safe_load(f)


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChapterPlan(BaseModel):
    title: str
    page_start: int
    page_end: int
    key_topics: list[str] = []
    difficulty: str = "intermediate"   # beginner | intermediate | advanced
    include: bool = True
    youtube_search_query: str = ""


class LessonPlan(BaseModel):
    course_title: str
    description: str
    estimated_duration: str = ""
    objectives: list[str] = []
    chapters: list[ChapterPlan]
    redis_token: str
    total_pages: int


class YouTubeVideo(BaseModel):
    video_id: str
    title: str
    channel: str
    thumbnail_url: str
    embed_url: str


class GenerateChapter(BaseModel):
    title: str
    page_start: int
    page_end: int
    include: bool = True
    generate_tasks: list[str] = Field(
        default=["summary", "quiz", "flashcards", "glossary", "discussion_prompts"],
    )
    quiz_count: int = Field(default=8, ge=1, le=25)


class YouTubeAttachment(BaseModel):
    chapter_index: int
    video_id: str
    title: str
    thumbnail_url: str = ""


class GenerateRequest(BaseModel):
    redis_token: str
    space_title: str
    space_description: str = ""
    chapters: list[GenerateChapter]
    youtube_videos: list[YouTubeAttachment] = []


class ChapterJobStatus(BaseModel):
    chapter_title: str
    content_item_id: str
    job_id: Optional[str] = None
    status: str
    progress_pct: int = 0


class GenerateResponse(BaseModel):
    space_id: str
    space_title: str
    chapters: list[ChapterJobStatus]
    total_chapters: int


class ProgressResponse(BaseModel):
    space_id: str
    chapters: list[ChapterJobStatus]
    completed: int
    total: int
    done: bool


# ── ENDPOINT 1: Analyze PDF ───────────────────────────────────────────────────

@router.post(
    "/course-builder/analyze",
    response_model=LessonPlan,
    summary="Upload PDF → AI generates lesson plan",
)
async def analyze_pdf(
    file: UploadFile = File(..., description="PDF file to analyze"),
    user: AxisUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Extract text from uploaded PDF page-by-page, send to LLM, return structured
    lesson plan JSON. Stores per-page text in Redis (TTL 2 h) for the generate step.
    """
    if user.role not in ("admin", "creator"):
        raise HTTPException(403, "Creator or admin access required")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > 50 * 1024 * 1024:
        raise HTTPException(400, "PDF too large — maximum 50 MB")

    # ── Extract per-page text ─────────────────────────────────────────────
    pages_text: list[str] = []
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        with pdfplumber.open(tmp_path) as pdf:
            total_pages = len(pdf.pages)
            if total_pages > _MAX_PDF_PAGES:
                raise HTTPException(
                    400, f"PDF too long ({total_pages} pages). Max is {_MAX_PDF_PAGES}."
                )
            for page in pdf.pages:
                pages_text.append((page.extract_text() or "").strip())

        os.unlink(tmp_path)
    except HTTPException:
        raise
    except Exception as e:
        log.error("course_builder_pdf_extract_failed", error=str(e))
        raise HTTPException(500, f"Could not extract PDF text: {e}")

    full_text = "\n\n".join(pages_text)
    if len(full_text) < 200:
        raise HTTPException(400, "PDF appears to be empty or image-only (no extractable text)")

    if len(full_text) > _MAX_TEXT_CHARS:
        full_text = full_text[:_MAX_TEXT_CHARS]

    # ── Store per-page text in Redis ──────────────────────────────────────
    token = secrets.token_urlsafe(24)
    redis_key = f"course_build:{token}"
    try:
        redis = await get_redis()
        await redis.set(redis_key, json.dumps(pages_text), ex=_REDIS_TTL)
    except Exception as e:
        log.error("course_builder_redis_store_failed", error=str(e))
        raise HTTPException(500, "Failed to store course data — please retry")

    # ── LLM: generate lesson plan ─────────────────────────────────────────
    from app.services.ai.client import AIClient
    from app.core.database import AsyncSessionFactory

    prompt_def = _load_course_analysis_prompt()
    main_model, _ = await get_current_ai_models(db)

    system_prompt = prompt_def["system"].strip()
    user_prompt = prompt_def["user"].format(
        total_pages=total_pages,
        full_text=full_text,
    ).strip()

    ai_client = AIClient(
        session_factory=AsyncSessionFactory,
        tenant_id=str(user.tenant_id) if user.tenant_id else None,
        axis_user_id=str(user.id),
    )

    try:
        response = await ai_client.complete(
            model=main_model,
            task_type="course_analysis",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=3000,
            response_format={"type": "json_object"},
        )
        lesson_data = json.loads(response.choices[0].message.content)
    except json.JSONDecodeError as e:
        log.error("course_builder_json_parse_failed", error=str(e))
        raise HTTPException(500, "LLM returned invalid JSON for lesson plan")
    except Exception as e:
        log.error("course_builder_llm_failed", error=str(e))
        raise HTTPException(500, f"AI lesson plan generation failed: {e}")

    chapters = [
        ChapterPlan(
            title=ch.get("title", f"Chapter {i + 1}"),
            page_start=max(1, int(ch.get("page_start", 1))),
            page_end=min(total_pages, int(ch.get("page_end", total_pages))),
            key_topics=ch.get("key_topics", [])[:8],
            difficulty=ch.get("difficulty", "intermediate") if ch.get("difficulty", "intermediate") in ("beginner", "intermediate", "advanced") else "intermediate",
            include=bool(ch.get("include", True)),
            youtube_search_query=ch.get("youtube_search_query", ""),
        )
        for i, ch in enumerate(lesson_data.get("chapters", []))
    ]

    log.info(
        "course_builder_analyzed",
        user_id=str(user.id),
        pages=total_pages,
        chapters=len(chapters),
        model=main_model,
    )

    return LessonPlan(
        course_title=lesson_data.get("course_title", file.filename or "My Course"),
        description=lesson_data.get("description", ""),
        estimated_duration=lesson_data.get("estimated_duration", ""),
        objectives=lesson_data.get("objectives", [])[:8],
        chapters=chapters,
        redis_token=token,
        total_pages=total_pages,
    )


# ── ENDPOINT 2: YouTube Search ────────────────────────────────────────────────

@router.get(
    "/course-builder/youtube",
    response_model=list[YouTubeVideo],
    summary="Search YouTube for video suggestions",
)
async def search_youtube(
    query: str,
    max_results: int = 5,
    user: AxisUser = Depends(get_current_user),
):
    """Search YouTube Data API v3. Requires YOUTUBE_API_KEY env var."""
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        raise HTTPException(503, "YouTube API key not configured (YOUTUBE_API_KEY)")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                _YOUTUBE_SEARCH_URL,
                params={
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "videoDuration": "medium",
                    "videoEmbeddable": "true",
                    "order": "relevance",
                    "maxResults": min(int(max_results), 5),
                    "key": api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        log.error("youtube_api_error", status=e.response.status_code)
        raise HTTPException(502, f"YouTube API error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(500, f"YouTube search failed: {e}")

    videos = []
    for item in data.get("items", []):
        vid_id = item.get("id", {}).get("videoId", "")
        snippet = item.get("snippet", {})
        if not vid_id:
            continue
        thumbs = snippet.get("thumbnails", {})
        thumb_url = (
            (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {})
            .get("url", "")
        )
        videos.append(YouTubeVideo(
            video_id=vid_id,
            title=snippet.get("title", ""),
            channel=snippet.get("channelTitle", ""),
            thumbnail_url=thumb_url,
            embed_url=f"https://www.youtube.com/embed/{vid_id}",
        ))

    return videos


# ── ENDPOINT 3: Generate Course ───────────────────────────────────────────────

@router.post(
    "/course-builder/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Learning Space + kick off all chapter generation jobs",
)
async def generate_course(
    req: GenerateRequest,
    user: AxisUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    1. Read per-page text from Redis (via redis_token from analyze step)
    2. For each included chapter: write text to temp file, create ContentItem + Job
    3. For each YouTube video: create ContentItem of type youtube
    4. Fire standard run_pipeline Celery tasks for all items
    5. Return space_id + chapter job list for frontend progress polling
    """
    if user.role not in ("admin", "creator"):
        raise HTTPException(403, "Creator or admin access required")

    from app.tasks.celery_app import celery_app

    # ── Load pages from Redis ─────────────────────────────────────────────
    redis_key = f"course_build:{req.redis_token}"
    try:
        redis = await get_redis()
        raw = await redis.get(redis_key)
    except Exception as e:
        raise HTTPException(500, f"Redis read failed: {e}")

    if not raw:
        raise HTTPException(
            410, "Course build session expired — please re-upload your PDF"
        )

    pages_text: list[str] = json.loads(raw)

    # ── Create Learning Space ─────────────────────────────────────────────
    space_title = (req.space_title or "My Course").strip()
    space = LearningSpace(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        creator_id=user.id,
        title=space_title,
        slug=_unique_slug(space_title),
        description=(req.space_description or "").strip(),
        is_published=False,
        is_guest_accessible=False,
        tags=[],
    )
    db.add(space)
    await db.flush()

    # ── Temp directory for chapter text files ─────────────────────────────
    _course_tmp = _get_tmp_dir()
    _course_tmp.mkdir(parents=True, exist_ok=True)
    session_dir = _course_tmp / req.redis_token
    session_dir.mkdir(exist_ok=True)

    chapter_statuses: list[ChapterJobStatus] = []
    position = 0

    included = [ch for ch in req.chapters if ch.include]

    for ch_idx, chapter in enumerate(included):
        start_idx = max(0, chapter.page_start - 1)
        end_idx = min(len(pages_text), chapter.page_end)
        chapter_text = "\n\n".join(pages_text[start_idx:end_idx]).strip()

        if not chapter_text:
            log.warning("course_builder_empty_chapter", title=chapter.title)
            continue

        # Write chapter text to a temp file (TextExtractor handles file:// URLs)
        txt_file = session_dir / f"chapter_{ch_idx:03d}.txt"
        txt_file.write_text(chapter_text, encoding="utf-8")

        new_asset_id = uuid.uuid4()

        content_item = ContentItem(
            id=uuid.uuid4(),
            tenant_id=user.tenant_id,
            origin=ContentOrigin.SPACE.value,
            space_id=space.id,
            asset_id=new_asset_id,
            moodle_course_id=None,
            moodle_cmid=None,
            content_type=ContentType.TEXT.value,
            source_url=f"file://{txt_file}",
            title=chapter.title,
            status=ContentStatus.PENDING.value,
            experience_mode="standard",
            content_hash=str(new_asset_id),
            quiz_count=chapter.quiz_count,
            processing_config={
                "tasks": chapter.generate_tasks,
                "options": {"quiz_count": chapter.quiz_count},
            },
            moodle_metadata={
                "course_builder": True,
                "chapter_index": ch_idx,
                "page_start": chapter.page_start,
                "page_end": chapter.page_end,
                "uploaded_by": str(user.id),
                "space_id": str(space.id),
            },
        )
        db.add(content_item)
        await db.flush()

        space_item = SpaceItem(
            id=uuid.uuid4(),
            space_id=space.id,
            content_item_id=content_item.id,
            position=position,
            is_visible=True,
            visible_outputs=chapter.generate_tasks,
        )
        db.add(space_item)
        position += 1

        job = ProcessingJob(
            id=uuid.uuid4(),
            content_item_id=content_item.id,
            tenant_id=user.tenant_id,
            job_type=JobType.FULL_PIPELINE,
            status=JobStatus.QUEUED,
            progress=0,
            progress_message="Queued",
            job_config={
                "tasks": chapter.generate_tasks,
                "options": {"quiz_count": chapter.quiz_count},
            },
        )
        db.add(job)
        await db.flush()

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

        chapter_statuses.append(ChapterJobStatus(
            chapter_title=chapter.title,
            content_item_id=str(content_item.id),
            job_id=str(job.id),
            status="queued",
            progress_pct=0,
        ))

    # ── Add YouTube videos ────────────────────────────────────────────────
    for yt in req.youtube_videos:
        yt_asset_id = uuid.uuid4()
        yt_item = ContentItem(
            id=uuid.uuid4(),
            tenant_id=user.tenant_id,
            origin=ContentOrigin.SPACE.value,
            space_id=space.id,
            asset_id=yt_asset_id,
            moodle_course_id=None,
            moodle_cmid=None,
            content_type=ContentType.YOUTUBE.value,
            source_url=f"https://www.youtube.com/watch?v={yt.video_id}",
            title=yt.title or f"Video {yt.video_id}",
            status=ContentStatus.PENDING.value,
            experience_mode="standard",
            content_hash=str(yt_asset_id),
            processing_config={"tasks": ["summary", "quiz", "flashcards", "discussion_prompts"], "options": {}},
            moodle_metadata={
                "thumbnail_url": yt.thumbnail_url,
                "chapter_index": yt.chapter_index,
                "uploaded_by": str(user.id),
                "space_id": str(space.id),
            },
        )
        db.add(yt_item)
        await db.flush()

        db.add(SpaceItem(
            id=uuid.uuid4(),
            space_id=space.id,
            content_item_id=yt_item.id,
            position=position,
            is_visible=True,
            visible_outputs=["summary", "quiz", "flashcards", "discussion_prompts"],
        ))
        position += 1

        yt_job = ProcessingJob(
            id=uuid.uuid4(),
            content_item_id=yt_item.id,
            tenant_id=user.tenant_id,
            job_type=JobType.FULL_PIPELINE,
            status=JobStatus.QUEUED,
            progress=0,
            progress_message="Queued",
            job_config={"tasks": ["summary", "quiz", "flashcards", "discussion_prompts"], "options": {}},
        )
        db.add(yt_job)
        await db.flush()

        celery_app.send_task(
            "app.tasks.process_content.run_pipeline",
            kwargs={
                "job_id": str(yt_job.id),
                "content_item_id": str(yt_item.id),
                "tenant_id": str(user.tenant_id),
                "job_config": yt_job.job_config,
                "axis_user_id": str(user.id),
            },
            queue="default",
        )

    await db.commit()

    log.info(
        "course_builder_generated",
        user_id=str(user.id),
        space_id=str(space.id),
        chapters=len(chapter_statuses),
        youtube_videos=len(req.youtube_videos),
    )

    return GenerateResponse(
        space_id=str(space.id),
        space_title=space.title,
        chapters=chapter_statuses,
        total_chapters=len(chapter_statuses),
    )


# ── ENDPOINT 4: Poll Progress ─────────────────────────────────────────────────

@router.get(
    "/course-builder/progress/{space_id}",
    response_model=ProgressResponse,
    summary="Poll generation progress for all chapters in a space",
)
async def get_progress(
    space_id: str,
    user: AxisUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Query all content items + their latest processing jobs for a space.
    Frontend polls this every 3 s to drive the live progress screen.
    """
    try:
        sid = uuid.UUID(space_id)
    except ValueError:
        raise HTTPException(400, "Invalid space_id")

    space = await db.get(LearningSpace, sid)
    is_admin = getattr(user, "role", None) == "admin"
    if not space or (space.creator_id != user.id and not is_admin):
        raise HTTPException(404, "Space not found")

    items_result = await db.execute(
        select(SpaceItem)
        .where(SpaceItem.space_id == sid)
        .order_by(SpaceItem.position)
    )
    space_items = items_result.scalars().all()

    chapter_statuses: list[ChapterJobStatus] = []
    completed_count = 0

    for si in space_items:
        content_item = await db.get(ContentItem, si.content_item_id)
        if not content_item:
            continue

        job_result = await db.execute(
            select(ProcessingJob)
            .where(ProcessingJob.content_item_id == content_item.id)
            .order_by(ProcessingJob.created_at.desc())
            .limit(1)
        )
        job = job_result.scalar_one_or_none()

        job_status = "queued"
        job_id = None
        progress_pct = 0

        if job:
            job_id = str(job.id)
            raw_status = job.status.value if hasattr(job.status, "value") else str(job.status)
            job_status = raw_status
            progress_pct = job.progress or {
                "queued": 0, "processing": 50, "completed": 100, "failed": 100,
            }.get(raw_status, 0)

        if job_status == "completed":
            completed_count += 1

        chapter_statuses.append(ChapterJobStatus(
            chapter_title=content_item.title or "Chapter",
            content_item_id=str(content_item.id),
            job_id=job_id,
            status=job_status,
            progress_pct=progress_pct,
        ))

    total = len(chapter_statuses)
    return ProgressResponse(
        space_id=space_id,
        chapters=chapter_statuses,
        completed=completed_count,
        total=total,
        done=(total > 0 and completed_count == total),
    )
