"""
SlideshowRenderer — photo slideshow with ken burns effects and narration.

Structure:
  - LLM breaks script into slides, each with narration + optional caption
  - For each slide: Pexels image → ken burns clip → TTS narration
  - Optional: caption text overlay at bottom
  - Optional: background music under narration

MoviePy dependency: requires ImageMagick only if captions are enabled.
Pexels dependency: requires VIDEO_PEXELS_API_KEY env var.
"""
from __future__ import annotations

import asyncio
import functools
from dataclasses import dataclass
from pathlib import Path

import structlog

from app.services.video import RenderResult
from app.services.video.base_renderer import BaseVideoRenderer

log = structlog.get_logger(__name__)

_FPS = 24
_MIN_SLIDE_DURATION = 3.0   # seconds — floor for very short narrations
_FALLBACK_COLOR = (30, 30, 30)   # dark grey background when image unavailable


@dataclass
class _SlideData:
    narration_audio: Path | None
    image_path: Path | None
    duration: float
    caption: str
    ken_burns: str   # zoom_in | zoom_out | pan_left | pan_right


class SlideshowRenderer(BaseVideoRenderer):
    """Photo slideshow with ken burns effects, captions, and TTS narration."""

    async def render(self) -> RenderResult:
        script = self.job.script or self.job.title
        w, h = self._get_resolution()

        # ── Resolve template-specific settings ────────────────────────────────
        primary, secondary = self._get_brand_colors()
        # slidestyle: "standard" | "cinematic" | "minimal" | "corporate"
        slide_style: str   = str(self.settings.get("slidestyle") or "standard").lower()
        # slideperscene: how many Pexels images to use per LLM scene (1-3)
        try:
            slides_per_scene = max(1, min(3, int(self.settings.get("slideperscene") or 1)))
        except (ValueError, TypeError):
            slides_per_scene = 1

        overlay_opacity = self._get_overlay_opacity()
        transition_dur  = self._get_transition_duration()
        music_volume    = self._get_music_volume()

        # ── Extract PDF pages to images (if pdf_url provided in assets) ────
        await self._update_progress(10, "Checking for PDF slides...")
        await _extract_pdf_pages(self.assets, self.tmp_dir, self)

        # ── Plan slides ───────────────────────────────────────────────────────
        await self._update_progress(20, "Planning slideshow structure...")
        slides = await self._plan_scenes(script, extra_context={"slide_style": slide_style, "slides_per_scene": slides_per_scene})
        if not slides:
            slides = [{"narration": script, "caption": "", "ken_burns": "zoom_in"}]

        # ── Build each slide: TTS + Pexels image ──────────────────────────────
        await self._update_progress(30, f"Processing {len(slides)} slides...")
        slide_data: list[_SlideData] = []

        for idx, slide in enumerate(slides):
            narration = str(slide.get("narration", script))
            caption = str(slide.get("caption", ""))
            ken_burns = str(slide.get("ken_burns", "zoom_in"))

            # TTS
            audio_path = self.tmp_dir / f"slide_{idx}_audio.mp3"
            try:
                tts_dur = await self._synthesize_tts(narration, audio_path)
                duration = max(_MIN_SLIDE_DURATION, tts_dur)
            except Exception as exc:  # noqa: BLE001
                log.warning("slideshow_tts_failed", slide=idx, error=str(exc))
                audio_path = None
                duration = 5.0

            # Image resolution order:
            #  1. pre-provided image_urls from _resolved_assets (Moodle or test curl)
            #  2. PDF pages (if pdf_url or pdf_pages_dir in assets)
            #  3. Pexels stock search
            #  4. solid brand-colour fallback
            query = narration[:60].strip()
            image_path: Path | None = None

            # 1. Pre-provided image_urls list
            _image_urls: list[str] = self.assets.get("image_urls") or []
            if _image_urls and idx < len(_image_urls):
                try:
                    image_path = self.tmp_dir / f"slide_{idx}_img.jpg"
                    await self._download_asset(_image_urls[idx], image_path, timeout_sec=30)
                except Exception as exc:  # noqa: BLE001
                    log.warning("slideshow_provided_image_failed", slide=idx, error=str(exc))
                    image_path = None

            # 2. PDF pages (pre-extracted into tmp_dir by _extract_pdf_pages)
            if not (image_path and image_path.exists()):
                _pdf_page = self.tmp_dir / f"pdf_page_{idx}.jpg"
                if _pdf_page.exists():
                    image_path = _pdf_page

            # 3. Pexels stock search fallback
            if not (image_path and image_path.exists()) and self.providers.stock:
                try:
                    images = await self.providers.stock.search_images(
                        query=query, count=1,
                        orientation="portrait" if w < h else "landscape"
                    )
                    if images:
                        image_path = self.tmp_dir / f"slide_{idx}_img.jpg"
                        await self._download_asset(images[0].url, image_path, timeout_sec=30)
                except Exception as exc:  # noqa: BLE001
                    log.warning("slideshow_image_download_failed", slide=idx, error=str(exc))

            slide_data.append(_SlideData(
                narration_audio=audio_path if (audio_path and audio_path.exists()) else None,
                image_path=image_path if (image_path and image_path.exists()) else None,
                duration=duration,
                caption=caption,
                ken_burns=ken_burns,
            ))

            pct = 30 + int(40 * (idx + 1) / len(slides))
            await self._update_progress(pct, f"Slide {idx + 1}/{len(slides)} ready")

        # ── Optional background music ─────────────────────────────────────────
        music_url = self.assets.get("music_url")
        music_path: Path | None = None
        if music_url:
            try:
                music_path = self.tmp_dir / "music.mp3"
                await self._download_asset(music_url, music_path)
            except Exception as exc:  # noqa: BLE001
                log.warning("slideshow_music_download_failed", error=str(exc))

        # ── Assemble video in thread executor ─────────────────────────────────
        await self._update_progress(72, "Assembling slideshow video...")
        output_path = self.tmp_dir / "raw.mp4"

        fn = functools.partial(
            _assemble_slideshow,
            slide_data=slide_data,
            music_path=music_path,
            music_volume=music_volume,
            w=w, h=h,
            primary_rgb=_hex_to_rgb(primary),
            text_color=secondary,
            transition=self._get_transition(),
            transition_dur=transition_dur,
            overlay_opacity=overlay_opacity,
            slide_style=slide_style,
            tmp_dir=self.tmp_dir,
            output_path=output_path,
            fps=_FPS,
        )
        loop = asyncio.get_running_loop()
        total_duration = await loop.run_in_executor(None, fn)

        await self._update_progress(75, "Slideshow assembly complete.")
        return RenderResult(
            raw_mp4_path=output_path,
            duration_seconds=total_duration,
            metadata={
                "slide_count": len(slides),
                "slidestyle": slide_style,
                "slideperscene": slides_per_scene,
            },
        )


