"""
StockFootageRenderer — narrated stock video footage.

Structure:
  - LLM breaks script into scenes with search keywords and duration hints
  - For each scene: Pexels video clip → trim/loop to narration length → TTS overlay
  - Scenes concatenated with optional fade transitions
  - Optional: scene title lower-third overlay
  - Optional: background music mixed under narration

Pexels dependency: requires VIDEO_PEXELS_API_KEY env var.
MoviePy: TextClip requires ImageMagick if titles are enabled.
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
_MIN_SCENE_DURATION = 4.0


@dataclass
class _SceneData:
    narration_audio: Path | None
    video_clip_path: Path | None
    duration: float
    title: str
    keywords: list[str] = field(default_factory=list)


class StockFootageRenderer(BaseVideoRenderer):
    """Stock footage video: narrated Pexels clips assembled into a complete video."""

    async def render(self) -> RenderResult:
        script = self.job.script or self.job.title
        w, h = self._get_resolution()

        # ── Plan scenes ───────────────────────────────────────────────────────
        await self._update_progress(20, "Planning scenes...")
        scenes = await self._plan_scenes(script)
        if not scenes:
            scenes = [{
                "title": self.job.title,
                "narration": script,
                "search_keywords": [self.job.title],
                "duration_seconds": 30,
            }]

        # ── Build each scene: TTS + Pexels video ──────────────────────────────
        await self._update_progress(30, f"Processing {len(scenes)} scenes...")
        scene_data: list[_SceneData] = []

        for idx, scene in enumerate(scenes):
            narration = str(scene.get("narration", ""))
            title = str(scene.get("title", ""))
            keywords: list[str] = scene.get("search_keywords", [title or "nature"])
            planned_duration = float(scene.get("duration_seconds", 15))

            # TTS narration
            audio_path: Path | None = None
            tts_duration = planned_duration
            if narration.strip():
                audio_path = self.tmp_dir / f"scene_{idx}_audio.mp3"
                try:
                    tts_duration = await self._synthesize_tts(narration, audio_path)
                    tts_duration = max(_MIN_SCENE_DURATION, tts_duration)
                except Exception as exc:  # noqa: BLE001
                    log.warning("stockfootage_tts_failed", scene=idx, error=str(exc))
                    audio_path = None
                    tts_duration = planned_duration

            # Pexels video — try each keyword until we find a clip
            video_path: Path | None = None
            if self.providers.stock:
                for kw in keywords[:3]:
                    try:
                        clips = await self.providers.stock.search_videos(
                            query=kw,
                            count=1,
                            min_duration_sec=int(_MIN_SCENE_DURATION),
                            max_duration_sec=int(tts_duration * 3),
                        )
                        if clips:
                            video_path = self.tmp_dir / f"scene_{idx}_clip.mp4"
                            await self._download_asset(
                                clips[0].url, video_path, timeout_sec=120
                            )
                            break
                    except Exception as exc:  # noqa: BLE001
                        log.warning("stockfootage_clip_download_failed",
                                    scene=idx, kw=kw, error=str(exc))

            scene_data.append(_SceneData(
                narration_audio=audio_path if (audio_path and audio_path.exists()) else None,
                video_clip_path=video_path if (video_path and video_path.exists()) else None,
                duration=tts_duration,
                title=title,
                keywords=keywords,
            ))

            pct = 30 + int(40 * (idx + 1) / len(scenes))
            await self._update_progress(pct, f"Scene {idx+1}/{len(scenes)} ready")

        # ── Optional background music ─────────────────────────────────────────
        music_url = self.assets.get("music_url")
        music_path: Path | None = None
        if music_url:
            try:
                music_path = self.tmp_dir / "music.mp3"
                await self._download_asset(music_url, music_path)
            except Exception as exc:  # noqa: BLE001
                log.warning("stockfootage_music_failed", error=str(exc))

        # ── Assemble in executor ──────────────────────────────────────────────
        await self._update_progress(72, "Assembling stock footage video...")
        output_path = self.tmp_dir / "raw.mp4"

        fn = functools.partial(
            _assemble_stockfootage,
            scene_data=scene_data,
            music_path=music_path,
            music_volume=self._get_music_volume(),
            w=w, h=h,
            primary_rgb=_hex_to_rgb(self._get_brand_colors()[0]),
            text_color=self._get_brand_colors()[1],
            transition=self._get_transition(),
            tmp_dir=self.tmp_dir,
            output_path=output_path,
            fps=_FPS,
        )
        loop = asyncio.get_running_loop()
        total_duration = await loop.run_in_executor(None, fn)

        await self._update_progress(75, "Stock footage render complete.")
        return RenderResult(
            raw_mp4_path=output_path,
            duration_seconds=total_duration,
            metadata={"scene_count": len(scenes)},
        )


# ── Synchronous MoviePy assembly ─────────────────────────────────────────────

def _assemble_stockfootage(
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
        VideoFileClip,
        concatenate_videoclips,
    )
    from app.services.video import vfx_compat as vfx

    clips = []
    total_duration = 0.0

    for sd in scene_data:
        d = sd.duration
        total_duration += d

        # ── Video base layer ──────────────────────────────────────────────────
        if sd.video_clip_path and sd.video_clip_path.exists():
            try:
                raw = VideoFileClip(str(sd.video_clip_path)).without_audio()
                # Trim or loop to exact narration duration
                if raw.duration >= d:
                    base = raw.subclipped(0, d)
                else:
                    loops = int(d / raw.duration) + 1
                    looped = concatenate_videoclips([raw] * loops)
                    base = looped.subclipped(0, d)
                # Resize to target resolution (preserve aspect ratio, letterbox)
                base = _resize_fill(base, w, h)
            except Exception as exc:  # noqa: BLE001
                log.warning("stockfootage_clip_load_failed",
                            path=str(sd.video_clip_path), error=str(exc))
                base = ColorClip(size=(w, h), color=primary_rgb, duration=d)
        else:
            base = ColorClip(size=(w, h), color=primary_rgb, duration=d)

        layers = [base]

        # ── Scene title lower-third ───────────────────────────────────────────
        if sd.title.strip():
            title_clips = _make_lower_third(sd.title, min(d, 3.0), w, h, text_color)
            if title_clips:
                layers.extend(title_clips)

        scene_clip = CompositeVideoClip(layers, size=(w, h)).with_duration(d)

        # ── Narration audio ───────────────────────────────────────────────────
        if sd.narration_audio and sd.narration_audio.exists():
            try:
                narration = AudioFileClip(str(sd.narration_audio))
                if narration.duration > d:
                    narration = narration.subclipped(0, d)
                scene_clip = scene_clip.with_audio(narration)
            except Exception as exc:  # noqa: BLE001
                log.warning("stockfootage_audio_failed", error=str(exc))

        # ── Transition ────────────────────────────────────────────────────────
        if transition == "fade":
            scene_clip = scene_clip.with_effects([vfx.FadeIn(0.4), vfx.FadeOut(0.4)])

        clips.append(scene_clip)

    if not clips:
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


def _resize_fill(clip, w: int, h: int):
    """Resize clip to fill (w, h), center-cropping if aspect ratio differs."""
    clip_w, clip_h = clip.size
    scale = max(w / clip_w, h / clip_h)
    new_w = int(clip_w * scale)
    new_h = int(clip_h * scale)
    resized = clip.resized((new_w, new_h))
    if new_w == w and new_h == h:
        return resized
    # Crop center to exact target
    x = (new_w - w) // 2
    y = (new_h - h) // 2
    return resized.cropped(x1=x, y1=y, x2=x + w, y2=y + h)


def _make_lower_third(
    title: str,
    duration: float,
    w: int,
    h: int,
    text_color: str,
) -> "list | None":
    """
    Create lower-third overlay clips: a semi-transparent bar + title text.

    Returns [bar_clip, txt_clip] for direct insertion into a layers list.
    Returns None on failure (e.g. ImageMagick not installed).

    Fades are applied individually to each clip.
    """
    try:
        from moviepy import ColorClip, TextClip
        from app.services.video import vfx_compat as vfx

        bar_h = max(50, h // 12)
        y_pos = int(h * 0.78)
        bar = (ColorClip(size=(w, bar_h), color=(0, 0, 0))
               .with_opacity(0.65)
               .with_duration(duration)
               .with_position(("center", y_pos))
               .with_effects([vfx.FadeIn(0.3)])
               .with_effects([vfx.FadeOut(0.3)]))

        txt = (TextClip(
            text=title[:80],
            font_size=max(18, bar_h // 2),
            color=_normalize_color(text_color),
            size=(w - 60, None),
            method="caption",
            text_align="center",
        ).with_duration(duration)
         .with_position(("center", y_pos + 6))
         .with_effects([vfx.FadeIn(0.3)])
         .with_effects([vfx.FadeOut(0.3)]))

        return [bar, txt]

    except Exception as exc:  # noqa: BLE001
        log.warning("lower_third_failed", title=title[:40], error=str(exc))
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
