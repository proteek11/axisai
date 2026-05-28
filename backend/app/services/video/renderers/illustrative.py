"""
IllustrativeRenderer — character + background illustrated video.

Structure:
  - LLM breaks script into scenes (character_position, background_hint,
    caption, narration, duration_seconds)
  - For each scene:
      1. Background: Pexels stock image OR solid brand-colour gradient
      2. Character PNG composited on background (RGBA alpha blend)
      3. TTS narration
      4. Bob animation: per-frame vertical sine offset computed on-the-fly
         (no frame pre-caching — O(1) RAM regardless of duration)
      5. Caption bar with semi-transparent overlay
  - Fade transitions + optional background music

Memory model (Task 42 — chunked rendering):
  Background and character are stored as pre-processed numpy arrays.
  Each video frame is composited on-demand inside make_frame(t), so
  RAM usage stays constant at ~3 × one-frame regardless of clip length.
  No list of PIL Images is built.

Character images:
  Expects PNG with transparency (RGBA).  character_urls is a list in
  tenant/job assets:  {"character_urls": ["https://...", "https://..."]}
  If no URLs provided, characters are skipped; background + caption only.
"""
from __future__ import annotations

import asyncio
import functools
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import structlog

from app.services.video import RenderResult
from app.services.video.base_renderer import BaseVideoRenderer

log = structlog.get_logger(__name__)

_FPS = 24
_MIN_SCENE_DURATION = 4.0

_POSITIONS: dict[str, tuple[float, float]] = {
    "left":         (0.05, 0.20),
    "right":        (0.55, 0.20),
    "center":       (0.25, 0.20),
    "center_left":  (0.10, 0.25),
    "center_right": (0.50, 0.25),
}
_DEFAULT_POSITION  = "left"
_BOB_AMPLITUDE_PX  = 6
_BOB_FREQ_HZ       = 0.8
_CHAR_HEIGHT_FRAC  = 0.60   # character height as fraction of frame height


@dataclass
class _SceneAssets:
    """
    Pre-processed numpy arrays for one scene.
    Held in RAM for the duration of that scene's VideoClip only.
    """
    bg_arr: np.ndarray         # H×W×3 uint8 background
    char_arr: np.ndarray | None  # char_h×char_w×4 uint8 RGBA (None if no char)
    char_x: int                # left-edge x when bob_offset == 0
    char_y: int                # top-edge y when bob_offset == 0
    cap_overlay: np.ndarray    # H×W×3 uint8 — bg with caption bar pre-drawn
    #                            (composited per-frame by replacing bottom rows)
    cap_bar_y: int             # pixel row where caption bar starts


@dataclass
class _SceneData:
    narration_audio: Path | None
    duration: float
    caption: str
    title: str
    assets: _SceneAssets


