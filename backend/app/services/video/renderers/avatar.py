"""
AvatarRenderer — HeyGen talking-head avatar video.

Structure:
  - LLM breaks script into sections (each section = one HeyGen API call)
  - For each section: submit to HeyGen, poll until done, download MP4
  - Section videos concatenated with optional fade transitions

HeyGen dependency: requires VIDEO_HEYGEN_KEY env var (or per-tenant key).
  tenant.config.video.api_keys.heygen   — per-tenant key
  tenant.config.video.heygen_avatar_id  — avatar to use
  tenant.config.video.heygen_voice_id   — voice to use (optional)
  VideoSettings.heygen_avatar_id        — per-job avatar override
  VideoSettings.heygen_voice_id         — per-job voice override

HeyGen limits:
  - Single video max 5 minutes = break long scripts into sections
  - API polling: 10s interval, 30-min timeout (inside HeyGenProvider)

The rendered sections are concatenated via MoviePy.  No TTS is used
because HeyGen generates its own lip-synced audio internally.
"""
from __future__ import annotations

import asyncio
import functools
from pathlib import Path

import structlog

from app.services.video import RenderResult
from app.services.video.base_renderer import BaseVideoRenderer

log = structlog.get_logger(__name__)

# ── Retry configuration for HeyGen / avatar providers ────────────────────────
_MAX_RETRIES     = 3          # total attempts (1 initial + 2 retries)
_RETRY_BASE_SEC  = 5.0        # initial back-off: 5 s → 10 s → 20 s
_RETRY_MAX_SEC   = 60.0       # cap each sleep at 60 seconds
_RETRYABLE_ERRS  = (
    "timeout",
    "rate limit",
    "429",
    "503",
    "502",
    "500",
    "connection",
    "timed out",
)   # substrings in exception message that are worth retrying

_FPS = 30          # HeyGen outputs 30fps
_MAX_SECTION_CHARS = 1500   # ~2 min at average speaking pace


