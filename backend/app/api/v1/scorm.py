"""
SCORM API — upload, serve metadata, runtime session, and reports.

Endpoints:
  POST /scorm/upload                         — upload .zip, parse manifest, extract
  GET  /scorm/{content_item_id}              — package metadata
  GET  /scorm/{content_item_id}/session      — get/create learner session (for resume)
  POST /scorm/{content_item_id}/commit       — save cmi.* data mid-session
  POST /scorm/{content_item_id}/finish       — mark session terminated/complete
  POST /scorm/{content_item_id}/new-attempt  — start a fresh attempt
  GET  /spaces/{space_id}/scorm-report       — all learners × all SCORM items
  GET  /scorm/{content_item_id}/report/csv   — CSV download for one item
"""
import csv
import io
import json
import os
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiofiles
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Security, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.core.storage import get_scorm_package_dir, delete_tree
from app.models.content import ContentItem, ContentOrigin, ContentStatus, ContentType
from app.models.scorm import ScormPackage, ScormSession
from app.models.space import LearningSpace, SpaceItem
from app.models.user import AxisUser
from app.utils.scorm_parser import parse_manifest

log = structlog.get_logger(__name__)
router = APIRouter(tags=["scorm"])
_bearer = HTTPBearer()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _require_creator(
    credentials: HTTPAuthorizationCredentials, db: AsyncSession
) -> AxisUser:
    user = await get_current_user(credentials.credentials, db)
    if user.role not in ("creator", "admin"):
        raise HTTPException(403, "Creator or admin access required")
    return user


async def _require_any_user(
    credentials: HTTPAuthorizationCredentials, db: AsyncSession
) -> AxisUser:
    return await get_current_user(credentials.credentials, db)



def _session_to_dict(s) -> dict:
    """Serialize a ScormSession row to a response dict."""
    return {
        "attempt_number": s.attempt_number,
        "completion_status": s.completion_status,
        "success_status": s.success_status,
        "score_raw": s.score_raw,
        "score_scaled": s.score_scaled,
        "total_time_seconds": s.total_time_seconds,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
    }

def _parse_scorm_time(time_str: Optional[str]) -> int:
    """Convert SCORM time strings to seconds. Handles HH:MM:SS and PT#H#M#S."""
    if not time_str:
        return 0
    try:
        # ISO 8601 / SCORM 2004: PTxHxMxS
        if time_str.startswith("PT"):
            import re
            h = int(re.search(r"(\d+)H", time_str).group(1)) if "H" in time_str else 0
            m = int(re.search(r"(\d+)M", time_str).group(1)) if "M" in time_str else 0
            s = float(re.search(r"([\d.]+)S", time_str).group(1)) if "S" in time_str else 0
            return int(h * 3600 + m * 60 + s)
        # SCORM 1.2: HH:MM:SS or HH:MM:SS.ss
        parts = time_str.split(":")
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
            return int(h * 3600 + m * 60 + s)
    except Exception:
        pass
    return 0


