"""
MotionRenderer — brand-styled motion graphics slides.

Structure:
  - LLM breaks script into slides (title, bullets, narration, bg_color_hint, accent)
  - Each slide: Pillow brand gradient background + title + bullet text + accent bar
  - TTS narration per slide
  - Optional logo watermark from _resolved_assets.logo_url
  - Slide transitions (fade) + optional background music

Template settings consumed
--------------------------
  showlogo         — bool: show logo watermark (default true)
  showlowerthird   — bool: render lower-third name bar at bottom (default false)
  motionstyle      — "minimal" | "bold" | "gradient" | "corporate" (default gradient)
  primarycolor     — background base colour
  accentcolor      — text / accent colour
  fontfamily       — TTF font name (downloaded via _get_font_path)
  aspectratio      — "16:9" | "9:16" | "1:1" | "4:3"
  resolution       — "720p" | "1080p" | "4k"
  bgmvolume        — background music volume
  voicevolume      — narration voice volume
  transition       — "fade" | "wipe" etc.
  transitionduration — seconds
  overlayopacity   — lower-third bar opacity
"""
from __future__ import annotations

import asyncio
import functools
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from app.services.video import RenderResult
from app.services.video.base_renderer import BaseVideoRenderer

log = structlog.get_logger(__name__)

_FPS = 24
_MIN_SLIDE_DURATION = 4.0

# motionstyle → gradient intensity factor (how much the BG darkens toward bottom)
_STYLE_GRADIENT: dict[str, float] = {
    "minimal":   0.10,   # very slight gradient
    "bold":      0.50,   # strong contrast
    "gradient":  0.35,   # standard (default)
    "corporate": 0.20,   # subtle, professional
}


@dataclass
class _SlideData:
    narration_audio: Path | None
    image_path: Path
    duration: float
    title: str
    bullets: list[str] = field(default_factory=list)


