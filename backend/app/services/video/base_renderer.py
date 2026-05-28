"""
BaseVideoRenderer — abstract base class for all 10 video type renderers.

Every renderer (kinetic, slideshow, stockfootage, avatar, …) extends this class
and implements render().  All shared utilities (_synthesize_tts, _download_asset,
_plan_scenes, _update_progress) live here so renderers stay focused on their
specific rendering logic.

Constructor receives:
  job             — VideoJob ORM instance (read-only inside render())
  providers       — ProviderBundle (TTS, stock, avatar, etc.)
  tmp_dir         — exclusive temp directory for this job (cleaned up by Celery task)
  session_factory — async_sessionmaker for writing progress updates to DB

render() contract:
  - Must call _update_progress() at least once during execution
  - Must return a RenderResult with a valid raw_mp4_path (pre-FFmpeg gate)
  - Must NOT call ffmpeg_gate or storage — the Celery task handles those
  - May raise any exception; the Celery task catches all and sets job=FAILED

Settings key convention
-----------------------
The Moodle plugin sends two layers of settings that end up merged in
VideoJob.settings (JSONB):

  1. Template settings (set in local_edzaxisvideo_templates.settings JSON)
     Keys: primarycolor, accentcolor, bgmvolume, voicevolume, aspectratio,
           fontfamily, overlayopacity, transition, transitionduration,
           defaultduration, maxduration + type-specific keys per video type.

  2. Tenant/brand config injected by the platform
     Keys: brand_color_primary, brand_color_secondary, music_volume, resolution

Helper methods below check the template key FIRST, then fall back to the
platform key, so template settings always take precedence while remaining
backward-compatible with jobs that do not have a template attached.
"""
from __future__ import annotations

import copy

import asyncio
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from app.services.video import ProviderBundle, RenderResult

if TYPE_CHECKING:
    import uuid
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.models.video_job import VideoJob

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Google Fonts — curated download map for fonts commonly used in templates.
# Keys are the exact fontfamily values sent from Moodle templates.
# Values map to direct GitHub raw CDN URLs for TTF files.
# Extend this dict as new templates are added.
# ---------------------------------------------------------------------------
_GOOGLE_FONT_URLS: dict[str, dict[str, str]] = {
    "Poppins": {
        "ttf_regular": "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf",
        "ttf_bold":    "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf",
    },
    "Oswald": {
        "ttf_regular": "https://github.com/google/fonts/raw/main/ofl/oswald/static/Oswald-Regular.ttf",
        "ttf_bold":    "https://github.com/google/fonts/raw/main/ofl/oswald/static/Oswald-Bold.ttf",
    },
    "PatrickHand": {
        "ttf_regular": "https://github.com/google/fonts/raw/main/ofl/patrickhand/PatrickHand-Regular.ttf",
        "ttf_bold":    "https://github.com/google/fonts/raw/main/ofl/patrickhand/PatrickHand-Regular.ttf",
    },
    "Patrick Hand": {
        "ttf_regular": "https://github.com/google/fonts/raw/main/ofl/patrickhand/PatrickHand-Regular.ttf",
        "ttf_bold":    "https://github.com/google/fonts/raw/main/ofl/patrickhand/PatrickHand-Regular.ttf",
    },
    "Montserrat": {
        "ttf_regular": "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-Regular.ttf",
        "ttf_bold":    "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-Bold.ttf",
    },
    "Roboto": {
        "ttf_regular": "https://github.com/google/fonts/raw/main/apache/roboto/static/Roboto-Regular.ttf",
        "ttf_bold":    "https://github.com/google/fonts/raw/main/apache/roboto/static/Roboto-Bold.ttf",
    },
    "Lato": {
        "ttf_regular": "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Regular.ttf",
        "ttf_bold":    "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Bold.ttf",
    },
    "Open Sans": {
        "ttf_regular": "https://github.com/google/fonts/raw/main/ofl/opensans/static/OpenSans-Regular.ttf",
        "ttf_bold":    "https://github.com/google/fonts/raw/main/ofl/opensans/static/OpenSans-Bold.ttf",
    },
    "Nunito": {
        "ttf_regular": "https://github.com/google/fonts/raw/main/ofl/nunito/static/Nunito-Regular.ttf",
        "ttf_bold":    "https://github.com/google/fonts/raw/main/ofl/nunito/static/Nunito-Bold.ttf",
    },
    "Raleway": {
        "ttf_regular": "https://github.com/google/fonts/raw/main/ofl/raleway/static/Raleway-Regular.ttf",
        "ttf_bold":    "https://github.com/google/fonts/raw/main/ofl/raleway/static/Raleway-Bold.ttf",
    },
    "Playfair Display": {
        "ttf_regular": "https://github.com/google/fonts/raw/main/ofl/playfairdisplay/static/PlayfairDisplay-Regular.ttf",
        "ttf_bold":    "https://github.com/google/fonts/raw/main/ofl/playfairdisplay/static/PlayfairDisplay-Bold.ttf",
    },
    "Merriweather": {
        "ttf_regular": "https://github.com/google/fonts/raw/main/ofl/merriweather/Merriweather-Regular.ttf",
        "ttf_bold":    "https://github.com/google/fonts/raw/main/ofl/merriweather/Merriweather-Bold.ttf",
    },
    "Caveat": {
        "ttf_regular": "https://github.com/google/fonts/raw/main/ofl/caveat/static/Caveat-Regular.ttf",
        "ttf_bold":    "https://github.com/google/fonts/raw/main/ofl/caveat/static/Caveat-Bold.ttf",
    },
}