class AvatarRenderer(BaseVideoRenderer):
    """HeyGen avatar video: lip-synced talking head assembled from script sections."""

    async def render(self) -> RenderResult:
        if self.providers.avatar is None:
            raise RuntimeError(
                "AvatarRenderer requires an avatar provider. "
                "Configure HeyGen: set VIDEO_HEYGEN_KEY and video_type=avatar."
            )

        script = self.job.script or self.job.title
        w, h = self._get_resolution()

        # ── Resolve avatar + voice IDs ────────────────────────────────────────
        # Job settings override tenant defaults (already in HeyGenProvider)
        # Template keys take precedence over direct heygen keys
        avatar_id = (
            self.settings.get("heygen_avatar_id") or ""
        )
        voice_id = (
            self.settings.get("heygen_voice_id") or ""
        )

        # ── Resolve template-specific settings ────────────────────────────────
        # avatar_style: "normal" | "closeUp" | "circle"
        avatar_style: str     = str(self.settings.get("avatar_style") or "normal")
        # avatar_position: "left" | "right" | "center"
        avatar_position: str  = str(self.settings.get("avatar_position") or "center")
        # voice_speed: float 0.5–2.0 (1.0 = normal)
        try:
            voice_speed = max(0.5, min(2.0, float(self.settings.get("voice_speed") or 1.0)))
        except (ValueError, TypeError):
            voice_speed = 1.0
        # voice_emotion: string hint passed to HeyGen (happy/neutral/sad/serious etc.)
        voice_emotion: str    = str(self.settings.get("voice_emotion") or "")
        # background_type: "image" | "color" | "video"
        background_type: str  = str(self.settings.get("background_type") or "color")
        background_value: str = str(self.settings.get("background_value") or "")
        # show_captions: bool
        show_captions: bool   = _truthy(self.settings.get("show_captions", False))

        # ── Plan sections ─────────────────────────────────────────────────────
        await self._update_progress(15, "Planning avatar script sections...")
        sections = await self._plan_scenes(
            script,
            extra_context={"max_chars_per_section": _MAX_SECTION_CHARS},
        )
        if not sections:
            sections = [{"id": 1, "script": script, "duration_hint": 60}]

        log.info(
            "avatar_sections_planned",
            job_id=str(self.job.id),
            section_count=len(sections),
        )

        # ── Generate each section via HeyGen ─────────────────────────────────
        section_paths: list[Path] = []
        total_duration = 0.0

        # Detect whether the provider needs TTS pre-synthesis (e.g. SadTalker)
        provider_needs_tts: bool = getattr(
            self.providers.avatar, "requires_pre_tts", False
        )

        for idx, section in enumerate(sections):
            section_script = str(section.get("script", "")).strip()
            if not section_script:
                continue

            await self._update_progress(
                15 + int(55 * idx / len(sections)),
                f"Generating avatar section {idx + 1}/{len(sections)}...",
            )

            section_path = self.tmp_dir / f"section_{idx}.mp4"

            # ── SadTalker (and any future local lip-sync provider) needs ───────
            # pre-synthesised audio.  Synthesise here and pass the file path
            # as voice_id so the provider can read it directly.
            effective_voice_id = voice_id
            if provider_needs_tts:
                tts_audio_path = self.tmp_dir / f"section_{idx}_tts.mp3"
                try:
                    await self._synthesize_tts(
                        section_script, tts_audio_path,
                        voice=voice_id if voice_id else None,
                    )
                    effective_voice_id = str(tts_audio_path)
                    log.info(
                        "avatar_pre_tts_done",
                        idx=idx,
                        path=str(tts_audio_path),
                    )
                except Exception as exc:  # noqa: BLE001
                    log.error(
                        "avatar_pre_tts_failed",
                        idx=idx,
                        error=str(exc),
                    )
                    raise RuntimeError(
                        f"TTS pre-synthesis required by avatar provider but failed "
                        f"on section {idx}: {exc}"
                    ) from exc

            duration = await _create_with_retry_and_fallback(
                renderer=self,
                section_script=section_script,
                section_idx=idx,
                avatar_id=avatar_id,
                voice_id=effective_voice_id,
                avatar_style=avatar_style,
                avatar_position=avatar_position,
                voice_speed=voice_speed,
                voice_emotion=voice_emotion or None,
                background_type=background_type,
                background_value=background_value or None,
                show_captions=show_captions,
                section_path=section_path,
            )
            total_duration += duration
            section_paths.append(section_path)

        if not section_paths:
            raise RuntimeError("Avatar rendering produced no output sections.")

        # ── Concatenate sections in executor ──────────────────────────────────
        await self._update_progress(72, "Concatenating avatar sections...")
        output_path = self.tmp_dir / "raw.mp4"

        if len(section_paths) == 1:
            # Single section: move/rename directly — no MoviePy needed
            import shutil
            shutil.copy2(str(section_paths[0]), str(output_path))
        else:
            fn = functools.partial(
                _concatenate_sections,
                section_paths=section_paths,
                w=w, h=h,
                transition=self._get_transition(),
                tmp_dir=self.tmp_dir,
                output_path=output_path,
                fps=_FPS,
            )
            loop = asyncio.get_running_loop()
            total_duration = await loop.run_in_executor(None, fn)

        await self._update_progress(75, "Avatar render complete.")
        return RenderResult(
            raw_mp4_path=output_path,
            duration_seconds=total_duration,
            metadata={
                "section_count": len(section_paths),
                "avatar_id": avatar_id,
                "voice_id": voice_id,
                "avatar_style": avatar_style,
                "avatar_position": avatar_position,
                "show_captions": show_captions,
            },
        )


# ── Synchronous MoviePy assembly ─────────────────────────────────────────────

def _concatenate_sections(
    *,
    section_paths: list[Path],
    w: int,
    h: int,
    transition: str,
    tmp_dir: Path,
    output_path: Path,
    fps: int,
) -> float:
    """Concatenate HeyGen section MP4s into a single video."""
    from moviepy import VideoFileClip, concatenate_videoclips
    from app.services.video import vfx_compat as vfx

    clips = []
    total_duration = 0.0

    for path in section_paths:
        if not path.exists():
            continue
        try:
            clip = VideoFileClip(str(path))
            # Resize to target if HeyGen returned different dimensions
            if clip.size != (w, h):
                clip = _resize_fill(clip, w, h)
            if transition == "fade":
                clip = clip.with_effects([vfx.FadeIn(0.3), vfx.FadeOut(0.3)])
            clips.append(clip)
            total_duration += clip.duration
        except Exception as exc:  # noqa: BLE001
            log.warning("avatar_section_load_failed", path=str(path), error=str(exc))

    if not clips:
        raise RuntimeError("No valid section clips to concatenate for avatar video.")

    final = concatenate_videoclips(clips, method="compose")

    final.write_videofile(
        str(output_path),
        codec="libx264",
        fps=fps,
        audio_codec="aac",
        temp_audiofile=str(tmp_dir / "_tmp_audio.m4a"),
        remove_temp=True,
        logger=None,
    )
    final.close()
    return total_duration


