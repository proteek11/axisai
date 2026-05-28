"""
PresentationRenderer — PowerPoint-style slide deck video.

Structure:
  - LLM breaks script into slides (slide_type, title, bullets/content,
    speaker_notes, layout, duration_seconds)
  - Slide types supported:
      title_slide   — large centered title + subtitle
      content       — title + bullet points (default)
      two_column    — title + left bullets + right bullets
      quote         — centered pull-quote with attribution
      image_text    — Pexels image left + text right
      divider       — full-screen accent color separator slide
  - Per slide: Pillow rendering + TTS narration from speaker_notes
  - Slide transitions (fade / slide_left) + optional background music
  - Brand color palette applied throughout

No external API calls required — fully offline render using brand colors.
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

# Slide type constants
_SLIDE_TITLE     = "title_slide"
_SLIDE_CONTENT   = "content"
_SLIDE_TWO_COL   = "two_column"
_SLIDE_QUOTE     = "quote"
_SLIDE_IMG_TEXT  = "image_text"
_SLIDE_DIVIDER   = "divider"


@dataclass
class _SlideData:
    narration_audio: Path | None
    image_path: Path
    duration: float
    slide_type: str
    title: str
    content: list[str] = field(default_factory=list)
    right_content: list[str] = field(default_factory=list)
    quote_text: str = ""
    quote_attribution: str = ""
    subtitle: str = ""


class PresentationRenderer(BaseVideoRenderer):
    """PowerPoint-style slide deck video with multiple layout types."""

    async def render(self) -> RenderResult:
        script = self.job.script or self.job.title
        w, h = self._get_resolution()
        primary, secondary = self._get_brand_colors()

        # ── Resolve template-specific settings ────────────────────────────────
        show_slide_numbers: bool = _truthy(self.settings.get("showslidenumbers", True))
        presentation_style: str  = str(self.settings.get("presentationstyle") or "pitch").lower()
        # presentationstyle affects LLM scene planning context (slide emphasis)
        loop = asyncio.get_running_loop()
        font_path: Path | None = await loop.run_in_executor(
            None, self._get_font_path, True
        )
        transition_dur = self._get_transition_duration()
        music_volume   = self._get_music_volume()

        # ── Plan slides ───────────────────────────────────────────────────────
        await self._update_progress(20, "Planning presentation slides...")
        slides = await self._plan_scenes(script, extra_context={"presentation_style": presentation_style})
        if not slides:
            slides = [{
                "slide_type": _SLIDE_TITLE,
                "title": self.job.title,
                "subtitle": "",
                "speaker_notes": script,
                "duration_seconds": 10,
            }]

        # ── Optional logo ─────────────────────────────────────────────────────
        logo_path: Path | None = None
        logo_url = self.assets.get("logo_url")
        if logo_url:
            try:
                logo_path = self.tmp_dir / "logo.png"
                await self._download_asset(logo_url, logo_path)
                if not logo_path.exists():
                    logo_path = None
            except Exception as exc:  # noqa: BLE001
                log.warning("presentation_logo_failed", error=str(exc))

        # ── Build each slide ──────────────────────────────────────────────────
        await self._update_progress(30, f"Rendering {len(slides)} slides...")
        slide_data: list[_SlideData] = []

        for idx, slide in enumerate(slides):
            slide_type    = str(slide.get("slide_type", _SLIDE_CONTENT))
            title         = str(slide.get("title", ""))
            subtitle      = str(slide.get("subtitle", ""))
            bullets       = slide.get("bullets", slide.get("content", []))
            right_bullets = slide.get("right_bullets", slide.get("right_content", []))
            quote_text    = str(slide.get("quote", slide.get("quote_text", "")))
            quote_attr    = str(slide.get("attribution", slide.get("quote_attribution", "")))
            speaker_notes = str(slide.get("speaker_notes", slide.get("narration", title)))

            if isinstance(bullets, str):
                bullets = [b.strip() for b in bullets.split("\n") if b.strip()]
            if isinstance(right_bullets, str):
                right_bullets = [b.strip() for b in right_bullets.split("\n") if b.strip()]

            # TTS from speaker notes
            audio_path = self.tmp_dir / f"slide_{idx}_audio.mp3"
            try:
                tts_dur = await self._synthesize_tts(speaker_notes, audio_path)
                duration = max(_MIN_SLIDE_DURATION, tts_dur)
            except Exception as exc:  # noqa: BLE001
                log.warning("presentation_tts_failed", slide=idx, error=str(exc))
                audio_path = None
                duration = float(slide.get("duration_seconds", 8))

            # For image_text slides, fetch a Pexels image
            img_bg_path: Path | None = None
            if slide_type == _SLIDE_IMG_TEXT and self.providers.stock:
                img_bg_path = await self._fetch_slide_image(idx, title)

            # Render slide as PNG
            image_path = self.tmp_dir / f"slide_{idx}.png"
            await loop.run_in_executor(
                None,
                _render_slide,
                slide_type, title, subtitle, bullets, right_bullets,
                quote_text, quote_attr, img_bg_path,
                w, h, image_path,
                _hex_to_rgb(primary), _hex_to_rgb(secondary),
                logo_path, idx, len(slides),
                show_slide_numbers, font_path,
            )

            slide_data.append(_SlideData(
                narration_audio=audio_path if (audio_path and audio_path.exists()) else None,
                image_path=image_path,
                duration=duration,
                slide_type=slide_type,
                title=title,
                content=bullets if isinstance(bullets, list) else [],
                right_content=right_bullets if isinstance(right_bullets, list) else [],
                quote_text=quote_text,
                quote_attribution=quote_attr,
                subtitle=subtitle,
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
                log.warning("presentation_music_failed", error=str(exc))

        # ── Assemble ──────────────────────────────────────────────────────────
        await self._update_progress(72, "Assembling presentation video...")
        output_path = self.tmp_dir / "raw.mp4"

        fn = functools.partial(
            _assemble_presentation,
            slide_data=slide_data,
            music_path=music_path,
            music_volume=music_volume,
            w=w, h=h,
            transition=self._get_transition(),
            transition_dur=transition_dur,
            tmp_dir=self.tmp_dir,
            output_path=output_path,
            fps=_FPS,
        )
        total_duration = await loop.run_in_executor(None, fn)

        await self._update_progress(75, "Presentation render complete.")
        return RenderResult(
            raw_mp4_path=output_path,
            duration_seconds=total_duration,
            metadata={
                "slide_count": len(slides),
                "presentationstyle": presentation_style,
                "showslidenumbers": show_slide_numbers,
            },
        )

    async def _fetch_slide_image(self, idx: int, query: str) -> Path | None:
        if not query:
            return None
        dest = self.tmp_dir / f"slide_img_{idx}.jpg"
        try:
            images = await self.providers.stock.search_images(
                query=query[:60], count=1, orientation="landscape"
            )
            if images:
                await self._download_asset(images[0].url, dest, timeout_sec=30)
                if dest.exists():
                    return dest
        except Exception as exc:  # noqa: BLE001
            log.warning("presentation_img_fetch_failed", idx=idx, error=str(exc))
        return None


# ── Synchronous slide rendering ───────────────────────────────────────────────

def _render_slide(
    slide_type: str,
    title: str,
    subtitle: str,
    bullets: list[str],
    right_bullets: list[str],
    quote_text: str,
    quote_attr: str,
    img_bg_path: Path | None,
    w: int,
    h: int,
    output_path: Path,
    primary_rgb: tuple[int, int, int],
    secondary_rgb: tuple[int, int, int],
    logo_path: Path | None,
    slide_index: int,
    total_slides: int,
    show_slide_numbers: bool = True,
    font_path: "Path | None" = None,  # type: ignore[name-defined]
) -> None:
    """Dispatch to the appropriate slide type renderer."""
    if slide_type == _SLIDE_TITLE:
        _render_title_slide(title, subtitle, w, h, output_path,
                            primary_rgb, secondary_rgb, logo_path)
    elif slide_type == _SLIDE_DIVIDER:
        _render_divider_slide(title, w, h, output_path, primary_rgb, secondary_rgb)
    elif slide_type == _SLIDE_QUOTE:
        _render_quote_slide(quote_text, quote_attr, w, h, output_path,
                            primary_rgb, secondary_rgb)
    elif slide_type == _SLIDE_TWO_COL:
        _render_two_column_slide(title, bullets, right_bullets, w, h, output_path,
                                 primary_rgb, secondary_rgb, logo_path,
                                 slide_index, total_slides)
    elif slide_type == _SLIDE_IMG_TEXT:
        _render_image_text_slide(title, bullets, img_bg_path, w, h, output_path,
                                 primary_rgb, secondary_rgb, logo_path)
    else:
        # Default: content slide
        _render_content_slide(title, bullets, w, h, output_path,
                              primary_rgb, secondary_rgb, logo_path,
                              slide_index, total_slides)


def _make_base(w: int, h: int, primary_rgb):
    """Create gradient background image."""
    from PIL import Image as PILImage, ImageDraw
    img  = PILImage.new("RGB", (w, h), color=primary_rgb)
    draw = ImageDraw.Draw(img)
    dark = tuple(max(0, int(c * 0.70)) for c in primary_rgb)
    for y in range(h):
        t = y / h
        row = tuple(int(primary_rgb[i] * (1 - t) + dark[i] * t) for i in range(3))
        draw.line([(0, y), (w, y)], fill=row)  # type: ignore[arg-type]
    return img


def _paste_logo(img, logo_path: Path | None, w: int, h: int, pad: int):
    if not logo_path or not logo_path.exists():
        return
    try:
        from PIL import Image as PILImage
        logo = PILImage.open(str(logo_path)).convert("RGBA")
        logo_h = max(30, h // 16)
        ratio  = logo_h / logo.height
        logo_w = int(logo.width * ratio)
        logo   = logo.resize((logo_w, logo_h), PILImage.LANCZOS)
        img.paste(logo, (w - logo_w - pad, pad // 2), logo)
    except Exception as exc:  # noqa: BLE001
        log.warning("presentation_logo_paste_failed", error=str(exc))


def _render_title_slide(title, subtitle, w, h, output_path,
                         primary_rgb, secondary_rgb, logo_path):
    from PIL import ImageDraw
    img  = _make_base(w, h, primary_rgb)
    draw = ImageDraw.Draw(img)
    pad  = int(w * 0.08)

    # Accent bar (horizontal, centered vertically)
    bar_h = max(4, h // 60)
    draw.rectangle([(pad, h // 2 - bar_h // 2), (w - pad, h // 2 + bar_h // 2)],
                   fill=secondary_rgb)

    title_size    = max(48, h // 8)
    subtitle_size = max(28, h // 18)
    title_font    = _find_font(title_size)
    sub_font      = _find_font(subtitle_size)

    if title:
        try:
            tw = draw.textlength(title[:60], font=title_font)
        except Exception:  # noqa: BLE001
            tw = w - 2 * pad
        tx = max(pad, (w - int(tw)) // 2)
        ty = int(h * 0.28)
        draw.text((tx, ty), title[:60], font=title_font, fill=secondary_rgb)

    if subtitle:
        try:
            sw = draw.textlength(subtitle[:80], font=sub_font)
        except Exception:  # noqa: BLE001
            sw = w - 2 * pad
        sx = max(pad, (w - int(sw)) // 2)
        sy = int(h * 0.56)
        draw.text((sx, sy), subtitle[:80], font=sub_font,
                  fill=tuple(max(0, int(c * 0.85)) for c in secondary_rgb))  # type: ignore[arg-type]

    _paste_logo(img, logo_path, w, h, pad)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")


def _render_divider_slide(title, w, h, output_path, primary_rgb, secondary_rgb):
    """Full-screen accent color divider with centered title."""
    from PIL import Image as PILImage, ImageDraw
    # Use secondary as background for contrast
    img  = PILImage.new("RGB", (w, h), color=secondary_rgb)
    draw = ImageDraw.Draw(img)
    font_size = max(54, h // 7)
    font = _find_font(font_size)
    if title:
        try:
            tw = draw.textlength(title[:50], font=font)
        except Exception:  # noqa: BLE001
            tw = w * 0.6
        tx = max(20, (w - int(tw)) // 2)
        ty = (h - font_size) // 2
        draw.text((tx, ty), title[:50], font=font, fill=primary_rgb)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")


def _render_quote_slide(quote_text, attribution, w, h, output_path,
                         primary_rgb, secondary_rgb):
    """Large pull-quote centered on gradient background."""
    from PIL import ImageDraw
    img  = _make_base(w, h, primary_rgb)
    draw = ImageDraw.Draw(img)
    pad  = int(w * 0.10)

    quote_size = max(32, h // 12)
    attr_size  = max(22, h // 22)
    q_font = _find_font(quote_size)
    a_font = _find_font(attr_size)

    # Opening quote mark
    draw.text((pad, int(h * 0.15)), "“", font=_find_font(max(80, h // 5)),
              fill=secondary_rgb)

    if quote_text:
        _draw_wrapped_text(draw, quote_text[:300], q_font,
                           x=pad + 20, y=int(h * 0.28),
                           max_width=w - 2 * pad - 20,
                           line_spacing=int(quote_size * 1.5),
                           fill=secondary_rgb)

    if attribution:
        draw.text((w - pad - 20, int(h * 0.78)), f"— {attribution[:60]}",
                  font=a_font,
                  fill=tuple(max(0, int(c * 0.80)) for c in secondary_rgb),  # type: ignore[arg-type]
                  anchor="ra")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")


def _render_content_slide(title, bullets, w, h, output_path,
                           primary_rgb, secondary_rgb, logo_path,
                           slide_index, total_slides):
    """Standard title + bullet points layout."""
    from PIL import ImageDraw
    img  = _make_base(w, h, primary_rgb)
    draw = ImageDraw.Draw(img)
    pad  = int(w * 0.07)

    bar_w = max(8, w // 60)
    draw.rectangle([(pad // 2, pad // 2), (pad // 2 + bar_w, h - pad // 2)],
                   fill=secondary_rgb)

    title_size  = max(40, h // 10)
    bullet_size = max(26, h // 22)
    title_font  = _find_font(title_size)
    b_font      = _find_font(bullet_size)

    y = int(h * 0.10)
    if title:
        draw.text((pad + bar_w + 10, y), title[:70], font=title_font, fill=secondary_rgb)
        bbox = draw.textbbox((pad + bar_w + 10, y), title[:70], font=title_font)
        y = bbox[3] + int(h * 0.04)
        draw.line([(pad + bar_w + 10, y), (w - pad, y)],
                  fill=secondary_rgb, width=2)
        y += int(h * 0.03)

    dim = tuple(max(0, int(c * 0.85)) for c in secondary_rgb)
    bx  = pad + bar_w + 22
    for bullet in bullets[:8]:
        if y + bullet_size * 2 > h - int(h * 0.12):
            break
        draw.text((bx - 22, y), "•", font=b_font, fill=secondary_rgb)
        _draw_wrapped_text(draw, bullet[:120], b_font,
                           x=bx, y=y,
                           max_width=w - bx - pad,
                           line_spacing=int(bullet_size * 1.6),
                           fill=dim)  # type: ignore[arg-type]
        bbox = draw.textbbox((bx, y), bullet[:120], font=b_font)
        y = bbox[3] + int(bullet_size * 0.6)

    # Progress dots
    if total_slides > 1:
        _draw_progress_dots(draw, slide_index, total_slides, w, h,
                            secondary_rgb, dim)  # type: ignore[arg-type]

    _paste_logo(img, logo_path, w, h, pad)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")


def _render_two_column_slide(title, left_bullets, right_bullets, w, h, output_path,
                              primary_rgb, secondary_rgb, logo_path,
                              slide_index, total_slides):
    """Title + two equal bullet columns."""
    from PIL import ImageDraw
    img  = _make_base(w, h, primary_rgb)
    draw = ImageDraw.Draw(img)
    pad  = int(w * 0.06)

    title_size  = max(36, h // 12)
    bullet_size = max(22, h // 26)
    title_font  = _find_font(title_size)
    b_font      = _find_font(bullet_size)

    y = int(h * 0.08)
    if title:
        draw.text((pad, y), title[:70], font=title_font, fill=secondary_rgb)
        bbox = draw.textbbox((pad, y), title[:70], font=title_font)
        y = bbox[3] + int(h * 0.04)
        draw.line([(pad, y), (w - pad, y)], fill=secondary_rgb, width=2)
        y += int(h * 0.03)

    # Divider line between columns
    mid_x = w // 2
    draw.line([(mid_x, y), (mid_x, h - int(h * 0.12))],
              fill=tuple(max(0, int(c * 0.50)) for c in secondary_rgb),  # type: ignore[arg-type]
              width=1)

    dim = tuple(max(0, int(c * 0.85)) for c in secondary_rgb)
    col_w = mid_x - pad - 20

    # Left column
    ly = y
    for bullet in left_bullets[:6]:
        if ly + bullet_size * 2 > h - int(h * 0.12):
            break
        draw.text((pad, ly), "•", font=b_font, fill=secondary_rgb)
        _draw_wrapped_text(draw, bullet[:80], b_font,
                           x=pad + 20, y=ly,
                           max_width=col_w - 20,
                           line_spacing=int(bullet_size * 1.5),
                           fill=dim)  # type: ignore[arg-type]
        bbox = draw.textbbox((pad + 20, ly), bullet[:80], font=b_font)
        ly = bbox[3] + int(bullet_size * 0.5)

    # Right column
    ry = y
    rx = mid_x + 20
    for bullet in right_bullets[:6]:
        if ry + bullet_size * 2 > h - int(h * 0.12):
            break
        draw.text((rx, ry), "•", font=b_font, fill=secondary_rgb)
        _draw_wrapped_text(draw, bullet[:80], b_font,
                           x=rx + 20, y=ry,
                           max_width=col_w - 20,
                           line_spacing=int(bullet_size * 1.5),
                           fill=dim)  # type: ignore[arg-type]
        bbox = draw.textbbox((rx + 20, ry), bullet[:80], font=b_font)
        ry = bbox[3] + int(bullet_size * 0.5)

    if total_slides > 1:
        _draw_progress_dots(draw, slide_index, total_slides, w, h,
                            secondary_rgb, dim)  # type: ignore[arg-type]

    _paste_logo(img, logo_path, w, h, pad)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")


def _render_image_text_slide(title, bullets, img_bg_path, w, h, output_path,
                              primary_rgb, secondary_rgb, logo_path):
    """Left half = image, right half = text."""
    from PIL import Image as PILImage, ImageDraw
    img  = _make_base(w, h, primary_rgb)
    draw = ImageDraw.Draw(img)

    half_w = w // 2
    pad    = int(w * 0.04)

    # Left image panel
    if img_bg_path and img_bg_path.exists():
        try:
            photo = PILImage.open(str(img_bg_path)).convert("RGB")
            fill_scale = max(half_w / photo.width, h / photo.height)
            pw = int(photo.width * fill_scale)
            ph = int(photo.height * fill_scale)
            photo = photo.resize((pw, ph), PILImage.LANCZOS)
            left_crop = photo.crop((0, 0, half_w, h))
            img.paste(left_crop, (0, 0))
        except Exception as exc:  # noqa: BLE001
            log.warning("presentation_img_text_photo_failed", error=str(exc))

    # Divider line
    draw.line([(half_w, 0), (half_w, h)], fill=secondary_rgb, width=3)

    # Right text panel
    title_size  = max(34, h // 12)
    bullet_size = max(22, h // 26)
    t_font = _find_font(title_size)
    b_font = _find_font(bullet_size)
    tx = half_w + pad
    y  = int(h * 0.10)

    if title:
        draw.text((tx, y), title[:50], font=t_font, fill=secondary_rgb)
        bbox = draw.textbbox((tx, y), title[:50], font=t_font)
        y = bbox[3] + int(h * 0.04)
        draw.line([(tx, y), (w - pad, y)], fill=secondary_rgb, width=2)
        y += int(h * 0.03)

    dim = tuple(max(0, int(c * 0.85)) for c in secondary_rgb)
    for bullet in bullets[:6]:
        if y + bullet_size * 2 > h - int(h * 0.10):
            break
        draw.text((tx, y), "•", font=b_font, fill=secondary_rgb)
        _draw_wrapped_text(draw, bullet[:80], b_font,
                           x=tx + 20, y=y,
                           max_width=w - tx - pad - 20,
                           line_spacing=int(bullet_size * 1.5),
                           fill=dim)  # type: ignore[arg-type]
        bbox = draw.textbbox((tx + 20, y), bullet[:80], font=b_font)
        y = bbox[3] + int(bullet_size * 0.5)

    _paste_logo(img, logo_path, w, h, pad)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")


def _draw_progress_dots(draw, slide_index, total_slides, w, h,
                         active_color, inactive_color):
    dot_r = max(4, w // 120)
    spacing = dot_r * 3
    total_w = (total_slides * dot_r * 2) + ((total_slides - 1) * (spacing - dot_r * 2))
    dx = (w - total_w) // 2
    dy = h - int(h * 0.05)
    for i in range(total_slides):
        cx = dx + i * spacing
        fill = active_color if i == slide_index else inactive_color
        draw.ellipse([(cx, dy - dot_r), (cx + dot_r * 2, dy + dot_r)], fill=fill)


# ── MoviePy assembly ──────────────────────────────────────────────────────────

def _assemble_presentation(
    *,
    slide_data: list[_SlideData],
    music_path: Path | None,
    music_volume: float,
    w: int,
    h: int,
    transition: str,
    transition_dur: float = 0.4,
    tmp_dir: Path,
    output_path: Path,
    fps: int,
) -> float:
    from moviepy import (
        AudioFileClip,
        ImageClip,
        ColorClip,
        concatenate_videoclips,
    )
    from app.services.video import vfx_compat as vfx

    clips = []
    total_duration = 0.0

    for sd in slide_data:
        d = sd.duration
        total_duration += d

        if sd.image_path.exists():
            clip = ImageClip(str(sd.image_path), duration=d)
        else:
            clip = ColorClip(size=(w, h), color=(37, 99, 235), duration=d)

        if sd.narration_audio and sd.narration_audio.exists():
            try:
                narration = AudioFileClip(str(sd.narration_audio))
                if narration.duration > d:
                    narration = narration.subclipped(0, d)
                clip = clip.with_audio(narration)
            except Exception as exc:  # noqa: BLE001
                log.warning("presentation_audio_failed", error=str(exc))

        if transition == "fade":
            clip = clip.with_effects([vfx.FadeIn(transition_dur), vfx.FadeOut(transition_dur)])

        clips.append(clip)

    if not clips:
        final = ColorClip(size=(w, h), color=(37, 99, 235), duration=3.0)
        total_duration = 3.0
    else:
        final = concatenate_videoclips(clips, method="compose")

    if music_path and music_path.exists() and music_volume > 0:
        final = _overlay_music(final, music_path, music_volume, total_duration)

    _write(final, output_path, tmp_dir, fps)
    final.close()
    return total_duration


# ── Shared helpers ────────────────────────────────────────────────────────────

def _draw_wrapped_text(draw, text, font, x, y, max_width, line_spacing, fill):
    words = text.split()
    line  = ""
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
                draw.text((x, y), line, font=font, fill=fill)
                y += line_spacing
            line = word
    if line:
        draw.text((x, y), line, font=font, fill=fill)


def _find_font(size: int):
    from PIL import ImageFont
    search = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in search:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:  # noqa: BLE001
                continue
    try:
        return ImageFont.truetype("arialbd.ttf", size)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


def _overlay_music(clip, music_path: Path, music_volume: float, duration: float):
    try:
        from moviepy import AudioFileClip, CompositeAudioClip, concatenate_audioclips
        from moviepy.audio.fx import MultiplyVolume
        music = AudioFileClip(str(music_path)).with_effects([MultiplyVolume(music_volume)])
        if music.duration < duration:
            loops = int(duration / music.duration) + 1
            music = concatenate_audioclips([music] * loops)
        music = music.subclipped(0, duration)
        existing = clip.audio
        if existing is not None:
            return clip.with_audio(CompositeAudioClip([existing, music]))
        return clip.with_audio(music)
    except Exception as exc:  # noqa: BLE001
        log.warning("presentation_music_overlay_failed", error=str(exc))
        return clip


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (37, 99, 235)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


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
