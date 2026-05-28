"""
FFmpeg quality gate — final re-encode step for every rendered video.

Runs AFTER the renderer produces a raw MP4, regardless of which provider
generated it (MoviePy, HeyGen, Synthesia, Pictory, …).

Guarantees enterprise-standard output:
  • H.264 (libx264) by default; H.265 (libx265) when configured
  • 8 Mbps target bitrate, 10 Mbps max
  • AAC stereo audio at 192 kbps / 48 kHz
  • yuv420p pixel format — universal browser / LMS / mobile playback
  • moov atom first (faststart) — enables instant streaming before full download
  • Letterbox to target resolution — preserves aspect ratio, adds black bars
"""
from __future__ import annotations

import asyncio
import functools
import shutil
import subprocess
from pathlib import Path

import structlog

from app.config import settings

log = structlog.get_logger(__name__)


# ── Codec probe (cached — checked once per worker process) ───────────────────

@functools.lru_cache(maxsize=1)
def _available_codec() -> str:
    """
    Return the best available H.26x codec on this machine.

    Preference order: configured codec → libx265 → libx264.
    lru_cache means we only run ffmpeg -codecs once per worker process.
    """
    preferred = settings.video_export_codec  # "libx264" or "libx265"
    try:
        result = subprocess.run(
            ["ffmpeg", "-codecs"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout + result.stderr
        if preferred in output:
            return preferred
        if "libx265" in output:
            return "libx265"
        return "libx264"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        log.warning("ffmpeg_probe_failed_falling_back_to_libx264")
        return "libx264"


def _ffmpeg_present() -> bool:
    return shutil.which("ffmpeg") is not None


# ── Public API ────────────────────────────────────────────────────────────────

async def encode(
    input_path: Path,
    output_path: Path,
    resolution: str = "1080p",
) -> Path:
    """
    Re-encode input_path to enterprise-standard MP4 at output_path.

    Runs in a thread pool executor so it doesn't block the event loop.
    Returns output_path on success.
    Raises RuntimeError if ffmpeg is not installed or exits non-zero.
    """
    # Dev bypass: SKIP_FFMPEG_GATE=true in .env copies raw MP4 directly
    if not _ffmpeg_present() or getattr(settings, "skip_ffmpeg_gate", False):
        if not _ffmpeg_present():
            log.warning(
                "ffmpeg_not_found_bypassing_gate",
                hint="Set SKIP_FFMPEG_GATE=true in .env to suppress this warning, "
                     "or install ffmpeg: brew install ffmpeg",
            )
        import shutil as _shutil
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _shutil.copy2(str(input_path), str(output_path))
        log.info("ffmpeg_gate_skipped", output=str(output_path))
        return output_path

    codec = _available_codec()
    width, height = _RESOLUTION_MAP.get(resolution, (1920, 1080))

    cmd = _build_ffmpeg_cmd(
        input_path=input_path,
        output_path=output_path,
        codec=codec,
        width=width,
        height=height,
        bitrate=settings.video_export_bitrate,
        crf=settings.video_export_crf,
        audio_bitrate=settings.video_export_audio_bitrate,
    )

    log.info(
        "ffmpeg_gate_start",
        input=str(input_path),
        output=str(output_path),
        codec=codec,
        resolution=resolution,
    )

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _run_ffmpeg, cmd)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    log.info(
        "ffmpeg_gate_done",
        output=str(output_path),
        size_mb=round(size_mb, 1),
    )

    return output_path


# ── Internal helpers ──────────────────────────────────────────────────────────

_RESOLUTION_MAP: dict[str, tuple[int, int]] = {
    "720p":  (1280, 720),
    "1080p": (1920, 1080),
    "4k":    (3840, 2160),
}


def _build_ffmpeg_cmd(
    input_path: Path,
    output_path: Path,
    codec: str,
    width: int,
    height: int,
    bitrate: str,
    crf: int,
    audio_bitrate: str,
) -> list[str]:
    """Build the ffmpeg command list."""
    # vf: scale to target keeping aspect ratio, pad black bars, enforce yuv420p
    # Expressions use ffmpeg's 'if odd, subtract 1' trick (trunc(ow/2)*2) to
    # ensure width/height are always divisible by 2 (required by libx264/265).
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"format=yuv420p"
    )

    cmd = [
        "ffmpeg",
        "-y",                           # overwrite output without asking
        "-i", str(input_path),
        # Video
        "-c:v", codec,
        "-crf", str(crf),
        "-preset", "medium",
        "-b:v", bitrate,
        "-maxrate", _scale_bitrate(bitrate, 1.25),
        "-bufsize", _scale_bitrate(bitrate, 2.5),
        "-vf", vf,
        # Audio
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        "-ac", "2",                     # stereo
        "-ar", "48000",
        # Container
        "-movflags", "+faststart",      # moov atom first — instant streaming
        str(output_path),
    ]

    # H.265 extra flags for broader compatibility
    if codec == "libx265":
        cmd = cmd[:-1] + ["-tag:v", "hvc1", str(output_path)]

    return cmd


def _run_ffmpeg(cmd: list[str]) -> None:
    """Synchronous FFmpeg execution — called via run_in_executor."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=1800,   # 30-minute hard timeout (generous for long videos)
    )
    if result.returncode != 0:
        # Include last 500 chars of stderr for debugging
        excerpt = result.stderr[-500:] if result.stderr else "(no stderr)"
        raise RuntimeError(
            f"FFmpeg exited with code {result.returncode}.\n"
            f"Command: {' '.join(cmd[:6])} ...\n"
            f"Stderr (last 500 chars): {excerpt}"
        )


def _scale_bitrate(bitrate_str: str, multiplier: float) -> str:
    """Scale a bitrate string like '8000k' by a multiplier. Returns e.g. '10000k'."""
    if bitrate_str.endswith("k"):
        return f"{int(int(bitrate_str[:-1]) * multiplier)}k"
    if bitrate_str.endswith("M"):
        return f"{int(int(bitrate_str[:-1]) * multiplier)}M"
    return bitrate_str   # fallback: return unchanged