def _extract_status_from_cmi(cmi: dict, scorm_version: str) -> dict:
    """
    Pull completion_status, success_status, score_* from a raw cmi dict.
    Normalises SCORM 1.2 and 2004 field names to our canonical names.
    """
    result = {
        "completion_status": "unknown",
        "success_status": "unknown",
        "score_raw": None,
        "score_min": None,
        "score_max": None,
        "score_scaled": None,
        "lesson_location": None,
        "suspend_data": None,
        "total_time_seconds": 0,
    }
    if not cmi:
        return result

    if scorm_version == "1.2":
        core = cmi.get("core", cmi)  # scorm-again flattens under "core" for 1.2
        ls = core.get("lesson_status", "")
        # SCORM 1.2 uses one field for both completion and success
        if ls in ("completed", "passed", "failed", "incomplete", "browsed", "not attempted"):
            if ls in ("passed", "failed"):
                result["success_status"] = ls
                result["completion_status"] = "completed" if ls == "passed" else "completed"
            elif ls == "completed":
                result["completion_status"] = "completed"
                result["success_status"] = "unknown"
            elif ls == "incomplete":
                result["completion_status"] = "incomplete"
            else:
                result["completion_status"] = "not_attempted"

        score = core.get("score", {})
        if isinstance(score, dict):
            result["score_raw"] = _safe_float(score.get("raw"))
            result["score_min"] = _safe_float(score.get("min"))
            result["score_max"] = _safe_float(score.get("max"))
        result["lesson_location"] = core.get("lesson_location") or cmi.get("lesson_location")
        result["suspend_data"] = cmi.get("suspend_data")
        result["total_time_seconds"] = _parse_scorm_time(core.get("total_time") or cmi.get("total_time"))
    else:
        # SCORM 2004
        result["completion_status"] = cmi.get("completion_status", "unknown")
        result["success_status"] = cmi.get("success_status", "unknown")
        score = cmi.get("score", {})
        if isinstance(score, dict):
            result["score_raw"] = _safe_float(score.get("raw"))
            result["score_min"] = _safe_float(score.get("min"))
            result["score_max"] = _safe_float(score.get("max"))
            result["score_scaled"] = _safe_float(score.get("scaled"))
        result["lesson_location"] = cmi.get("location")
        result["suspend_data"] = cmi.get("suspend_data")
        result["total_time_seconds"] = _parse_scorm_time(cmi.get("total_time"))

    return result


def _safe_float(val) -> Optional[float]:
    try:
        return float(val) if val is not None and val != "" else None
    except (TypeError, ValueError):
        return None


# ── Schemas ───────────────────────────────────────────────────────────────────

class ScormPackageResponse(BaseModel):
    content_item_id: str
    scorm_version: str
    entry_point: str
    title: str
    sco_count: int
    file_count: Optional[int]
    package_size_bytes: Optional[int]
    passing_score: Optional[float]
    scorm_url_base: str  # URL prefix learner iframe loads from

    class Config:
        from_attributes = True


class ScormSessionResponse(BaseModel):
    session_id: str
    attempt_number: int
    completion_status: str
    success_status: str
    score_raw: Optional[float]
    score_scaled: Optional[float]
    lesson_location: Optional[str]
    suspend_data: Optional[str]
    cmi_data: Optional[dict]
    total_time_seconds: int
    started_at: str
    last_accessed_at: str
    completed_at: Optional[str]
    attempts_used: int
    max_attempts: Optional[int]


class CommitRequest(BaseModel):
    space_id: str
    attempt_number: int
    cmi_data: dict