# ── Synchronous MoviePy assembly ─────────────────────────────────────────────

def _assemble_slideshow(
    *,
    slide_data: list[_SlideData],
    music_path: Path | None,
    music_volume: float,
    w: int,
    h: int,
    primary_rgb: tuple[int, int, int],
    text_color: str,
    transition: str,
    transition_dur: float = 0.4,
    overlay_opacity: float = 0.55,
    slide_style: str = "standard",
    tmp_dir: Path,
    output_path: Path,
    fps: int,
) -> float:
    from moviepy import (
        AudioFileClip,
        ColorClip,
        CompositeVideoClip,
        concatenate_videoclips,
    )
    from app.services.video import vfx_compat as vfx

    clips = []
    total_duration = 0.0

    for sd in slide_data:
        d = sd.duration
        total_duration += d

        # ── Base layer: image or solid color ─────────────────────────────────
        if sd.image_path and sd.image_path.exists():
            try:
                base = _ken_burns_clip(sd.image_path, d, sd.ken_burns, w, h)
            except Exception as exc:  # noqa: BLE001
                log.warning("ken_burns_failed", error=str(exc))
                base = ColorClip(size=(w, h), color=primary_rgb, duration=d)
        else:
            base = ColorClip(size=(w, h), color=primary_rgb, duration=d)

        layers = [base]

        # ── Caption overlay ───────────────────────────────────────────────────
        if sd.caption.strip():
            caption_clips = _make_caption(sd.caption, d, w, h, text_color)
            if caption_clips:
                layers.extend(caption_clips)

        # ── Compose ───────────────────────────────────────────────────────────
        slide_clip = CompositeVideoClip(layers, size=(w, h)).with_duration(d)

        # ── Per-slide narration audio ─────────────────────────────────────────
        if sd.narration_audio and sd.narration_audio.exists():
            try:
                narration = AudioFileClip(str(sd.narration_audio))
                if narration.duration > d:
                    narration = narration.subclipped(0, d)
                slide_clip = slide_clip.with_audio(narration)
            except Exception as exc:  # noqa: BLE001
                log.warning("slide_audio_failed", error=str(exc))

        # ── Fade transition ───────────────────────────────────────────────────
        if transition == "fade":
            slide_clip = slide_clip.with_effects([vfx.FadeIn(0.3), vfx.FadeOut(0.3)])

        clips.append(slide_clip)

    if not clips:
        # Fallback: single black frame
        final = ColorClip(size=(w, h), color=(0, 0, 0), duration=3.0)
        total_duration = 3.0
    else:
        final = concatenate_videoclips(clips, method="compose")

    # ── Global background music ───────────────────────────────────────────────
    if music_path and music_path.exists() and music_volume > 0:
        final = _overlay_music(final, music_path, music_volume, total_duration)

    _write(final, output_path, tmp_dir, fps)
    final.close()
    return total_duration


