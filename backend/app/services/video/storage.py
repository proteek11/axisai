"""
VideoStorageService — upload rendered MP4s and thumbnails.

Two backends:
  local — copies file to VIDEO_OUTPUT_DIR/{tenant_id}/{job_id}/{filename}
          served by nginx at VIDEO_OUTPUT_BASE_URL (configured in .env).
  s3    — uploads via boto3 to VIDEO_S3_BUCKET, returns CDN or direct S3 URL.

Both backends are async-safe: blocking I/O runs in a thread pool executor.

Output path convention (mirrors arch doc §13.4):
  local:  {VIDEO_OUTPUT_DIR}/{tenant_id}/{job_id}/{filename}
  S3 key: videos/{tenant_id}/{job_id}/{filename}
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import structlog

from app.config import settings

log = structlog.get_logger(__name__)


class VideoStorageService:
    """Upload finished video assets to the configured storage backend."""

    async def upload_mp4(self, local_path: Path, tenant_id: str, job_id: str) -> str:
        """Upload the final MP4 and return its public URL."""
        return await self._upload(local_path, tenant_id, job_id, "output.mp4")

    async def upload_thumbnail(self, local_path: Path, tenant_id: str, job_id: str) -> str:
        """Upload the thumbnail and return its public URL."""
        return await self._upload(local_path, tenant_id, job_id, "thumb.jpg")

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _upload(
        self,
        local_path: Path,
        tenant_id: str,
        job_id: str,
        filename: str,
    ) -> str:
        if settings.video_storage == "s3":
            return await self._upload_s3(local_path, tenant_id, job_id, filename)
        return await self._upload_local(local_path, tenant_id, job_id, filename)

    # ── Local storage ─────────────────────────────────────────────────────────

    async def _upload_local(
        self,
        local_path: Path,
        tenant_id: str,
        job_id: str,
        filename: str,
    ) -> str:
        dest_dir = Path(settings.video_output_dir) / tenant_id / job_id
        dest_path = dest_dir / filename

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._copy_local, local_path, dest_dir, dest_path)

        base_url = settings.video_output_base_url.rstrip("/")
        if not base_url:
            raise ValueError(
                "VIDEO_OUTPUT_BASE_URL is not configured. "
                "Set it in .env to the public URL where nginx serves VIDEO_OUTPUT_DIR."
            )
        url = f"{base_url}/{tenant_id}/{job_id}/{filename}"
        log.info("video_stored_local", dest=str(dest_path), url=url)
        return url

    @staticmethod
    def _copy_local(src: Path, dest_dir: Path, dest_path: Path) -> None:
        """Blocking copy — runs in executor."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest_path))

    # ── S3 storage ────────────────────────────────────────────────────────────

    async def _upload_s3(
        self,
        local_path: Path,
        tenant_id: str,
        job_id: str,
        filename: str,
    ) -> str:
        s3_key = f"videos/{tenant_id}/{job_id}/{filename}"

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            self._do_s3_upload,
            local_path,
            s3_key,
        )

        # Return CDN URL if configured, otherwise direct S3 URL
        if settings.video_s3_cdn_url:
            url = f"{settings.video_s3_cdn_url.rstrip('/')}/{s3_key}"
        else:
            region = settings.video_s3_region
            bucket = settings.video_s3_bucket
            url = f"https://{bucket}.s3.{region}.amazonaws.com/{s3_key}"

        log.info("video_stored_s3", key=s3_key, url=url)
        return url

    @staticmethod
    def _do_s3_upload(local_path: Path, s3_key: str) -> None:
        """Blocking S3 upload — runs in executor."""
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        session_kwargs: dict = {}
        if settings.video_s3_access_key_id:
            session_kwargs["aws_access_key_id"]     = settings.video_s3_access_key_id
            session_kwargs["aws_secret_access_key"] = settings.video_s3_secret_access_key

        s3 = boto3.client("s3", region_name=settings.video_s3_region, **session_kwargs)

        content_type = "video/mp4" if s3_key.endswith(".mp4") else "image/jpeg"
        try:
            s3.upload_file(
                str(local_path),
                settings.video_s3_bucket,
                s3_key,
                ExtraArgs={
                    "ContentType": content_type,
                    "CacheControl": "public, max-age=31536000",  # 1 year
                },
            )
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError(f"S3 upload failed for key '{s3_key}': {exc}") from exc