class FinishRequest(BaseModel):
    space_id: str
    attempt_number: int
    cmi_data: dict


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/scorm/upload")
async def upload_scorm(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    is_public: str = Form(default="false"),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a SCORM .zip package.
    - Validates the ZIP contains imsmanifest.xml
    - Parses the manifest (version, entry point, SCO list, passing score)
    - Extracts files to /data/axis/scorm/{content_item_id}/
    - Creates ContentItem (content_type=scorm, status=ready) + ScormPackage row
    - No AI pipeline run (SCORM content is self-contained)
    """
    user = await _require_creator(credentials, db)

    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(400, "Only .zip files are accepted for SCORM upload")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(400, "Empty file")

    # Validate it's a real zip
    try:
        zf = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile:
        raise HTTPException(400, "File is not a valid ZIP archive")

    # Must contain imsmanifest.xml
    names = zf.namelist()
    manifest_name = next((n for n in names if n.lower() == "imsmanifest.xml"), None)
    if not manifest_name:
        raise HTTPException(
            400,
            "Not a valid SCORM package — imsmanifest.xml not found in the ZIP root"
        )

    # Create ContentItem
    asset_id = uuid.uuid4()
    content_id = uuid.uuid4()
    pub = is_public.lower() in ("true", "1", "yes")

    content_item = ContentItem(
        id=content_id,
        tenant_id=user.tenant_id,
        origin=ContentOrigin.SPACE.value,
        space_id=None,
        asset_id=asset_id,
        creator_id=user.id,
        moodle_course_id=None,
        moodle_cmid=None,
        content_type=ContentType.SCORM.value,
        title=title or file.filename or "SCORM Package",
        source_url=f"scorm://{content_id}",  # special scheme — files on disk
        status=ContentStatus.READY.value,     # SCORM is ready immediately after extract
        is_public=pub,
        experience_mode="standard",
        file_size_bytes=len(file_bytes),
        processing_config={},
        moodle_metadata={},
    )
    db.add(content_item)
    await db.flush()  # get content_item.id before extracting files

    # Extract files to storage
    package_dir = get_scorm_package_dir(str(content_id))
    try:
        zf.extractall(package_dir)
    except Exception as e:
        await db.rollback()
        log.error("scorm_extract_failed", error=str(e))
        raise HTTPException(500, f"Failed to extract SCORM package: {e}")

    # Parse manifest
    manifest_path = package_dir / manifest_name
    try:
        parsed = parse_manifest(manifest_path)
    except ValueError as e:
        # Clean up extracted files
        delete_tree(f"scorm/{content_id}")
        await db.rollback()
        raise HTTPException(400, str(e))

    # Create ScormPackage row
    scorm_pkg = ScormPackage(
        id=uuid.uuid4(),
        content_item_id=content_id,
        scorm_version=parsed["scorm_version"],
        entry_point=parsed["entry_point"],
        package_title=parsed["title"],
        sco_list=parsed["sco_list"],
        manifest_data=parsed["manifest_data"],
        file_count=len(names),
        package_size_bytes=len(file_bytes),
        passing_score=parsed.get("passing_score"),
        max_time_allowed=parsed.get("max_time_allowed"),
    )
    db.add(scorm_pkg)

    # Update ContentItem title from manifest if not provided
    if not title and parsed["title"]:
        content_item.title = parsed["title"]

    await db.commit()

    log.info(
        "scorm_uploaded",
        content_item_id=str(content_id),
        scorm_version=parsed["scorm_version"],
        entry_point=parsed["entry_point"],
        file_count=len(names),
        user_id=str(user.id),
    )

    return {
        "content_item_id": str(content_id),
        "scorm_version": parsed["scorm_version"],
        "entry_point": parsed["entry_point"],
        "title": content_item.title,
        "sco_count": len(parsed.get("sco_list") or []),
        "file_count": len(names),
        "package_size_bytes": len(file_bytes),
        "passing_score": parsed.get("passing_score"),
    }




# ── Replace SCORM package ─────────────────────────────────────────────────────

@router.post("/scorm/{content_item_id}/replace")
async def replace_scorm_package(
    content_item_id: uuid.UUID,
    file: UploadFile = File(...),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """
    Replace the SCORM .zip for an existing content item.
    - Old extracted files are deleted from disk
    - New package is validated, extracted and ScormPackage row is updated
    - All ScormSessions are preserved (history intact for reporting)
    - Content item status stays READY immediately (no pipeline)
    """
    user = await _require_creator(credentials, db)

    # Load and check ownership
    ci = (
        await db.execute(
            select(ContentItem).where(
                ContentItem.id == content_item_id,
                ContentItem.creator_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if not ci:
        raise HTTPException(404, "SCORM content item not found or access denied")
    if str(ci.content_type) not in ("scorm", "ContentType.SCORM"):
        raise HTTPException(400, "Content item is not a SCORM package")

    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(400, "Only .zip files are accepted for SCORM upload")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(400, "Empty file")

    # Validate ZIP
    try:
        zf = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile:
        raise HTTPException(400, "File is not a valid ZIP archive")

    names = zf.namelist()
    manifest_name = next((n for n in names if n.lower() == "imsmanifest.xml"), None)
    if not manifest_name:
        raise HTTPException(400, "Not a valid SCORM package — imsmanifest.xml not found in the ZIP root")

    # Delete old extracted files
    try:
        delete_tree(f"scorm/{content_item_id}")
    except Exception as e:
        log.warning("scorm_old_files_delete_failed", error=str(e))

    # Extract new package
    package_dir = get_scorm_package_dir(str(content_item_id))
    try:
        zf.extractall(package_dir)
    except Exception as e:
        raise HTTPException(500, f"Failed to extract SCORM package: {e}")

    # Parse manifest
    manifest_path = package_dir / manifest_name
    try:
        parsed = parse_manifest(manifest_path)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Update/upsert ScormPackage row
    existing_pkg = (
        await db.execute(
            select(ScormPackage).where(ScormPackage.content_item_id == content_item_id)
        )
    ).scalar_one_or_none()

    if existing_pkg:
        existing_pkg.scorm_version = parsed["scorm_version"]
        existing_pkg.entry_point = parsed["entry_point"]
        existing_pkg.package_title = parsed["title"]
        existing_pkg.sco_list = parsed["sco_list"]
        existing_pkg.manifest_data = parsed["manifest_data"]
        existing_pkg.file_count = len(names)
        existing_pkg.package_size_bytes = len(file_bytes)
        existing_pkg.passing_score = parsed.get("passing_score")
        existing_pkg.max_time_allowed = parsed.get("max_time_allowed")
    else:
        db.add(ScormPackage(
            id=uuid.uuid4(),
            content_item_id=content_item_id,
            scorm_version=parsed["scorm_version"],
            entry_point=parsed["entry_point"],
            package_title=parsed["title"],
            sco_list=parsed["sco_list"],
            manifest_data=parsed["manifest_data"],
            file_count=len(names),
            package_size_bytes=len(file_bytes),
            passing_score=parsed.get("passing_score"),
            max_time_allowed=parsed.get("max_time_allowed"),
        ))

    # Update ContentItem
    ci.file_size_bytes = len(file_bytes)
    ci.status = ContentStatus.READY.value
    if parsed["title"]:
        ci.title = parsed["title"]

    await db.commit()

    log.info(
        "scorm_package_replaced",
        content_item_id=str(content_item_id),
        scorm_version=parsed["scorm_version"],
        user_id=str(user.id),
    )

    return {
        "content_item_id": str(content_item_id),
        "scorm_version": parsed["scorm_version"],
        "entry_point": parsed["entry_point"],
        "title": ci.title,
        "sco_count": len(parsed.get("sco_list") or []),
        "file_count": len(names),
        "package_size_bytes": len(file_bytes),
        "passing_score": parsed.get("passing_score"),
        "message": "SCORM package replaced. Learner session history is preserved.",
    }

# ── Package metadata ──────────────────────────────────────────────────────────

@router.get("/scorm/{content_item_id}")
async def get_scorm_package(
    content_item_id: uuid.UUID,
    space_id: Optional[str] = Query(None),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """Get SCORM package metadata + space-specific config (attempts, trigger)."""
    user = await _require_any_user(credentials, db)

    r = await db.execute(
        select(ScormPackage).where(ScormPackage.content_item_id == content_item_id)
    )
    pkg = r.scalar_one_or_none()
    if not pkg:
        raise HTTPException(404, "SCORM package not found")

    space_config = {}
    if space_id:
        r2 = await db.execute(
            select(SpaceItem).where(
                and_(
                    SpaceItem.space_id == uuid.UUID(space_id),
                    SpaceItem.content_item_id == content_item_id,
                )
            )
        )
        si = r2.scalar_one_or_none()
        if si:
            space_config = {
                "scorm_completion_trigger": si.scorm_completion_trigger,
                "scorm_max_attempts": si.scorm_max_attempts,
                "scorm_grade_aggregation": si.scorm_grade_aggregation,
            }

    return {
        "content_item_id": str(content_item_id),
        "scorm_version": pkg.scorm_version,
        "entry_point": pkg.entry_point,
        "title": pkg.package_title,
        "sco_count": len(pkg.sco_list or []),
        "file_count": pkg.file_count,
        "package_size_bytes": pkg.package_size_bytes,
        "passing_score": pkg.passing_score,
        "scorm_url_base": f"/api/v1/scorm/{content_item_id}/serve/",
        **space_config,
    }


# ── Static file serving ───────────────────────────────────────────────────────

@router.get("/scorm/{content_item_id}/serve/{file_path:path}")
async def serve_scorm_file(
    content_item_id: uuid.UUID,
    file_path: str,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """
    Serve individual files from an extracted SCORM package.
    Checks JWT auth so only valid users can load SCORM content.
    In production, replace with Nginx X-Accel-Redirect for performance.
    """
    await _require_any_user(credentials, db)

    # Security: prevent path traversal
    pkg_dir = get_scorm_package_dir(str(content_item_id))
    try:
        target = (pkg_dir / file_path).resolve()
        pkg_dir.resolve()
        target.relative_to(pkg_dir.resolve())  # raises ValueError if outside
    except ValueError:
        raise HTTPException(400, "Invalid file path")

    if not target.exists():
        raise HTTPException(404, f"File not found: {file_path}")

    from fastapi.responses import FileResponse
    # Determine media type
    suffix = target.suffix.lower()
    media_map = {
        ".html": "text/html", ".htm": "text/html",
        ".js": "application/javascript", ".css": "text/css",
        ".json": "application/json", ".xml": "application/xml",
        ".png": "image/png", ".jpg": "image/jpeg", ".gif": "image/gif",
        ".svg": "image/svg+xml", ".mp4": "video/mp4",
        ".mp3": "audio/mpeg", ".woff": "font/woff", ".woff2": "font/woff2",
        ".ttf": "font/ttf",
    }
    media_type = media_map.get(suffix, "application/octet-stream")
    return FileResponse(str(target), media_type=media_type)


# ── Session (runtime) ─────────────────────────────────────────────────────────

@router.get("/scorm/{content_item_id}/session")
async def get_scorm_session(
    content_item_id: uuid.UUID,
    space_id: str = Query(...),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the learner's latest SCORM session for resume.
    If no session exists, returns empty session data (attempt_number=1).
    Also returns how many total attempts used and the max allowed.
    """
    user = await _require_any_user(credentials, db)
    sid = uuid.UUID(space_id)

    # All attempts for this learner × item × space
    r = await db.execute(
        select(ScormSession)
        .where(and_(
            ScormSession.content_item_id == content_item_id,
            ScormSession.user_id == user.id,
            ScormSession.space_id == sid,
        ))
        .order_by(ScormSession.attempt_number.desc())
    )
    sessions = r.scalars().all()
    attempts_used = len(sessions)
    latest = sessions[0] if sessions else None

    # Get space config for max_attempts
    r2 = await db.execute(
        select(SpaceItem).where(and_(
            SpaceItem.space_id == sid,
            SpaceItem.content_item_id == content_item_id,
        ))
    )
    si = r2.scalar_one_or_none()
    max_attempts = si.scorm_max_attempts if si else None

    # Compute derived fields
    can_new = (max_attempts is None or attempts_used < max_attempts)
    attempts_remaining = (max_attempts - attempts_used) if max_attempts is not None else None

    # Past attempts summary (all except latest, oldest first)
    past = [_session_to_dict(s) for s in reversed(sessions[1:])] if len(sessions) > 1 else []

    if not latest:
        return {
            "session_id": None,
            "attempt_number": 1,
            "completion_status": "not_attempted",
            "success_status": "unknown",
            "score_raw": None,
            "score_scaled": None,
            "lesson_location": None,
            "suspend_data": None,
            "cmi_data": None,
            "total_time_seconds": 0,
            "started_at": None,
            "last_accessed_at": None,
            "completed_at": None,
            "attempts_used": 0,
            "attempts_remaining": attempts_remaining,
            "can_new_attempt": can_new,
            "max_attempts": max_attempts,
            "past_attempts": [],
        }

    return {
        "session_id": str(latest.id),
        "attempt_number": latest.attempt_number,
        "completion_status": latest.completion_status,
        "success_status": latest.success_status,
        "score_raw": latest.score_raw,
        "score_scaled": latest.score_scaled,
        "lesson_location": latest.lesson_location,
        "suspend_data": latest.suspend_data,
        "cmi_data": latest.cmi_data,
        "total_time_seconds": latest.total_time_seconds,
        "started_at": latest.started_at.isoformat(),
        "last_accessed_at": latest.last_accessed_at.isoformat(),
        "completed_at": latest.completed_at.isoformat() if latest.completed_at else None,
        "attempts_used": attempts_used,
        "attempts_remaining": attempts_remaining,
        "can_new_attempt": can_new,
        "max_attempts": max_attempts,
        "past_attempts": past,
    }


@router.post("/scorm/{content_item_id}/new-attempt")
async def new_scorm_attempt(
    content_item_id: uuid.UUID,
    space_id: str = Query(...),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new ScormSession row for the next attempt number.
    Checks max_attempts limit before creating.
    """
    user = await _require_any_user(credentials, db)
    sid = uuid.UUID(space_id)

    # Count existing attempts
    r = await db.execute(
        select(ScormSession).where(and_(
            ScormSession.content_item_id == content_item_id,
            ScormSession.user_id == user.id,
            ScormSession.space_id == sid,
        ))
    )
    existing = r.scalars().all()
    attempts_used = len(existing)

    # Check limit
    r2 = await db.execute(
        select(SpaceItem).where(and_(
            SpaceItem.space_id == sid,
            SpaceItem.content_item_id == content_item_id,
        ))
    )
    si = r2.scalar_one_or_none()
    max_attempts = si.scorm_max_attempts if si else None
    if max_attempts and attempts_used >= max_attempts:
        raise HTTPException(
            429, f"Maximum attempts ({max_attempts}) reached for this SCORM item"
        )

    new_attempt = attempts_used + 1
    session = ScormSession(
        id=uuid.uuid4(),
        content_item_id=content_item_id,
        user_id=user.id,
        space_id=sid,
        attempt_number=new_attempt,
        completion_status="not_attempted",
        success_status="unknown",
    )
    db.add(session)
    await db.commit()

    log.info("scorm_new_attempt", content_item_id=str(content_item_id),
             user_id=str(user.id), attempt=new_attempt)

    can_new_next = (max_attempts is None or new_attempt < max_attempts)
    att_remaining = (max_attempts - new_attempt) if max_attempts is not None else None

    return {
        "session_id": str(session.id),
        "attempt_number": new_attempt,
        "completion_status": "not_attempted",
        "success_status": "unknown",
        "score_raw": None,
        "score_scaled": None,
        "lesson_location": None,
        "suspend_data": None,
        "cmi_data": None,
        "total_time_seconds": 0,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "last_accessed_at": None,
        "completed_at": None,
        "attempts_used": new_attempt,
        "attempts_remaining": att_remaining,
        "can_new_attempt": can_new_next,
        "max_attempts": max_attempts,
        "past_attempts": [_session_to_dict(s) for s in sorted(existing, key=lambda x: x.attempt_number)],
    }


@router.post("/scorm/{content_item_id}/commit")
async def commit_scorm_session(
    content_item_id: uuid.UUID,
    body: CommitRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """
    Save cmi.* data snapshot. Called by scorm-again on every LMSCommit().
    Creates the session row on first commit if it doesn't exist yet.
    Updates mirrored status fields for fast reporting queries.
    """
    user = await _require_any_user(credentials, db)
    sid = uuid.UUID(body.space_id)

    # Find or create session for this attempt
    r = await db.execute(
        select(ScormSession).where(and_(
            ScormSession.content_item_id == content_item_id,
            ScormSession.user_id == user.id,
            ScormSession.space_id == sid,
            ScormSession.attempt_number == body.attempt_number,
        ))
    )
    session = r.scalar_one_or_none()

    if not session:
        session = ScormSession(
            id=uuid.uuid4(),
            content_item_id=content_item_id,
            user_id=user.id,
            space_id=sid,
            attempt_number=body.attempt_number,
        )
        db.add(session)

    # Get SCORM version for field name resolution
    r2 = await db.execute(
        select(ScormPackage).where(ScormPackage.content_item_id == content_item_id)
    )
    pkg = r2.scalar_one_or_none()
    scorm_version = pkg.scorm_version if pkg else "1.2"

    # Extract and mirror status fields
    status = _extract_status_from_cmi(body.cmi_data, scorm_version)
    session.cmi_data = body.cmi_data
    session.completion_status = status["completion_status"]
    session.success_status = status["success_status"]
    session.score_raw = status["score_raw"]
    session.score_min = status["score_min"]
    session.score_max = status["score_max"]
    session.score_scaled = status["score_scaled"]
    session.lesson_location = status["lesson_location"]
    session.suspend_data = status["suspend_data"]
    session.total_time_seconds = status["total_time_seconds"]
    session.last_accessed_at = datetime.now(timezone.utc)

    await db.commit()
    return {"saved": True, "completion_status": session.completion_status}


@router.post("/scorm/{content_item_id}/finish")
async def finish_scorm_session(
    content_item_id: uuid.UUID,
    body: FinishRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """
    Mark the SCORM session as terminated (LMSFinish / Terminate called).
    Saves final cmi.* data and sets completed_at timestamp.
    """
    user = await _require_any_user(credentials, db)
    sid = uuid.UUID(body.space_id)

    r = await db.execute(
        select(ScormSession).where(and_(
            ScormSession.content_item_id == content_item_id,
            ScormSession.user_id == user.id,
            ScormSession.space_id == sid,
            ScormSession.attempt_number == body.attempt_number,
        ))
    )
    session = r.scalar_one_or_none()
    if not session:
        # Create on finish if commit was never called (short packages)
        session = ScormSession(
            id=uuid.uuid4(),
            content_item_id=content_item_id,
            user_id=user.id,
            space_id=sid,
            attempt_number=body.attempt_number,
        )
        db.add(session)

    r2 = await db.execute(
        select(ScormPackage).where(ScormPackage.content_item_id == content_item_id)
    )
    pkg = r2.scalar_one_or_none()
    scorm_version = pkg.scorm_version if pkg else "1.2"

    status = _extract_status_from_cmi(body.cmi_data, scorm_version)
    session.cmi_data = body.cmi_data
    session.completion_status = status["completion_status"]
    session.success_status = status["success_status"]
    session.score_raw = status["score_raw"]
    session.score_min = status["score_min"]
    session.score_max = status["score_max"]
    session.score_scaled = status["score_scaled"]
    session.lesson_location = status["lesson_location"]
    session.suspend_data = status["suspend_data"]
    session.total_time_seconds = status["total_time_seconds"]
    session.last_accessed_at = datetime.now(timezone.utc)

    if status["completion_status"] in ("completed",) or status["success_status"] in ("passed", "failed"):
        session.completed_at = session.completed_at or datetime.now(timezone.utc)

    await db.commit()

    log.info(
        "scorm_session_finished",
        content_item_id=str(content_item_id),
        user_id=str(user.id),
        attempt=body.attempt_number,
        completion=session.completion_status,
        success=session.success_status,
        score=session.score_raw,
    )

    return {
        "saved": True,
        "completion_status": session.completion_status,
        "success_status": session.success_status,
        "score_raw": session.score_raw,
    }


# ── Reports ───────────────────────────────────────────────────────────────────

@router.get("/spaces/{space_id}/scorm-report")
async def space_scorm_report(
    space_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """
    All learners × all SCORM items in a space.
    Returns one row per learner per SCORM item (best/latest/avg based on space_item config).
    """
    user = await _require_creator(credentials, db)

    # Get all SCORM space_items
    r = await db.execute(
        select(SpaceItem)
        .join(ContentItem, SpaceItem.content_item_id == ContentItem.id)
        .where(and_(
            SpaceItem.space_id == space_id,
            ContentItem.content_type == ContentType.SCORM.value,
        ))
    )
    items = r.scalars().all()

    report = []
    for si in items:
        # All sessions for this item in this space
        r2 = await db.execute(
            select(ScormSession)
            .where(and_(
                ScormSession.content_item_id == si.content_item_id,
                ScormSession.space_id == space_id,
            ))
            .order_by(ScormSession.user_id, ScormSession.attempt_number)
        )
        sessions = r2.scalars().all()

        # Group by user
        by_user: dict[str, list] = {}
        for s in sessions:
            uid = str(s.user_id)
            by_user.setdefault(uid, []).append(s)

        # Get content item title
        r3 = await db.execute(
            select(ContentItem).where(ContentItem.id == si.content_item_id)
        )
        ci = r3.scalar_one_or_none()

        for uid, user_sessions in by_user.items():
            best = _aggregate_sessions(user_sessions, si.scorm_grade_aggregation)
            # Get user info
            r4 = await db.execute(
                select(AxisUser).where(AxisUser.id == uuid.UUID(uid))
            )
            u = r4.scalar_one_or_none()
            report.append({
                "content_item_id": str(si.content_item_id),
                "content_title": ci.title if ci else "",
                "user_id": uid,
                "user_name": u.name if u else "",
                "user_email": u.email if u else "",
                "attempts": len(user_sessions),
                "completion_status": best.completion_status,
                "success_status": best.success_status,
                "score_raw": best.score_raw,
                "score_max": best.score_max,
                "total_time_seconds": best.total_time_seconds,
                "last_accessed_at": best.last_accessed_at.isoformat(),
                "completed_at": best.completed_at.isoformat() if best.completed_at else None,
            })

    return {"space_id": str(space_id), "report": report}


@router.get("/scorm/{content_item_id}/report/csv")
async def scorm_csv_report(
    content_item_id: uuid.UUID,
    space_id: str = Query(...),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """Download a CSV of all learner sessions for one SCORM item."""
    user = await _require_creator(credentials, db)
    sid = uuid.UUID(space_id)

    r = await db.execute(
        select(ScormSession)
        .where(and_(
            ScormSession.content_item_id == content_item_id,
            ScormSession.space_id == sid,
        ))
        .order_by(ScormSession.user_id, ScormSession.attempt_number)
    )
    sessions = r.scalars().all()

    # Fetch content title
    r2 = await db.execute(select(ContentItem).where(ContentItem.id == content_item_id))
    ci = r2.scalar_one_or_none()
    item_title = ci.title if ci else str(content_item_id)

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Learner Name", "Email", "Attempt", "Completion Status",
        "Success Status", "Score", "Max Score", "Score %",
        "Time Spent (min)", "Started At", "Completed At",
    ])

    for s in sessions:
        r3 = await db.execute(select(AxisUser).where(AxisUser.id == s.user_id))
        u = r3.scalar_one_or_none()
        score_pct = ""
        if s.score_raw is not None and s.score_max:
            score_pct = f"{s.score_raw / s.score_max * 100:.1f}%"
        elif s.score_scaled is not None:
            score_pct = f"{s.score_scaled * 100:.1f}%"

        writer.writerow([
            u.name if u else "",
            u.email if u else "",
            s.attempt_number,
            s.completion_status,
            s.success_status,
            s.score_raw if s.score_raw is not None else "",
            s.score_max if s.score_max is not None else "",
            score_pct,
            round(s.total_time_seconds / 60, 1),
            s.started_at.strftime("%Y-%m-%d %H:%M") if s.started_at else "",
            s.completed_at.strftime("%Y-%m-%d %H:%M") if s.completed_at else "",
        ])

    output.seek(0)
    filename = f"scorm-report-{item_title[:40].replace(' ', '-')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _aggregate_sessions(sessions: list, mode: str):
    """Return the 'best' session according to grade aggregation mode."""
    if not sessions:
        return sessions[0] if sessions else None
    if mode == "latest":
        return max(sessions, key=lambda s: s.attempt_number)
    if mode == "average":
        # Return latest but with averaged score (for reporting)
        latest = max(sessions, key=lambda s: s.attempt_number)
        scores = [s.score_raw for s in sessions if s.score_raw is not None]
        if scores:
            latest.score_raw = sum(scores) / len(scores)
        return latest
    # "highest" (default)
    scored = [s for s in sessions if s.score_raw is not None]
    if scored:
        return max(scored, key=lambda s: s.score_raw)
    return max(sessions, key=lambda s: s.attempt_number)