# Local system font fallback search paths (in preference order)
_SYSTEM_FONTS_BOLD: list[str] = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
_SYSTEM_FONTS_REGULAR: list[str] = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
]

# Cache directory for downloaded Google Fonts TTFs
_FONT_CACHE_DIR = Path.home() / ".axis_fonts"


class BaseVideoRenderer(ABC):
    """Abstract base for all video renderers."""

    def __init__(
        self,
        job: "VideoJob",
        providers: ProviderBundle,
        tmp_dir: Path,
        session_factory: "async_sessionmaker",
    ) -> None:
        self.job = job
        self.providers = providers
        self.tmp_dir = tmp_dir
        self._session_factory = session_factory

        # Convenience shorthand for settings dict
        self.settings: dict = copy.deepcopy(job.settings or {})
        # Resolved assets sub-dict (may be empty)
        self.assets: dict = self.settings.get("_resolved_assets", {})
        # Language from job (or settings fallback)
        self.language: str = job.language or self.settings.get("language", "en")

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    async def render(self) -> RenderResult:
        """
        Execute the full render pipeline for this video type.

        Must call self._update_progress(pct, msg) at key steps.
        Returns RenderResult(raw_mp4_path, duration_seconds).
        The raw MP4 is the assembled video BEFORE the FFmpeg quality gate.
        """

    # ── Shared utilities ──────────────────────────────────────────────────────

    async def _update_progress(self, pct: int, msg: str) -> None:
        """
        Write progress to the VideoJob row.

        Opens a short-lived DB session — safe to call from any async context.
        Errors are logged but never re-raised (don't fail renders over progress).
        """
        from sqlalchemy import select
        from app.models.video_job import VideoJob

        try:
            async with self._session_factory() as db:
                result = await db.execute(
                    select(VideoJob).where(VideoJob.id == self.job.id)
                )
                row = result.scalar_one_or_none()
                if row:
                    row.progress = max(0, min(100, pct))
                    row.progress_msg = msg[:255] if msg else None
                    await db.commit()
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "progress_update_failed",
                job_id=str(self.job.id),
                pct=pct,
                error=str(exc),
            )

    async def _synthesize_tts(
        self,
        text: str,
        output_path: Path,
        voice: str | None = None,
    ) -> float:
        """
        Synthesize text to audio using the tenant's TTS provider.

        voice overrides the settings.voice when provided.
        Returns audio duration in seconds.
        """
        resolved_voice = (
            voice
            or self.settings.get("voice")
            or None   # TTSProvider will apply its own language default
        )
        duration = await self.providers.tts.synthesize(
            text=text,
            voice=resolved_voice or "",
            language=self.language,
            output_path=output_path,
        )
        log.debug(
            "tts_synthesized",
            chars=len(text),
            duration_sec=round(duration, 1),
            voice=resolved_voice,
        )
        return duration

    async def _download_asset(
        self,
        url: str,
        dest: Path,
        timeout_sec: float = 60.0,
    ) -> Path:
        """
        Download a remote asset (Moodle pluginfile, Pexels clip, etc.) to dest.

        Returns dest.  Raises httpx.HTTPError on network failures so the
        Celery task can retry.
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with dest.open("wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=65_536):
                        f.write(chunk)

        log.debug("asset_downloaded", url=url[:80], dest=str(dest), size=dest.stat().st_size)
        return dest

    async def _plan_scenes(
        self,
        script: str,
        extra_context: dict | None = None,
    ) -> list[dict]:
        """
        Call LLM planner to break the script into structured scenes.

        Returns a list of scene dicts whose schema is video-type-specific.
        Concrete renderers should pass extra_context with schema hints.
        """
        from app.services.video.llm_planner import plan_scenes
        return await plan_scenes(
            script=script,
            video_type=self.job.video_type,
            settings_dict=self.settings,
            extra_context=extra_context or {},
            session_factory=self._session_factory,
            tenant_id=self.job.tenant_id,
        )

    # ── Settings helpers — template-key-aware ────────────────────────────────

    def _get_brand_colors(self) -> tuple[str, str]:
        """
        Return (primary_hex, secondary_hex) brand colors.

        Checks template keys (primarycolor / accentcolor) first, then falls back
        to tenant platform keys (brand_color_primary / brand_color_secondary).
        Validates hex format; returns safe defaults for missing/invalid values.
        """
        primary = (
            self.settings.get("primarycolor")
            or self.settings.get("brand_color_primary")
            or "#2563EB"
        )
        secondary = (
            self.settings.get("accentcolor")
            or self.settings.get("brand_color_secondary")
            or "#FFFFFF"
        )
        return _safe_hex(str(primary), "#2563EB"), _safe_hex(str(secondary), "#FFFFFF")

    def _get_transition(self) -> str:
        """Return the configured transition style (default: fade)."""
        valid = {"fade", "wipe", "zoom", "crossfade", "none"}
        t = str(self.settings.get("transition") or "fade").lower()
        return t if t in valid else "fade"

    def _get_transition_duration(self) -> float:
        """
        Return the transition duration in seconds.

        Template key: transitionduration (float, seconds). Clamped to [0.1, 3.0].
        """
        try:
            v = float(self.settings.get("transitionduration") or 0.4)
        except (ValueError, TypeError):
            v = 0.4
        return max(0.1, min(3.0, v))

    def _get_music_volume(self) -> float:
        """
        Return background music volume (0.0–1.0).

        Template key: bgmvolume (float 0-1 or int 0-100).
        Platform key fallback: music_volume.
        """
        raw = self.settings.get("bgmvolume") or self.settings.get("music_volume") or 0.3
        try:
            v = float(raw)
        except (ValueError, TypeError):
            return 0.3
        # Some templates may store as 0-100 range — normalise
        if v > 1.0:
            v = v / 100.0
        return max(0.0, min(1.0, v))

    def _get_voice_volume(self) -> float:
        """
        Return voice/narration volume (0.0–1.0).

        Template key: voicevolume (float 0-1 or int 0-100). Defaults to 1.0 (full).
        """
        raw = self.settings.get("voicevolume") or 1.0
        try:
            v = float(raw)
        except (ValueError, TypeError):
            return 1.0
        if v > 1.0:
            v = v / 100.0
        return max(0.0, min(1.0, v))

    def _get_overlay_opacity(self) -> float:
        """
        Return the caption / text-overlay background opacity (0.0–1.0).

        Template key: overlayopacity (float 0-1 or int 0-100). Default: 0.55.
        """
        raw = self.settings.get("overlayopacity") or 0.55
        try:
            v = float(raw)
        except (ValueError, TypeError):
            return 0.55
        if v > 1.0:
            v = v / 100.0
        return max(0.0, min(1.0, v))

    def _get_resolution(self) -> tuple[int, int]:
        """
        Return (width, height) in pixels, honouring both aspectratio and quality.

        Template key: aspectratio ("16:9", "9:16", "1:1", "4:3", "3:4").
        Platform key:  resolution ("720p", "1080p", "4k") — sets base height.

        The base height is derived from resolution; width is computed from the ratio.
        Both dimensions are rounded to even numbers (H.264 requirement).

        Examples:
          aspectratio=16:9, resolution=1080p  →  (1920, 1080)
          aspectratio=9:16, resolution=1080p  →  (608,  1080)  ← portrait
          aspectratio=1:1,  resolution=720p   →  (720,  720)
          aspectratio=4:3,  resolution=1080p  →  (1440, 1080)
        """
        aspect  = str(self.settings.get("aspectratio") or self.settings.get("aspect_ratio") or "16:9").strip()
        quality = str(self.settings.get("resolution")  or "1080p").strip()

        _quality_base_h = {"720p": 720, "1080p": 1080, "4k": 2160}
        base_h = _quality_base_h.get(quality, 1080)

        ratio_w, ratio_h = _parse_aspect_ratio(aspect)
        h = base_h
        w = _even(round(h * ratio_w / ratio_h))
        return (w, h)

    def _get_font_path(self, bold: bool = True) -> Path | None:
        """
        Return a Path to the best available TTF for the configured fontfamily.

        Resolution order:
          1. Template fontfamily (e.g. "Poppins", "Oswald") →
             a. Check ~/.axis_fonts/ cache first (avoids repeat downloads)
             b. Download from Google Fonts CDN into cache
          2. System font fallback (bold preferred if bold=True)
          3. Return None → caller should use PIL ImageFont.load_default()

        This method is SYNCHRONOUS — invoke from a thread executor if calling
        from an async context and the font isn't yet cached.
        """
        font_name: str = str(self.settings.get("fontfamily") or "").strip()

        if font_name and font_name in _GOOGLE_FONT_URLS:
            cached = _get_cached_font(font_name, bold=bold)
            if cached:
                return cached
            urls = _GOOGLE_FONT_URLS[font_name]
            variant = "ttf_bold" if bold else "ttf_regular"
            fallback_variant = "ttf_regular" if bold else "ttf_bold"
            url = urls.get(variant) or urls.get(fallback_variant)
            if url:
                downloaded = _download_font_sync(font_name, url, bold=bold)
                if downloaded:
                    return downloaded

        # System font fallback
        search_lists = (_SYSTEM_FONTS_BOLD if bold else _SYSTEM_FONTS_REGULAR) + _SYSTEM_FONTS_REGULAR
        for path_str in search_lists:
            p = Path(path_str)
            if p.exists():
                return p

        return None

    def _get_default_duration(self) -> float:
        """Return the template's defaultduration in seconds (min 5). Default: 60."""
        try:
            return max(5.0, float(self.settings.get("defaultduration") or 60.0))
        except (ValueError, TypeError):
            return 60.0

    def _get_max_duration(self) -> float:
        """Return the template's maxduration in seconds (min 10). Default: 600."""
        try:
            return max(10.0, float(self.settings.get("maxduration") or 600.0))
        except (ValueError, TypeError):
            return 600.0