def _resize_fill(clip, w: int, h: int):
    """Resize clip to fill (w, h), cropping to center if aspect differs."""
    clip_w, clip_h = clip.size
    scale = max(w / clip_w, h / clip_h)
    new_w = int(clip_w * scale)
    new_h = int(clip_h * scale)
    resized = clip.resized((new_w, new_h))
    if new_w == w and new_h == h:
        return resized
    x = (new_w - w) // 2
    y = (new_h - h) // 2
    return resized.cropped(x1=x, y1=y, x2=x + w, y2=y + h)


# ── Retry + fallback helpers ─────────────────────────────────────────────────

def _is_retryable(exc: Exception) -> bool:
    """Return True if the exception looks like a transient API error."""
    msg = str(exc).lower()
    return any(kw in msg for kw in _RETRYABLE_ERRS)


async def _create_with_retry_and_fallback(
    *,
    renderer: "AvatarRenderer",
    section_script: str,
    section_idx: int,
    avatar_id: str,
    voice_id: str,
    avatar_style: str,
    avatar_position: str,
    voice_speed: float,
    voice_emotion: str | None,
    background_type: str,
    background_value: str | None,
    show_captions: bool,
    section_path: Path,
) -> float:
    """
    Try avatar.create_video() up to _MAX_RETRIES times with exponential back-off.

    If all attempts fail:
      - Permanent (non-retryable) error on attempt 1 → re-raise immediately
        so the job is marked FAILED with a meaningful error message.
      - Retryable errors exhausted → fall back to brand-colour placeholder
        (TTS audio + branded still-image video) so the rest of the job
        is not blocked by a single failed section.
    """
    last_exc: Exception | None = None
    last_was_retryable = False

    for attempt in range(_MAX_RETRIES):
        try:
            duration = await renderer.providers.avatar.create_video(
                script=section_script,
                avatar_id=avatar_id,
                voice_id=voice_id,
                language=renderer.language,
                output_path=section_path,
                # Pass through template settings — providers that support them
                # (HeyGen) will use them; others ignore unknown kwargs.
                avatar_style=avatar_style,
                avatar_position=avatar_position,
                voice_speed=voice_speed,
                voice_emotion=voice_emotion,
                background_type=background_type,
                background_value=background_value,
                show_captions=show_captions,
            )
            log.info(
                "avatar_section_done",
                idx=section_idx,
                attempt=attempt + 1,
                duration=round(duration, 1),
            )
            return duration

        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            last_was_retryable = _is_retryable(exc)

            log.warning(
                "avatar_section_attempt_failed",
                idx=section_idx,
                attempt=attempt + 1,
                retryable=last_was_retryable,
                error=str(exc)[:200],
            )

            if not last_was_retryable:
                # Permanent error (bad API key, quota exceeded, invalid avatar
                # ID, etc.) — no point retrying; surface the error immediately.
                raise RuntimeError(
                    f"Avatar provider permanent failure on section {section_idx}: {exc}"
                ) from exc

            if attempt < _MAX_RETRIES - 1:
                sleep_sec = min(
                    _RETRY_MAX_SEC,
                    _RETRY_BASE_SEC * (2 ** attempt),
                )
                log.info(
                    "avatar_retry_sleep",
                    idx=section_idx,
                    attempt=attempt + 1,
                    sleep_sec=sleep_sec,
                )
                await asyncio.sleep(sleep_sec)

    # All retries exhausted — fall back to branded placeholder
    log.error(
        "avatar_all_retries_failed_using_fallback",
        idx=section_idx,
        error=str(last_exc),
    )
    return await _render_placeholder_section(
        renderer=renderer,
        script=section_script,
        section_idx=section_idx,
        output_path=section_path,
    )