class MotionRenderer(BaseVideoRenderer):
    """Brand-styled motion graphics with gradient backgrounds and text."""

    async def render(self) -> RenderResult:
        script = self.job.script or self.job.title
        w, h = self._get_resolution()
        primary, secondary = self._get_brand_colors()

        # ── Resolve template-specific settings ────────────────────────────────
        show_logo: bool       = _truthy(self.settings.get("showlogo",       True))
        show_lower_third: bool = _truthy(self.settings.get("showlowerthird", False))
        motion_style: str     = str(self.settings.get("motionstyle") or "gradient").lower()
        gradient_factor: float = _STYLE_GRADIENT.get(motion_style, 0.35)

        # Font
        loop = asyncio.get_running_loop()
        font_path: Path | None = await loop.run_in_executor(
            None, self._get_font_path, True
        )

        transition_dur = self._get_transition_duration()
        music_volume   = self._get_music_volume()
        voice_volume   = self._get_voice_volume()
        overlay_opacity = self._get_overlay_opacity()

        # ── Plan slides ───────────────────────────────────────────────────────
        await self._update_progress(20, "Planning motion graphic slides...")
        slides = await self._plan_scenes(script)
        if not slides:
            slides = [{
                "title": self.job.title,
                "bullets": [script],
                "narration": script,
                "duration_seconds": 10,
            }]

        # ── Optional logo download ────────────────────────────────────────────
        logo_path: Path | None = None
        if show_logo:
            logo_url = self.assets.get("logo_url")
            if logo_url:
                try:
                    logo_path = self.tmp_dir / "logo.png"
                    await self._download_asset(logo_url, logo_path)
                    if not logo_path.exists():
                        logo_path = None
                except Exception as exc:  # noqa: BLE001
                    log.warning("motion_logo_download_failed", error=str(exc))

        # ── Build each slide ──────────────────────────────────────────────────
        await self._update_progress(30, f"Rendering {len(slides)} slides...")
        slide_data: list[_SlideData] = []

        for idx, slide in enumerate(slides):
            title   = str(slide.get("title", ""))
            bullets = slide.get("bullets", slide.get("body", []))
            if isinstance(bullets, str):
                bullets = [b.strip() for b in bullets.split("\n") if b.strip()]
            narration = str(slide.get("narration", title))

            # TTS
            audio_path = self.tmp_dir / f"slide_{idx}_audio.mp3"
            try:
                tts_dur  = await self._synthesize_tts(narration, audio_path)
                duration = max(_MIN_SLIDE_DURATION, tts_dur)
            except Exception as exc:  # noqa: BLE001
                log.warning("motion_tts_failed", slide=idx, error=str(exc))
                audio_path = None
                duration   = float(slide.get("duration_seconds", 10))

            # Render slide image (blocking → executor)
            image_path = self.tmp_dir / f"slide_{idx}.png"
            await loop.run_in_executor(
                None,
                _render_slide_image,
                title,
                bullets if isinstance(bullets, list) else [],
                w, h,
                image_path,
                _hex_to_rgb(primary),
                _hex_to_rgb(secondary),
                logo_path,
                idx,
                len(slides),
                font_path,
                gradient_factor,
                show_lower_third,
                overlay_opacity,
            )

            slide_data.append(_SlideData(
                narration_audio=audio_path if (audio_path and audio_path.exists()) else None,
                image_path=image_path,
                duration=duration,
                title=title,
                bullets=bullets if isinstance(bullets, list) else [],
            ))

            pct = 30 + int(40 * (idx + 1) / len(slides))
            await self._update_progress(pct, f"Slide {idx + 1}/{len(slides)} ready")

        # ── Optional background music ─────────────────────────────────────────
        music_path: Path | None = None
        music_url = self.assets.get("music_url")
        if music_url:
            try:
                music_path = self.tmp_dir / "music.mp3"
                await self._download_asset(music_url, music_path)
            except Exception as exc:  # noqa: BLE001
                log.warning("motion_music_failed", error=str(exc))

        # ── Assemble ──────────────────────────────────────────────────────────
        await self._update_progress(72, "Assembling motion graphics video...")
        output_path = self.tmp_dir / "raw.mp4"

        fn = functools.partial(
            _assemble_motion,
            slide_data=slide_data,
            music_path=music_path,
            music_volume=music_volume,
            voice_volume=voice_volume,
            w=w, h=h,
            bg_rgb=_hex_to_rgb(primary),
            transition=self._get_transition(),
            transition_dur=transition_dur,
            tmp_dir=self.tmp_dir,
            output_path=output_path,
            fps=_FPS,
        )
        total_duration = await loop.run_in_executor(None, fn)

        await self._update_progress(75, "Motion graphics render complete.")
        return RenderResult(
            raw_mp4_path=output_path,
            duration_seconds=total_duration,
            metadata={
                "slide_count": len(slides),
                "motionstyle": motion_style,
                "showlogo": show_logo,
                "showlowerthird": show_lower_third,
            },
        )


# ── Synchronous image rendering ───────────────────────────────────────────────