class IllustrativeRenderer(BaseVideoRenderer):
    """Illustrated character + background video with low memory footprint."""

    async def render(self) -> RenderResult:
        script = self.job.script or self.job.title
        w, h = self._get_resolution()
        primary, secondary = self._get_brand_colors()

        illustration_style: str = str(
            self.settings.get("illustrationstyle") or "flat"
        ).lower()
        try:
            character_count = max(1, min(4, int(self.settings.get("charactercount") or 1)))
        except (ValueError, TypeError):
            character_count = 1

        loop = asyncio.get_running_loop()
        font_path: Path | None = await loop.run_in_executor(
            None, self._get_font_path, True
        )

        # ── Plan scenes ───────────────────────────────────────────────────────
        await self._update_progress(20, "Planning illustrative scenes...")
        scenes = await self._plan_scenes(
            script,
            extra_context={
                "illustration_style": illustration_style,
                "character_count": character_count,
            },
        )
        if not scenes:
            scenes = [{
                "title":              self.job.title,
                "caption":            self.job.title,
                "narration":          script,
                "background_hint":    self.job.title,
                "character_position": "left",
                "duration_seconds":   10,
            }]

        # ── Download character images ─────────────────────────────────────────
        character_urls: list[str] = self.assets.get("character_urls", [])
        if isinstance(character_urls, str):
            character_urls = [character_urls]

        char_paths: list[Path | None] = []
        for ci, url in enumerate(character_urls[:character_count]):
            dest = self.tmp_dir / f"character_{ci}.png"
            try:
                await self._download_asset(url, dest, timeout_sec=30)
                char_paths.append(dest if dest.exists() else None)
            except Exception as exc:  # noqa: BLE001
                log.warning("illustrative_char_download", idx=ci, error=str(exc))
                char_paths.append(None)

        # ── Build scene data ──────────────────────────────────────────────────
        await self._update_progress(30, f"Building {len(scenes)} scenes...")
        scene_data: list[_SceneData] = []
        primary_rgb   = _hex_to_rgb(primary)
        secondary_rgb = _hex_to_rgb(secondary)

        for idx, scene in enumerate(scenes):
            title         = str(scene.get("title", ""))
            caption       = str(scene.get("caption", title))
            narration     = str(scene.get("narration", caption or script))
            bg_hint       = str(scene.get("background_hint", title or "educational"))
            char_position = str(scene.get("character_position", _DEFAULT_POSITION))
            pos_frac      = _POSITIONS.get(char_position, _POSITIONS[_DEFAULT_POSITION])

            char_path: Path | None = None
            if char_paths:
                char_path = char_paths[idx % len(char_paths)]

            # TTS
            audio_path = self.tmp_dir / f"scene_{idx}_audio.mp3"
            try:
                tts_dur  = await self._synthesize_tts(narration, audio_path)
                duration = max(_MIN_SCENE_DURATION, tts_dur)
            except Exception as exc:  # noqa: BLE001
                log.warning("illustrative_tts", scene=idx, error=str(exc))
                audio_path = None
                duration   = float(scene.get("duration_seconds", 10))

            # Background
            bg_path = await self._acquire_background(idx, bg_hint)

            # Pre-process assets into numpy arrays (blocking, in executor)
            scene_assets = await loop.run_in_executor(
                None,
                _prepare_scene_assets,
                bg_path, char_path, pos_frac, caption,
                w, h, primary_rgb, secondary_rgb, font_path,
            )

            scene_data.append(_SceneData(
                narration_audio=(
                    audio_path if (audio_path and audio_path.exists()) else None
                ),
                duration=duration,
                caption=caption,
                title=title,
                assets=scene_assets,
            ))

            pct = 30 + int(40 * (idx + 1) / len(scenes))
            await self._update_progress(pct, f"Scene {idx + 1}/{len(scenes)} ready")

        # ── Optional background music ─────────────────────────────────────────
        music_path: Path | None = None
        music_url = self.assets.get("music_url")
        if music_url:
            try:
                music_path = self.tmp_dir / "music.mp3"
                await self._download_asset(music_url, music_path)
            except Exception as exc:  # noqa: BLE001
                log.warning("illustrative_music_dl", error=str(exc))

        # ── Assemble ──────────────────────────────────────────────────────────
        await self._update_progress(72, "Assembling illustrative video...")
        output_path = self.tmp_dir / "raw.mp4"

        fn = functools.partial(
            _assemble_illustrative,
            scene_data=scene_data,
            music_path=music_path,
            music_volume=self._get_music_volume(),
            w=w, h=h,
            primary_rgb=primary_rgb,
            transition=self._get_transition(),
            tmp_dir=self.tmp_dir,
            output_path=output_path,
            fps=_FPS,
        )
        total_duration = await loop.run_in_executor(None, fn)

        await self._update_progress(75, "Illustrative render complete.")
        return RenderResult(
            raw_mp4_path=output_path,
            duration_seconds=total_duration,
            metadata={
                "scene_count":       len(scenes),
                "illustrationstyle": illustration_style,
                "charactercount":    character_count,
            },
        )

    async def _acquire_background(self, idx: int, query: str) -> Path | None:
        if not self.providers.stock:
            return None
        dest = self.tmp_dir / f"bg_{idx}.jpg"
        try:
            images = await self.providers.stock.search_images(
                query=query[:60], count=1, orientation="landscape"
            )
            if images:
                await self._download_asset(images[0].url, dest, timeout_sec=30)
                if dest.exists():
                    return dest
        except Exception as exc:  # noqa: BLE001
            log.warning("illustrative_bg_fetch", idx=idx, error=str(exc))
        return None


# ── Asset pre-processing (one scene, O(1 frame) RAM) ─────────────────────────