async def _render_placeholder_section(
    *,
    renderer: "AvatarRenderer",
    script: str,
    section_idx: int,
    output_path: Path,
) -> float:
    """
    Brand-colour placeholder video: TTS audio + branded still frame.

    Used when the avatar provider fails after all retries.  Keeps the
    overall job alive with a watchable (if visually plain) video rather
    than crashing the entire render pipeline.

    Frame layout:
      - Background: brand primary colour
      - Centred text: "Avatar unavailable" + job title
      - Footer: "Section {n}" counter
    """
    import functools

    w, h = renderer._get_resolution()
    primary, secondary = renderer._get_brand_colors()

    # TTS narration (best-effort — if this also fails, produce silent video)
    audio_path = renderer.tmp_dir / f"fallback_{section_idx}_audio.mp3"
    tts_duration: float = 0.0
    try:
        tts_duration = await renderer._synthesize_tts(script, audio_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("avatar_fallback_tts_failed", idx=section_idx, error=str(exc))
        audio_path = None

    duration = max(5.0, tts_duration)

    loop = asyncio.get_running_loop()
    fn = functools.partial(
        _render_placeholder_video,
        title=renderer.job.title or "Avatar Video",
        section_n=section_idx + 1,
        duration=duration,
        audio_path=audio_path if (audio_path and audio_path.exists()) else None,
        w=w, h=h,
        primary_hex=primary,
        secondary_hex=secondary,
        output_path=output_path,
        tmp_dir=renderer.tmp_dir,
        fps=_FPS,
    )
    await loop.run_in_executor(None, fn)
    return duration


def _render_placeholder_video(
    *,
    title: str,
    section_n: int,
    duration: float,
    audio_path: Path | None,
    w: int,
    h: int,
    primary_hex: str,
    secondary_hex: str,
    output_path: Path,
    tmp_dir: Path,
    fps: int,
) -> None:
    """
    Render a still-image branded placeholder as MP4 with optional TTS audio.
    """
    import numpy as np
    from PIL import Image as PILImage, ImageDraw, ImageFont
    from moviepy import VideoClip
    from moviepy import AudioFileClip

    # ── Draw branded still frame ──────────────────────────────────────────────
    def _hex_to_rgb_local(hex_c: str) -> tuple[int, int, int]:
        h = hex_c.lstrip("#")
        if len(h) != 6:
            return (37, 99, 235)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    bg_rgb   = _hex_to_rgb_local(primary_hex)
    text_rgb = _hex_to_rgb_local(secondary_hex)

    img  = PILImage.new("RGB", (w, h), color=bg_rgb)
    draw = ImageDraw.Draw(img)

    # Title font
    title_size = max(40, h // 10)
    sub_size   = max(24, h // 20)
    _font_paths = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    ]
    t_font = s_font = None
    for fp in _font_paths:
        if Path(fp).exists():
            try:
                t_font = ImageFont.truetype(fp, title_size)
                s_font = ImageFont.truetype(fp, sub_size)
                break
            except Exception:  # noqa: BLE001
                continue
    if t_font is None:
        t_font = s_font = ImageFont.load_default()

    # Warning banner
    warn_text = "⚠ Avatar service unavailable"
    warn_size = max(28, h // 15)
    try:
        w_font = ImageFont.truetype(_font_paths[0], warn_size)
    except Exception:  # noqa: BLE001
        w_font = t_font

    # Darken bg_rgb for contrast bar
    dark_bg = tuple(max(0, int(c * 0.5)) for c in bg_rgb)
    draw.rectangle([(0, h // 4), (w, 3 * h // 4)], fill=dark_bg)

    # Warning text
    try:
        tw = draw.textlength(warn_text, font=w_font)
    except Exception:  # noqa: BLE001
        tw = len(warn_text) * warn_size // 2
    draw.text(((w - tw) // 2, h // 4 + 20), warn_text, font=w_font, fill=(255, 200, 50))

    # Title
    t_trunc = title[:60]
    try:
        tw = draw.textlength(t_trunc, font=t_font)
    except Exception:  # noqa: BLE001
        tw = len(t_trunc) * title_size // 2
    draw.text(((w - tw) // 2, h // 2 - title_size), t_trunc, font=t_font, fill=text_rgb)

    # Section counter
    sub_text = f"Section {section_n}"
    try:
        sw = draw.textlength(sub_text, font=s_font)
    except Exception:  # noqa: BLE001
        sw = len(sub_text) * sub_size // 2
    draw.text(((w - sw) // 2, h // 2 + 10), sub_text, font=s_font, fill=text_rgb)

    frame_arr = np.array(img, dtype=np.uint8)

    # ── Build VideoClip from still frame ─────────────────────────────────────
    def make_frame(_t: float) -> np.ndarray:
        return frame_arr

    clip = VideoClip(make_frame, duration=duration)
    clip = clip.with_fps(fps)

    if audio_path and audio_path.exists():
        try:
            narration = AudioFileClip(str(audio_path))
            if narration.duration > duration:
                narration = narration.subclipped(0, duration)
            clip = clip.with_audio(narration)
        except Exception as exc:  # noqa: BLE001
            log.warning("avatar_fallback_audio_attach_failed", error=str(exc))

    clip.write_videofile(
        str(output_path),
        codec="libx264",
        fps=fps,
        audio_codec="aac",
        temp_audiofile=str(tmp_dir / f"_fb_{section_n}_audio.m4a"),
        remove_temp=True,
        logger=None,
    )
    clip.close()


def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v != 0
    return str(v).lower() not in ("false", "0", "no", "off", "")