def _render_slide_image(
    title: str,
    bullets: list[str],
    w: int,
    h: int,
    output_path: Path,
    primary_rgb: tuple[int, int, int],
    secondary_rgb: tuple[int, int, int],
    logo_path: Path | None,
    slide_index: int,
    total_slides: int,
    font_path: Path | None,
    gradient_factor: float,
    show_lower_third: bool,
    overlay_opacity: float,
) -> None:
    """Render one branded motion-graphic slide as PNG."""
    from PIL import Image as PILImage, ImageDraw

    img  = PILImage.new("RGB", (w, h), color=primary_rgb)
    draw = ImageDraw.Draw(img)

    # Background gradient
    dark = tuple(max(0, int(c * (1.0 - gradient_factor))) for c in primary_rgb)
    for y in range(h):
        t = y / h
        row_color = tuple(int(primary_rgb[i] * (1 - t) + dark[i] * t) for i in range(3))
        draw.line([(0, y), (w, y)], fill=row_color)  # type: ignore[arg-type]

    pad = int(w * 0.07)

    # Left accent bar
    bar_w = max(8, w // 60)
    draw.rectangle(
        [(pad // 2, pad // 2), (pad // 2 + bar_w, h - pad // 2)],
        fill=secondary_rgb,
    )

    title_size  = max(40, h // 10)
    bullet_size = max(24, h // 22)
    title_font  = _load_font(title_size, font_path)
    bullet_font = _load_font(bullet_size, font_path)

    text_x = pad + bar_w + 16
    y_cursor = int(h * 0.12)

    if title:
        draw.text((text_x, y_cursor), title[:80], font=title_font, fill=secondary_rgb)
        try:
            bbox = draw.textbbox((text_x, y_cursor), title[:80], font=title_font)
            y_cursor = bbox[3] + int(h * 0.04)
        except AttributeError:
            y_cursor += title_size + int(h * 0.04)
        draw.line([(text_x, y_cursor), (w - pad, y_cursor)],
                  fill=secondary_rgb, width=2)
        y_cursor += int(h * 0.03)

    dim = tuple(max(0, int(c * 0.85)) for c in secondary_rgb)
    bottom_limit = h - int(h * 0.15) if show_lower_third else h - int(h * 0.10)

    for bullet in bullets[:8]:
        if y_cursor + bullet_size * 2 > bottom_limit:
            break
        draw.text((text_x - 20, y_cursor), "•", font=bullet_font, fill=secondary_rgb)
        _draw_wrapped_text(
            draw, bullet[:120], bullet_font, text_x,
            y_cursor, w - text_x - pad,
            int(bullet_size * 1.6), dim,  # type: ignore[arg-type]
            max_y=bottom_limit,
        )
        try:
            bbox = draw.textbbox((text_x, y_cursor), bullet[:120], font=bullet_font)
            y_cursor = bbox[3] + int(bullet_size * 0.6)
        except AttributeError:
            y_cursor += bullet_size * 2

    # Lower-third bar (name card)
    if show_lower_third:
        bar_h = int(h * 0.12)
        bar_y = h - bar_h
        alpha = int(overlay_opacity * 255)
        overlay = PILImage.new("RGBA", (w, bar_h), (*secondary_rgb, alpha))
        img_rgba = img.convert("RGBA")
        img_rgba.paste(overlay, (0, bar_y), overlay)
        img = img_rgba.convert("RGB")
        draw = ImageDraw.Draw(img)
        # Subtitle text placeholder
        lower_font = _load_font(max(20, h // 28), font_path)
        draw.text(
            (pad + bar_w + 16, bar_y + int(bar_h * 0.2)),
            title[:60],
            font=lower_font,
            fill=primary_rgb,
        )

    # Progress dots
    if total_slides > 1:
        dot_r = max(4, w // 120)
        dot_sp = dot_r * 3
        total_w = total_slides * dot_r * 2 + (total_slides - 1) * (dot_sp - dot_r * 2)
        dot_x = (w - total_w) // 2
        dot_y = h - int(h * 0.035)
        for i in range(total_slides):
            cx = dot_x + i * dot_sp
            fill = secondary_rgb if i == slide_index else dim  # type: ignore[assignment]
            draw.ellipse([(cx, dot_y - dot_r), (cx + dot_r * 2, dot_y + dot_r)], fill=fill)

    # Logo watermark
    if logo_path and logo_path.exists():
        try:
            logo = PILImage.open(str(logo_path)).convert("RGBA")
            logo_h = max(40, h // 12)
            logo_w = int(logo.width * (logo_h / logo.height))
            logo   = logo.resize((logo_w, logo_h), PILImage.LANCZOS)
            img.paste(logo, (w - logo_w - pad, int(h * 0.025)), logo)
        except Exception as exc:  # noqa: BLE001
            log.warning("motion_logo_paste_failed", error=str(exc))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")


def _draw_wrapped_text(draw, text, font, x, y, max_width, line_spacing, fill, max_y: int = 99999):
    words = text.split()
    line = ""
    for word in words:
        test = f"{line} {word}".strip()
        try:
            tw = draw.textlength(test, font=font)
        except Exception:  # noqa: BLE001
            tw = len(test) * 10
        if tw <= max_width:
            line = test
        else:
            if line:
                if y > max_y:
                    return
                draw.text((x, y), line, font=font, fill=fill)
                y += line_spacing
            line = word
    if line and y <= max_y:
        draw.text((x, y), line, font=font, fill=fill)


def _load_font(size: int, font_path: Path | None):
    from PIL import ImageFont
    if font_path and font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:  # noqa: BLE001
            pass
    for p in [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:  # noqa: BLE001
                continue
    return ImageFont.load_default()


# ── Synchronous MoviePy assembly ─────────────────────────────────────────────

def _assemble_motion(
    *,
    slide_data: list[_SlideData],
    music_path: Path | None,
    music_volume: float,
    voice_volume: float,
    w: int,
    h: int,
    bg_rgb: tuple[int, int, int],
    transition: str,
    transition_dur: float,
    tmp_dir: Path,
    output_path: Path,
    fps: int,
) -> float:
    from moviepy import (
        AudioFileClip,
        ImageClip,
        ColorClip,
        concatenate_videoclips,
        CompositeAudioClip,
        concatenate_audioclips,
    )
    from app.services.video import vfx_compat as vfx

    clips = []
    total_duration = 0.0

    for sd in slide_data:
        d = sd.duration
        total_duration += d

        clip = ImageClip(str(sd.image_path), duration=d) if sd.image_path.exists() \
               else ColorClip(size=(w, h), color=bg_rgb, duration=d)

        if sd.narration_audio and sd.narration_audio.exists():
            try:
                narr = AudioFileClip(str(sd.narration_audio))
                if narr.duration > d:
                    narr = narr.subclipped(0, d)
                if voice_volume < 1.0:
                    narr = narr.with_effects([MultiplyVolume(voice_volume)])
                clip = clip.with_audio(narr)
            except Exception as exc:  # noqa: BLE001
                log.warning("motion_audio_failed", error=str(exc))

        if transition == "fade":
            clip = clip.with_effects([vfx.FadeIn(transition_dur), vfx.FadeOut(transition_dur)])

        clips.append(clip)

    if not clips:
        final = ColorClip(size=(w, h), color=bg_rgb, duration=3.0)
        total_duration = 3.0
    else:
        final = concatenate_videoclips(clips, method="compose")

    if music_path and music_path.exists() and music_volume > 0:
        try:
            music = AudioFileClip(str(music_path)).with_effects([MultiplyVolume(music_volume)])
            if music.duration < total_duration:
                loops = int(total_duration / music.duration) + 1
                music = concatenate_audioclips([music] * loops)
            music = music.subclipped(0, total_duration)
            existing = final.audio
            final = final.with_audio(
                CompositeAudioClip([existing, music]) if existing else music
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("motion_music_overlay_failed", error=str(exc))

    _write(final, output_path, tmp_dir, fps)
    final.close()
    return total_duration


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = str(hex_color).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (37, 99, 235)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (37, 99, 235)


def _truthy(v) -> bool:
    """Coerce PHP-style bool/string/int to Python bool."""
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v != 0
    return str(v).lower() not in ("false", "0", "no", "off", "")


def _write(clip, output_path: Path, tmp_dir: Path, fps: int = 24) -> None:
    clip.write_videofile(
        str(output_path),
        codec="libx264",
        fps=fps,
        audio_codec="aac",
        temp_audiofile=str(tmp_dir / "_tmp_audio.m4a"),
        remove_temp=True,
        logger=None,
    )