def _prepare_scene_assets(
    bg_path: Path | None,
    char_path: Path | None,
    pos_frac: tuple[float, float],
    caption: str,
    w: int,
    h: int,
    primary_rgb: tuple[int, int, int],
    secondary_rgb: tuple[int, int, int],
    font_path: Path | None,
) -> _SceneAssets:
    """
    Load + resize background and character into numpy arrays.
    Build cap_overlay (background + caption bar) as a numpy array.
    Returns _SceneAssets — no list of frames, just the source material.
    """
    from PIL import Image as PILImage, ImageDraw

    # ── Background ────────────────────────────────────────────────────────────
    if bg_path and bg_path.exists():
        try:
            bg = PILImage.open(str(bg_path)).convert("RGB")
            fill_scale = max(w / bg.width, h / bg.height)
            new_w = int(bg.width  * fill_scale)
            new_h = int(bg.height * fill_scale)
            bg    = bg.resize((new_w, new_h), PILImage.LANCZOS)
            left  = (new_w - w) // 2
            top   = (new_h - h) // 2
            bg    = bg.crop((left, top, left + w, top + h))
        except Exception as exc:  # noqa: BLE001
            log.warning("illustrative_bg_open", error=str(exc))
            bg = _gradient_bg(w, h, primary_rgb)
    else:
        bg = _gradient_bg(w, h, primary_rgb)

    bg_arr = np.array(bg, dtype=np.uint8)

    # ── Character ─────────────────────────────────────────────────────────────
    char_arr: np.ndarray | None = None
    char_x = char_y = char_w_px = char_h_px = 0

    if char_path and char_path.exists():
        try:
            char_img = PILImage.open(str(char_path)).convert("RGBA")
            char_h_px = int(h * _CHAR_HEIGHT_FRAC)
            ratio     = char_h_px / char_img.height
            char_w_px = int(char_img.width * ratio)
            char_img  = char_img.resize((char_w_px, char_h_px), PILImage.LANCZOS)
            char_arr  = np.array(char_img, dtype=np.uint8)
            cx_frac, cy_frac = pos_frac
            char_x    = int(w * cx_frac)
            char_y    = int(h * cy_frac)
        except Exception as exc:  # noqa: BLE001
            log.warning("illustrative_char_open", error=str(exc))
            char_arr = None

    # ── Caption overlay ───────────────────────────────────────────────────────
    cap_bar_h = int(h * 0.14)
    cap_bar_y = h - cap_bar_h

    # Pre-draw caption bar on a copy of the background (no character)
    cap_img  = PILImage.fromarray(bg_arr.copy())
    overlay  = PILImage.new("RGBA", (w, cap_bar_h), (10, 10, 10, 200))
    cap_rgba = cap_img.convert("RGBA")
    cap_rgba.paste(overlay, (0, cap_bar_y), overlay)
    cap_rgb  = cap_rgba.convert("RGB")

    # Draw text onto caption bar
    if caption:
        draw = ImageDraw.Draw(cap_rgb)
        font = _find_font(max(24, h // 22), font_path)
        text = caption[:140]
        try:
            tw = draw.textlength(text, font=font)
        except Exception:  # noqa: BLE001
            tw = len(text) * 10
        tx = max(20, int((w - tw) // 2))
        ty = cap_bar_y + max(4, cap_bar_h // 4)
        draw.text((tx, ty), text, font=font, fill=secondary_rgb)

    cap_overlay = np.array(cap_rgb, dtype=np.uint8)

    return _SceneAssets(
        bg_arr=bg_arr,
        char_arr=char_arr,
        char_x=char_x,
        char_y=char_y,
        cap_overlay=cap_overlay,
        cap_bar_y=cap_bar_y,
    )


def _gradient_bg(
    w: int, h: int, color: tuple[int, int, int]
):
    """Create a simple vertical gradient PIL Image as background fallback."""
    from PIL import Image as PILImage, ImageDraw
    img  = PILImage.new("RGB", (w, h), color)
    draw = ImageDraw.Draw(img)
    dark = tuple(max(0, int(c * 0.65)) for c in color)
    for y in range(h):
        t   = y / h
        row = tuple(int(color[i] * (1 - t) + dark[i] * t) for i in range(3))
        draw.line([(0, y), (w, y)], fill=row)  # type: ignore[arg-type]
    return img


# ── Per-frame on-demand compositor ───────────────────────────────────────────

def _make_frame_fn(sa: _SceneAssets, fps: int) -> Callable[[float], np.ndarray]:
    """
    Return make_frame(t) → H×W×3 numpy array.

    For each frame:
      1. Start with cap_overlay (background + caption bar, no character).
      2. If character exists, alpha-blend it at bob offset position.

    Memory: only 1 frame array created per call (+ two background references).
    """
    bg_arr      = sa.bg_arr          # H×W×3  — permanent background
    cap_overlay = sa.cap_overlay     # H×W×3  — bg + caption bar (no char)
    char_arr    = sa.char_arr        # char_h×char_w×4 or None
    base_cx     = sa.char_x
    base_cy     = sa.char_y
    cap_bar_y   = sa.cap_bar_y
    h, w        = bg_arr.shape[:2]

    if char_arr is None:
        # No character — return caption overlay directly (share, read-only safe)
        def make_frame_no_char(t: float) -> np.ndarray:
            return cap_overlay.copy()
        return make_frame_no_char

    char_h, char_w = char_arr.shape[:2]
    char_rgb   = char_arr[:, :, :3].astype(np.float32)
    char_alpha = (char_arr[:, :, 3] / 255.0).astype(np.float32)  # H×W

    def make_frame(t: float) -> np.ndarray:
        # Start from background (copy required — we write to it)
        frame = bg_arr.copy()

        # Bob offset
        bob_y  = int(_BOB_AMPLITUDE_PX * math.sin(2 * math.pi * _BOB_FREQ_HZ * t))
        cx     = max(0, min(base_cx,         w - char_w))
        cy     = max(0, min(base_cy + bob_y, h - char_h))

        # Slice region in frame
        r_y1, r_y2 = cy,        cy + char_h
        r_x1, r_x2 = cx,        cx + char_w
        # Clamp to frame bounds
        y1, y2 = max(0, r_y1), min(h, r_y2)
        x1, x2 = max(0, r_x1), min(w, r_x2)
        if y1 >= y2 or x1 >= x2:
            pass  # character off-screen
        else:
            cy_off = y1 - r_y1
            cx_off = x1 - r_x1
            ch     = y2 - y1
            cw     = x2 - x1

            bg_slice  = frame[y1:y2, x1:x2].astype(np.float32)      # ch×cw×3
            c_rgb     = char_rgb  [cy_off:cy_off+ch, cx_off:cx_off+cw]   # ch×cw×3
            c_alpha   = char_alpha[cy_off:cy_off+ch, cx_off:cx_off+cw]   # ch×cw
            alpha3    = c_alpha[:, :, np.newaxis]                         # ch×cw×1

            blended   = c_rgb * alpha3 + bg_slice * (1.0 - alpha3)
            frame[y1:y2, x1:x2] = blended.clip(0, 255).astype(np.uint8)

        # Paste caption bar from pre-drawn cap_overlay (bottom rows)
        frame[cap_bar_y:, :] = cap_overlay[cap_bar_y:, :]

        return frame

    return make_frame


# ── Assembly ──────────────────────────────────────────────────────────────────

def _assemble_illustrative(
    *,
    scene_data: list[_SceneData],
    music_path: Path | None,
    music_volume: float,
    w: int,
    h: int,
    primary_rgb: tuple[int, int, int],
    transition: str,
    tmp_dir: Path,
    output_path: Path,
    fps: int,
) -> float:
    from moviepy import VideoClip
    from moviepy import AudioFileClip, ColorClip, concatenate_videoclips
    from moviepy.audio.fx import MultiplyVolume
    from app.services.video import vfx_compat as vfx

    clips          = []
    total_duration = 0.0

    for sd in scene_data:
        d          = sd.duration
        total_duration += d

        make_frame = _make_frame_fn(sd.assets, fps)
        clip       = VideoClip(make_frame, duration=d)
        clip       = clip.with_fps(fps)

        if sd.narration_audio and sd.narration_audio.exists():
            try:
                narration = AudioFileClip(str(sd.narration_audio))
                if narration.duration > d:
                    narration = narration.subclipped(0, d)
                clip = clip.with_audio(narration)
            except Exception as exc:  # noqa: BLE001
                log.warning("illustrative_audio_attach", error=str(exc))

        if transition == "fade":
            clip = clip.with_effects([vfx.FadeIn(0.4), vfx.FadeOut(0.4)])

        clips.append(clip)

    if not clips:
        final          = ColorClip(size=(w, h), color=primary_rgb, duration=3.0)
        total_duration = 3.0
    else:
        final = concatenate_videoclips(clips, method="compose")

    if music_path and music_path.exists() and music_volume > 0:
        final = _overlay_music(final, music_path, music_volume, total_duration)

    _write(final, output_path, tmp_dir, fps)
    final.close()
    return total_duration


# ── Shared helpers ────────────────────────────────────────────────────────────

def _overlay_music(clip, music_path: Path, music_volume: float, duration: float):
    try:
        from moviepy import (
            AudioFileClip,
            CompositeAudioClip,
            concatenate_audioclips,
        )
        music = AudioFileClip(str(music_path)).with_effects([MultiplyVolume(music_volume)])
        if music.duration < duration:
            loops = int(duration / music.duration) + 1
            music = concatenate_audioclips([music] * loops)
        music    = music.subclipped(0, duration)
        existing = clip.audio
        if existing is not None:
            return clip.with_audio(CompositeAudioClip([existing, music]))
        return clip.with_audio(music)
    except Exception as exc:  # noqa: BLE001
        log.warning("illustrative_music_overlay", error=str(exc))
        return clip


def _find_font(size: int, font_path: Path | None = None):
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