# ── Module-level helpers (pure functions, no renderer state) ─────────────────

def _safe_hex(value: str, default: str) -> str:
    """Return value if it looks like a valid CSS hex colour, else default."""
    if not value:
        return default
    s = value.strip()
    if not s.startswith("#"):
        s = f"#{s}"
    if re.fullmatch(r"#[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?", s):
        # Expand 3-char shorthand to 6-char
        if len(s) == 4:
            s = "#" + "".join(c * 2 for c in s[1:])
        return s.upper()
    return default


def _parse_aspect_ratio(aspect: str) -> tuple[int, int]:
    """
    Parse an aspect ratio string like '16:9' into (width_parts, height_parts).
    Returns (16, 9) as a safe default for unrecognised input.
    """
    _NAMED: dict[str, tuple[int, int]] = {
        "16:9": (16, 9),
        "9:16": (9, 16),
        "1:1":  (1, 1),
        "4:3":  (4, 3),
        "3:4":  (3, 4),
        "21:9": (21, 9),
    }
    normalised = aspect.strip()
    if normalised in _NAMED:
        return _NAMED[normalised]
    parts = normalised.split(":")
    if len(parts) == 2:
        try:
            return (int(parts[0]), int(parts[1]))
        except ValueError:
            pass
    log.warning("unknown_aspect_ratio", aspect=aspect, fallback="16:9")
    return (16, 9)


