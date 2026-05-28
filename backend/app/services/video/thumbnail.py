"""
Thumbnail extraction — pulls a single frame from the finished MP4.

Output: 1280×720 JPEG, taken at seek_seconds (default 2s).

Uses ffmpeg via subprocess (run_in_executor for async safety).
Falls back to a plain black frame if ffmpeg extraction fails, so a missing
thumbnail never causes the entire video job to fail.
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)


async def extract(
    mp4_path: Path,
    output_path: Path,
    seek_seconds: float = 2.0,
    width: int = 1280,
    height: int = 720,
) -> Path:
    """
    Extract a thumbnail frame from mp4_path and write it as JPEG to output_path.

    Runs ffmpeg in a thread pool executor (blocking I/O).
    Returns output_path on success.

    If extraction fails (e.g. very short video where seek_seconds > duration),
    falls back to seek_seconds=0 before giving up entirely.
    """
    loop = asyncio.get_running_loop()

    # First attempt at requested seek time
    try:
        await loop.run_in_executor(
            None, _run_extract, mp4_path, output_path, seek_seconds, width, height
        )
        log.debug("thumbnail_extracted", path=str(output_path), seek=seek_seconds)
        return output_path

    except RuntimeError:
        log.warning(
            "thumbnail_extraction_failed_retrying_at_0s",
            mp4=str(mp4_path),
            seek=seek_seconds,
        )

    # Fallback: seek 0 (always works even for very short clips)
    try:
        await loop.run_in_executor(
            None, _run_extract, mp4_path, output_path, 0.0, width, height
        )
        return output_path

    except RuntimeError as exc:
        log.error(
            "thumbnail_extraction_failed_both_attempts",
            mp4=str(mp4_path),
            error=str(exc),
        )
        # Create a minimal placeholder so we always return a valid path
        _write_placeholder(output_path, width, height)
        return output_path


# ── Internal helpers ──────────────────────────────────────────────────────────

def _run_extract(
    mp4_path: Path,
    output_path: Path,
    seek_seconds: float,
    width: int,
    height: int,
) -> None:
    """Blocking ffmpeg call — runs inside executor."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(seek_seconds),
        "-i", str(mp4_path),
        "-vframes", "1",
        "-vf", (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
        ),
        "-q:v", "2",    # JPEG quality (1=best, 31=worst; 2 is near-lossless)
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg thumbnail extraction failed (code {result.returncode}): "
            f"{result.stderr[-300:]}"
        )


def _write_placeholder(output_path: Path, width: int, height: int) -> None:
    """
    Write a solid black JPEG placeholder when ffmpeg extraction fails entirely.
    Uses Pillow if available; otherwise writes a minimal valid JPEG byte sequence.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image  # type: ignore[import]
        img = Image.new("RGB", (width, height), color=(0, 0, 0))
        img.save(str(output_path), "JPEG", quality=85)
        log.debug("thumbnail_placeholder_written_pillow", path=str(output_path))
    except ImportError:
        # Pillow not yet installed — write the smallest valid JPEG (1×1 black pixel)
        _MINIMAL_BLACK_JPEG = bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
            0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
            0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
            0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
            0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
            0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
            0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
            0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
            0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
            0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
            0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
            0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
            0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD2,
            0x8A, 0x28, 0x03, 0xFF, 0xD9,
        ])
        output_path.write_bytes(_MINIMAL_BLACK_JPEG)
        log.debug("thumbnail_placeholder_written_raw", path=str(output_path))
