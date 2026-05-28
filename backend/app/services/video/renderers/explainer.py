"""
ExplainerRenderer — AI-illustrated explainer video.

Structure:
  - LLM breaks script into scenes (title, body_text, narration, image_prompt, image_style)
  - For each scene:
      1. Acquire image: ImageGenProvider → Pexels → solid brand color fallback
      2. TTS narration (edge-tts or configured provider)
      3. Pillow: title bar + body text overlay on image
  - Ken Burns zoom animation per scene
  - Crossfade transitions + optional background music
  - Scenes concatenated → raw MP4

ImageGen dependency:
  If providers.image_gen is configured (dalle3 / sdxl_local) images are generated
  from the LLM's image_prompt.  If not configured or the call fails, Pexels stock
  photos are fetched using the scene title as query.  If Pexels also fails, a solid
  brand-color background is used.

MoviePy: TextClip requires ImageMagick (apt-get install -y imagemagick).
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
_MIN_SCENE_DURATION = 4.0


@dataclass
class _SceneData:
    narration_audio: Path | None
    image_path: Path | None
    duration: float
    title: str
    body_text: str
    ken_burns: str   # zoom_in | zoom_out | pan_left | pan_right


class ExplainerRenderer(BaseVideoRenderer):
    """AI-illustrated explainer video with narration and text overlays."""

    async def render(self) -> RenderResult:
        script = self.job.script or self.job.title
        w, h = self._get_resolution()
        primary, secondary = self._get_brand_colors()

        # ── Resolve template-specific settings ────────────────────────────────
        animation_style: str = str(
            self.settings.get("animationstyle") or "character"
        ).lower()
        # Valid: character | infographic | problem_solution | social | data
        color_theme: str = str(self.settings.get("colortheme") or "").strip()
        # colortheme may provide an additional palette hint (e.g. "warm", "cool")

        overlay_opacity = self._get_overlay_opacity()
        transition_dur  = self._get_transition_duration()
        music_volume    = self._get_music_volume()

        # ── Plan scenes ───────────────────────────────────────────────────────
        await self._update_progress(20, "Planning explainer scenes...")
        scenes = await self._plan_scenes(script, extra_context={"animation_style": animation_style, "color_theme": color_theme})
        if not scenes:
            scenes = [{
                "title": self.job.title,
                "body_text": "",
                "narration": script,
                "image_prompt": self.job.title,
                "image_style": "flat illustration",
                "duration_seconds": 15,
            }]

        # ── Build each scene ──────────────────────────────────────────────────
        await self._update_progress(25, f"Building {len(scenes)} scenes...")
        scene_data: list[_SceneData] = []
        effects = ["zoom_in", "zoom_out", "pan_left", "pan_right"]

        for idx, scene in enumerate(scenes):
            title       = str(scene.get("title", ""))
            body_text   = str(scene.get("body_text", ""))
            narration   = str(scene.get("narration", script))
            image_prompt= str(scene.get("image_prompt", title or "educational concept"))
            image_style = str(scene.get("image_style", f"{animation_style} illustration"))
            ken_burns   = effects[idx % len(effects)]

            # TTS
            audio_path = self.tmp_dir / f"scene_{idx}_audio.mp3"
            try:
                tts_dur = await self._synthesize_tts(narration, audio_path)
                duration = max(_MIN_SCENE_DURATION, tts_dur)
            except Exception as exc:  # noqa: BLE001
                log.warning("explainer_tts_failed", scene=idx, error=str(exc))
                audio_path = None
                duration = float(scene.get("duration_seconds", 15))

            # Image: AI gen → Pexels → solid fallback
            image_path = await self._acquire_image(
                idx=idx,
                prompt=image_prompt,
                style=image_style,
                fallback_query=title or narration[:60],
            )

            scene_data.append(_SceneData(
                narration_audio=audio_path if (audio_path and audio_path.exists()) else None,
                image_path=image_path,
                duration=duration,
                title=title,
                body_text=body_text,
                ken_burns=ken_burns,
            ))

            pct = 25 + int(45 * (idx + 1) / len(scenes))
            await self._update_progress(pct, f"Scene {idx + 1}/{len(scenes)} ready")

        # ── Optional background music ─────────────────────────────────────────
        music_path: Path | None = None
        music_url = self.assets.get("music_url")
        if music_url:
            try:
                music_path = self.tmp_dir / "music.mp3"
                await self._download_asset(music_url, music_path)
            except Exception as exc:  # noqa: BLE001
                log.warning("explainer_music_failed", error=str(exc))

        # ── Assemble ──────────────────────────────────────────────────────────
        await self._update_progress(72, "Assembling explainer video...")
        output_path = self.tmp_dir / "raw.mp4"

        fn = functools.partial(
            _assemble_explainer,
            scene_data=scene_data,
            music_path=music_path,
            music_volume=self._get_music_volume(),
            w=w, h=h,
            primary_rgb=_hex_to_rgb(primary),
            text_color=secondary,
            transition=self._get_transition(),
            tmp_dir=self.tmp_dir,
            output_path=output_path,
            fps=_FPS,
        )
        loop = asyncio.get_running_loop()
        total_duration = await loop.run_in_executor(None, fn)

        await self._update_progress(75, "Explainer render complete.")
        return RenderResult(
            raw_mp4_path=output_path,
            duration_seconds=total_duration,
            metadata={"scene_count": len(scenes)},
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    # Cache the resolved character image across scenes so we only fetch once
    _character_image_cache: Path | None = None
    _character_image_resolved: bool = False

    async def _resolve_character_image(self) -> Path | None:
        """
        Resolve character_image_url from assets once and cache it.
        Supports:
          - http:// / https://  → download via httpx
          - file:///abs/path    → copy locally
          - /abs/path           → copy locally (shorthand)
        """
        if self._character_image_resolved:
            return self._character_image_cache

        self._character_image_resolved = True
        url: str = str(self.assets.get("character_image_url") or "").strip()
        if not url:
            return None

        dest = self.tmp_dir / "character_base.jpg"
        try:
            if url.startswith("http://") or url.startswith("https://"):
                await self._download_asset(url, dest, timeout_sec=30)
            else:
                # file:// or raw absolute path
                import shutil as _shutil
                src = url.removeprefix("file://")
                _shutil.copy2(src, dest)
            if dest.exists():
                log.info("explainer_character_image_resolved", path=str(dest))
                self._character_image_cache = dest
        except Exception as exc:  # noqa: BLE001
            log.warning("explainer_character_image_failed", url=url[:80], error=str(exc))

        return self._character_image_cache

    async def _acquire_image(
        self,
        idx: int,
        prompt: str,
        style: str,
        fallback_query: str,
    ) -> Path | None:
        """
        Resolution order:
          0. character_image_url from _resolved_assets  (reused for all scenes)
          1. AI image gen
          2. Pexels fallback
          3. None → solid brand color
        """
        # 0. Character image (same image for every scene)
        char_img = await self._resolve_character_image()
        if char_img:
            return char_img

        dest = self.tmp_dir / f"scene_{idx}_img.jpg"

        # 1. AI image gen
        if self.providers.image_gen:
            w, h = self._get_resolution()
            try:
                await self.providers.image_gen.generate(
                    prompt=prompt,
                    style=style,
                    width=w,
                    height=h,
                    output_path=dest,
                )
                if dest.exists():
                    return dest
            except Exception as exc:  # noqa: BLE001
                log.warning("explainer_image_gen_failed", idx=idx, error=str(exc))

        # 2. Pexels fallback
        if self.providers.stock:
            try:
                images = await self.providers.stock.search_images(
                    query=fallback_query[:60], count=1, orientation="landscape"
                )
                if images:
                    await self._download_asset(images[0].url, dest, timeout_sec=30)
                    if dest.exists():
                        return dest
            except Exception as exc:  # noqa: BLE001
                log.warning("explainer_pexels_fallback_failed", idx=idx, error=str(exc))

        return None   # Renderer will use solid brand color


# ── Synchronous MoviePy assembly ─────────────────────────────────────────────

def _assemble_explainer(
    *,
    scene_data: list[_SceneData],
    music_path: Path | None,
    music_volume: float,
    w: int,
    h: int,
    primary_rgb: tuple[int, int, int],
    text_color: str,
    transition: str,
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

    for sd in scene_data:
        d = sd.duration
        total_duration += d

        # ── Base layer: image with ken burns or solid color ───────────────────
        if sd.image_path and sd.image_path.exists():
            try:
                base = _ken_burns_clip(sd.image_path, d, sd.ken_burns, w, h)
            except Exception as exc:  # noqa: BLE001
                log.warning("explainer_ken_burns_failed", error=str(exc))
                base = ColorClip(size=(w, h), color=primary_rgb, duration=d)
        else:
            base = ColorClip(size=(w, h), color=primary_rgb, duration=d)

        layers = [base]

        # ── Text overlay: title bar + body text ───────────────────────────────
        if sd.title or sd.body_text:
            text_clips = _make_text_overlay(
                title=sd.title,
                body_text=sd.body_text,
                duration=d,
                w=w, h=h,
                text_color=text_color,
                primary_rgb=primary_rgb,
            )
            if text_clips:
                layers.extend(text_clips)

        scene_clip = CompositeVideoClip(layers, size=(w, h)).with_duration(d)

        # ── Narration audio ───────────────────────────────────────────────────
        if sd.narration_audio and sd.narration_audio.exists():
            try:
                narration = AudioFileClip(str(sd.narration_audio))
                if narration.duration > d:
                    narration = narration.subclipped(0, d)
                scene_clip = scene_clip.with_audio(narration)
            except Exception as exc:  # noqa: BLE001
                log.warning("explainer_audio_failed", error=str(exc))

        # ── Transition ────────────────────────────────────────────────────────
        if transition == "fade":
            scene_clip = scene_clip.with_effects([vfx.FadeIn(0.35), vfx.FadeOut(0.35)])

        clips.append(scene_clip)

    if not clips:
        final = ColorClip(size=(w, h), color=(0, 0, 0), duration=3.0)
        total_duration = 3.0
    else:
        final = concatenate_videoclips(clips, method="compose")

    if music_path and music_path.exists() and music_volume > 0:
        final = _overlay_music(final, music_path, music_volume, total_duration)

    _write(final, output_path, tmp_dir, fps)
    final.close()
    return total_duration


def _ken_burns_clip(img_path: Path, duration: float, effect: str, w: int, h: int):
    """Ken Burns zoom/pan animation for a still image."""
    import numpy as np
    from PIL import Image as PILImage
    from moviepy import VideoClip

    pil_img = PILImage.open(str(img_path)).convert("RGB")
    fill_scale = max(w / pil_img.width, h / pil_img.height)
    buffer = 1.15
    scaled_w = int(pil_img.width  * fill_scale * buffer)
    scaled_h = int(pil_img.height * fill_scale * buffer)
    pil_img = pil_img.resize((scaled_w, scaled_h), PILImage.LANCZOS)
    base = np.array(pil_img)
    bh, bw = base.shape[:2]

    def make_frame(t: float) -> np.ndarray:
        progress = min(1.0, t / max(0.001, duration))
        if effect == "zoom_in":
            zoom = 1.0 + 0.10 * progress
        elif effect == "zoom_out":
            zoom = 1.10 - 0.10 * progress
        elif effect == "pan_left":
            zoom = 1.05
        elif effect == "pan_right":
            zoom = 1.05
        else:
            zoom = 1.05

        vis_w = int(w / zoom)
        vis_h = int(h / zoom)

        if effect == "pan_left":
            cx = int(bw / 2 + (bw - w) * 0.15 * (1 - progress))
        elif effect == "pan_right":
            cx = int(bw / 2 - (bw - w) * 0.15 * (1 - progress))
        else:
            cx = bw // 2

        cy = bh // 2
        x0 = max(0, cx - vis_w // 2)
        y0 = max(0, cy - vis_h // 2)
        x1 = min(bw, x0 + vis_w)
        y1 = min(bh, y0 + vis_h)
        crop = base[y0:y1, x0:x1]
        if crop.shape[1] != w or crop.shape[0] != h:
            crop = np.array(PILImage.fromarray(crop).resize((w, h), PILImage.BILINEAR))
        return crop

    clip = VideoClip(make_frame, duration=duration)
    clip.fps = _FPS
    return clip


def _make_text_overlay(
    title: str,
    body_text: str,
    duration: float,
    w: int,
    h: int,
    text_color: str,
    primary_rgb: tuple[int, int, int],
) -> "list | None":
    """
    Create title bar (top 18% of frame) + body text below title.
    Returns [bar, title_clip, body_clip] for direct extension into layers list.
    """
    try:
        from moviepy import ColorClip, TextClip
        from app.services.video import vfx_compat as vfx

        clips = []

        if title:
            bar_h = max(70, h // 7)
            bar = (ColorClip(size=(w, bar_h), color=primary_rgb)
                   .with_opacity(0.85)
                   .with_duration(duration)
                   .with_position(("center", 0)))
            clips.append(bar)

            title_clip = (TextClip(
                text=title[:80],
                font_size=max(24, bar_h // 2),
                color=_normalize_color(text_color),
                size=(w - 60, None),
                method="caption",
                text_align="center",
            ).with_duration(duration)
             .with_position(("center", bar_h // 4))
             .with_effects([vfx.FadeIn(0.3)]))
            clips.append(title_clip)

        if body_text:
            body_bar_h = min(h // 4, 200)
            body_bar = (ColorClip(size=(w, body_bar_h), color=(10, 10, 10))
                        .with_opacity(0.70)
                        .with_duration(duration)
                        .with_position(("center", h - body_bar_h)))
            clips.append(body_bar)

            body_clip = (TextClip(
                text=body_text[:200],
                font_size=max(18, h // 30),
                color=_normalize_color(text_color),
                size=(w - 80, None),
                method="caption",
                text_align="left",
            ).with_duration(duration)
             .with_position((40, h - body_bar_h + 10))
             .with_effects([vfx.FadeIn(0.4)]))
            clips.append(body_clip)

        return clips if clips else None

    except Exception as exc:  # noqa: BLE001
        log.warning("explainer_text_overlay_failed", error=str(exc))
        return None


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
        log.warning("explainer_music_overlay_failed", error=str(exc))
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