def _even(n: int) -> int:
    """Round n up to the nearest even integer (H.264 dimension requirement)."""
    return n if n % 2 == 0 else n + 1


def _get_cached_font(font_name: str, bold: bool) -> Path | None:
    """Return cached TTF path if it already exists in _FONT_CACHE_DIR."""
    suffix = "Bold" if bold else "Regular"
    safe_name = font_name.replace(" ", "")
    cache_path = _FONT_CACHE_DIR / f"{safe_name}-{suffix}.ttf"
    if cache_path.exists() and cache_path.stat().st_size > 1000:
        return cache_path
    return None


def _download_font_sync(font_name: str, url: str, bold: bool) -> Path | None:
    """
    Synchronously download a font TTF from url into _FONT_CACHE_DIR.

    Returns the Path on success, None on any failure.
    Callers must treat None as "fall back to system font" — never raise.
    """
    import urllib.request

    suffix = "Bold" if bold else "Regular"
    safe_name = font_name.replace(" ", "")
    try:
        _FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        dest = _FONT_CACHE_DIR / f"{safe_name}-{suffix}.ttf"
        if dest.exists() and dest.stat().st_size > 1000:
            return dest  # race-condition guard

        log.info("downloading_google_font", font=font_name, url=url[:80])
        req = urllib.request.Request(url, headers={"User-Agent": "axis-ai/1.0"})
        with urllib.request.urlopen(req, timeout=15) as response:  # noqa: S310
            data = response.read()
        if len(data) < 1000:
            raise ValueError(f"Font download suspiciously small: {len(data)} bytes")
        dest.write_bytes(data)
        log.info("google_font_cached", font=font_name, path=str(dest))
        return dest
    except Exception as exc:  # noqa: BLE001
        log.warning("google_font_download_failed", font=font_name, error=str(exc))
        return None
