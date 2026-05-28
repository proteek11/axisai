"""
Storage abstraction — supports local disk (Phase 1) and S3-compatible object storage (Phase 2).

Switch backends by setting AXIS_STORAGE_BACKEND=s3 in .env.
All call sites use the same helpers — no changes needed at the call site.

Local backend:  save_bytes() → returns "file:///data/axis/..." path
S3 backend:     save_bytes() → uploads to S3, returns public/CDN URL

SCORM packages always stay on local disk because the SCORM runtime reads
individual asset files from the filesystem at serve time.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Lazy-import config to avoid circular imports at module load time.
# ---------------------------------------------------------------------------
def _cfg():
    from app.config import settings
    return settings


# ---------------------------------------------------------------------------
# Local-disk helpers (always available, used for SCORM regardless of backend)
# ---------------------------------------------------------------------------

def _data_dir() -> Path:
    return Path(os.environ.get("AXIS_DATA_DIR", _cfg().axis_data_dir))


def get_scorm_package_dir(content_item_id: str) -> Path:
    """
    Return the directory where a SCORM package's extracted files live.
    Always local — SCORM runtime reads asset files directly from disk.
    """
    p = _data_dir() / "scorm" / content_item_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_data_dir() -> Path:
    return _data_dir()


# ---------------------------------------------------------------------------
# S3 client (lazily initialised — only when backend == "s3")
# ---------------------------------------------------------------------------
_s3_client = None

def _get_s3_client():
    global _s3_client
    if _s3_client is not None:
        return _s3_client
    try:
        import boto3
    except ImportError as e:
        raise RuntimeError("boto3 is required for S3 storage — already in pyproject.toml") from e

    cfg = _cfg()
    kwargs: dict = {
        "region_name": cfg.s3_region,
        "aws_access_key_id": cfg.s3_access_key_id or None,
        "aws_secret_access_key": cfg.s3_secret_access_key or None,
    }
    if cfg.s3_endpoint_url:
        kwargs["endpoint_url"] = cfg.s3_endpoint_url

    _s3_client = boto3.client("s3", **kwargs)
    log.info("s3_client_initialised", bucket=cfg.s3_bucket, region=cfg.s3_region,
             endpoint=cfg.s3_endpoint_url or "AWS default")
    return _s3_client


def _s3_public_url(key: str) -> str:
    """Build the public URL for an S3 object."""
    cfg = _cfg()
    if cfg.s3_cdn_url:
        base = cfg.s3_cdn_url.rstrip("/")
        return f"{base}/{key}"
    if cfg.s3_endpoint_url:
        # e.g. Cloudflare R2 or MinIO
        endpoint = cfg.s3_endpoint_url.rstrip("/")
        return f"{endpoint}/{cfg.s3_bucket}/{key}"
    # Standard AWS
    return f"https://{cfg.s3_bucket}.s3.{cfg.s3_region}.amazonaws.com/{key}"


def _s3_presigned_url(key: str, expires: int = 3600) -> str:
    """Generate a presigned download URL for a private S3 object."""
    client = _get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": _cfg().s3_bucket, "Key": key},
        ExpiresIn=expires,
    )


# ---------------------------------------------------------------------------
# Primary API
# ---------------------------------------------------------------------------

def save_bytes(relative_path: str, data: bytes) -> str:
    """
    Persist raw bytes and return a storable URL.

    Local backend:
        Writes to  <AXIS_DATA_DIR>/<relative_path>
        Returns    "file:///data/axis/<relative_path>"

    S3 backend:
        Uploads to S3 key  <relative_path>
        Returns    public CDN/S3 URL  (or presigned if s3_public=False)

    Store the returned string in the database (e.g. content_items.source_url).
    Use get_local_path() to resolve a file:// URL back to a filesystem path.
    """
    cfg = _cfg()

    if cfg.storage_backend == "s3":
        return _save_bytes_s3(relative_path, data)
    else:
        return _save_bytes_local(relative_path, data)


def _save_bytes_local(relative_path: str, data: bytes) -> str:
    abs_path = _data_dir() / relative_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(data)
    log.debug("storage_save_local", path=str(abs_path), size=len(data))
    return f"file://{abs_path}"


def _save_bytes_s3(relative_path: str, data: bytes) -> str:
    import io
    cfg = _cfg()
    client = _get_s3_client()
    key = relative_path.lstrip("/")

    extra_args: dict = {}
    if cfg.s3_public:
        extra_args["ACL"] = "public-read"

    client.upload_fileobj(
        io.BytesIO(data),
        cfg.s3_bucket,
        key,
        ExtraArgs=extra_args,
    )
    log.info("storage_save_s3", bucket=cfg.s3_bucket, key=key, size=len(data))

    if cfg.s3_public:
        return _s3_public_url(key)
    return _s3_presigned_url(key)


def get_local_path(source_url: str) -> Optional[str]:
    """
    Given a source_url from the database, return the local filesystem path.
    Returns None if this is not a file:// URL (e.g. it's already an S3/CDN URL).
    """
    if source_url.startswith("file://"):
        return source_url[7:]   # strip "file://"
    return None


def is_remote_url(source_url: str) -> bool:
    """True if the stored URL points to a remote resource (S3, CDN, https)."""
    return source_url.startswith("http://") or source_url.startswith("https://")


def get_download_url(source_url: str, expires: int = 3600) -> str:
    """
    Given a stored source_url, return a URL suitable for redirecting a browser to.

    - file://  → raises ValueError (can't redirect to local path; use serve_library_file)
    - https:// → returned as-is if bucket is public; presigned if private
    - Other    → returned as-is
    """
    if source_url.startswith("file://"):
        raise ValueError("file:// URLs must be served via serve_library_file, not redirected")

    cfg = _cfg()
    if cfg.storage_backend == "s3" and not cfg.s3_public and source_url.startswith("https://"):
        # Re-generate a fresh presigned URL from the S3 key
        # Extract key from URL
        if cfg.s3_cdn_url and source_url.startswith(cfg.s3_cdn_url):
            key = source_url[len(cfg.s3_cdn_url):].lstrip("/")
        elif cfg.s3_endpoint_url and source_url.startswith(cfg.s3_endpoint_url):
            key = "/".join(source_url.split("/")[4:])  # strip endpoint+bucket
        else:
            # Standard AWS path: https://bucket.s3.region.amazonaws.com/key
            key = "/".join(source_url.split("/")[3:])
        return _s3_presigned_url(key, expires=expires)

    return source_url


def delete_tree(relative_path: str) -> None:
    """
    Delete a file tree or S3 prefix.

    Local: removes directory recursively.
    S3:    deletes all objects whose key starts with relative_path.
    """
    cfg = _cfg()

    if cfg.storage_backend == "s3":
        _delete_prefix_s3(relative_path)
    else:
        _delete_tree_local(relative_path)


def _delete_tree_local(relative_path: str) -> None:
    abs_path = _data_dir() / relative_path
    if abs_path.exists():
        shutil.rmtree(abs_path)
        log.info("storage_delete_tree_local", path=str(abs_path))


def _delete_prefix_s3(prefix: str) -> None:
    cfg = _cfg()
    client = _get_s3_client()
    key_prefix = prefix.lstrip("/")

    paginator = client.get_paginator("list_objects_v2")
    deleted = 0
    for page in paginator.paginate(Bucket=cfg.s3_bucket, Prefix=key_prefix):
        objects = page.get("Contents", [])
        if not objects:
            continue
        client.delete_objects(
            Bucket=cfg.s3_bucket,
            Delete={"Objects": [{"Key": obj["Key"]} for obj in objects]},
        )
        deleted += len(objects)
    log.info("storage_delete_prefix_s3", bucket=cfg.s3_bucket, prefix=key_prefix, deleted=deleted)