def _ken_burns_clip(img_path: Path, duration: float, effect: str, w: int, h: int):
    """Create an ImageClip with a ken burns animation effect."""
    import numpy as np
    from PIL import Image as PILImage
    from moviepy import VideoClip

    # Load and scale image to cover target with zoom buffer
    pil_img = PILImage.open(str(img_path)).convert("RGB")
    fill_scale = max(w / pil_img.width, h / pil_img.height)
    buffer = 1.2   # 20% zoom room
    scaled_w = int(pil_img.width  * fill_scale * buffer)
    scaled_h = int(pil_img.height * fill_scale * buffer)
    pil_img = pil_img.resize((scaled_w, scaled_h), PILImage.LANCZOS)
    base = np.array(pil_img)
    bh, bw = base.shape[:2]

    def make_frame(t: float) -> np.ndarray:
        # Zoom factor: zoom_in grows 1→1.1, zoom_out shrinks 1.1→1
        progress = min(1.0, t / max(0.001, duration))
        if effect == "zoom_in":
            zoom = 1.0 + 0.1 * progress
        elif effect == "zoom_out":
            zoom = 1.1 - 0.1 * progress
        elif effect == "pan_left":
            # Pan: shift x from center to -buffer/2
            zoom = 1.05
        elif effect == "pan_right":
            zoom = 1.05
        else:
            zoom = 1.05

        # Visible area in base image coordinates
        vis_w = int(w / zoom)
        vis_h = int(h / zoom)

        # Pan offset
        if effect == "pan_left":
            cx = int(bw / 2 + (bw - w) * 0.2 * (1 - progress))
        elif effect == "pan_right":
            cx = int(bw / 2 - (bw - w) * 0.2 * (1 - progress))
        else:
            cx = bw // 2

        cy = bh // 2

        x0 = max(0, cx - vis_w // 2)
        y0 = max(0, cy - vis_h // 2)
        x1 = min(bw, x0 + vis_w)
        y1 = min(bh, y0 + vis_h)

        crop = base[y0:y1, x0:x1]

        # Resize crop to exact target size
        if crop.shape[1] != w or crop.shape[0] != h:
            crop = np.array(
                PILImage.fromarray(crop).resize((w, h), PILImage.BILINEAR)
            )
        return crop

    clip = VideoClip(make_frame, duration=duration)
    clip.fps = 24
    return clip


def _make_caption(
    text: str,
    duration: float,
    w: int,
    h: int,
    text_color: str,
) -> "list | None":
    """
    Create caption overlay clips: a semi-transparent bar + text.

    Returns [bar_clip, txt_clip] to be added directly to the parent
    CompositeVideoClip layers list.  Returns None on failure.

    Note: we return a list rather than a wrapped CompositeVideoClip to
    avoid MoviePy's RGBA color issue (ColorClip only accepts RGB tuples).
    """
    try:
        from moviepy import ColorClip, TextClip

        font_size = max(20, min(36, h // 22))   # scale with frame height, capped
        padding   = 16
        # Measure text height by creating a throwaway clip
        _txt_probe = TextClip(
            text=text[:160],
            font_size=font_size,
            color="white",
            size=(w - padding * 2, None),
            method="caption",
            text_align="center",
        )
        txt_h = int(getattr(_txt_probe, "size", (0, font_size * 3))[1])
        _txt_probe.close()

        bar_h = max(txt_h + padding * 2, max(60, h // 10))
        bar = (ColorClip(size=(w, bar_h), color=(0, 0, 0))
               .with_opacity(0.6)
               .with_duration(duration)
               .with_position(("center", h - bar_h)))

        txt = (TextClip(
            text=text[:160],
            font_size=font_size,
            color=_normalize_color(text_color),
            size=(w - padding * 2, bar_h - padding),
            method="caption",
            text_align="center",
        ).with_duration(duration)
         .with_position(("center", h - bar_h + padding // 2)))

        return [bar, txt]

    except Exception as exc:  # noqa: BLE001
        log.warning("caption_clip_failed", text=text[:40], error=str(exc))
        return None


def _overlay_music(clip, music_path: Path, music_volume: float, duration: float):
    """Add background music under the clip's existing audio."""
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
            mixed = CompositeAudioClip([existing, music])
        else:
            mixed = music
        return clip.with_audio(mixed)
    except Exception as exc:  # noqa: BLE001
        log.warning("music_overlay_failed", error=str(exc))
        return clip


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (37, 99, 235)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _normalize_color(color: str) -> str:
    if color.startswith("#"):
        r, g, b = _hex_to_rgb(color)
        return f"rgb({r},{g},{b})"
    return color or "white"


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


async def _extract_pdf_pages(
    assets: dict,
    tmp_dir: Path,
    renderer: "SlideshowRenderer",
) -> None:
    """
    Convert PDF pages to JPEG images and save them as pdf_page_0.jpg,
    pdf_page_1.jpg, ... in tmp_dir.

    Triggered when assets contains either:
      - "pdf_url"  : a public/local HTTP(S) URL to a PDF file
      - "pdf_path" : an absolute local filesystem path to a PDF file

    Uses PyMuPDF (fitz) — install with: pip install pymupdf
    Falls back silently if pymupdf is not installed or PDF is unreadable.
    """
    pdf_url  = assets.get("pdf_url")
    pdf_path = assets.get("pdf_path")

    if not pdf_url and not pdf_path:
        return   # nothing to do

    try:
        import fitz  # PyMuPDF
    except ImportError:
        log.warning("pdf_extract_skipped", reason="pymupdf not installed — run: pip install pymupdf")
        return

    local_pdf: Path | None = None

    if pdf_path:
        local_pdf = Path(str(pdf_path))
        if not local_pdf.exists():
            log.warning("pdf_path_not_found", path=str(local_pdf))
            return

    elif pdf_url:
        local_pdf = tmp_dir / "source_slides.pdf"
        try:
            await renderer._download_asset(pdf_url, local_pdf, timeout_sec=60)
        except Exception as exc:  # noqa: BLE001
            log.warning("pdf_download_failed", url=pdf_url[:80], error=str(exc))
            return

    try:
        doc = fitz.open(str(local_pdf))
        log.info("pdf_opened", pages=doc.page_count, path=str(local_pdf))

        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            # Render at 2x scale for crisp images
            mat  = fitz.Matrix(2.0, 2.0)
            pix  = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
            out  = tmp_dir / f"pdf_page_{page_num}.jpg"
            pix.save(str(out))
            log.debug("pdf_page_extracted", page=page_num, path=str(out))

        page_count = doc.page_count
        doc.close()
        log.info("pdf_extraction_complete", pages=page_count)

    except Exception as exc:  # noqa: BLE001
        log.warning("pdf_extraction_failed", error=str(exc))
