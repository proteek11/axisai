"""
KineticRenderer — animated kinetic typography video.

Structure:
  - Solid background (template bgcolor or brand primary colour)
  - LLM breaks script into short phrases
  - Each phrase animates with the configured text animation style
  - TTS narration plays throughout

Template settings consumed
--------------------------
  bgcolor          — background colour hex (overrides primarycolor for BG)
  primarycolor     — fallback background colour if bgcolor not set
  accentcolor      — text colour
  textanimation    — "slam" | "lyric" | "float" | "typewriter" | "countdown"
                     (mapped to MoviePy effects)
  wordspacing      — extra horizontal letter spacing (0–20 px, cosmetic hint)
  fontfamily       — TTF font name (downloaded via _get_font_path if Google Font)
  aspectratio      — "16:9" | "9:16" | "1:1" | "4:3"
  resolution       — "720p" | "1080p" | "4k"
  bgmvolume        — background music volume (0-1)
  voicevolume      — narration voice volume (0-1)
  transition       — "fade" etc.
  transitionduration — seconds

MoviePy dependency: requires ImageMagick for TextClip.
  Install: apt-get install -y imagemagick
"""
from __future__ import annotations

import asyncio
import functools
from pathlib import Path

import structlog

from app.services.video import RenderResult
from app.services.video.base_renderer import BaseVideoRenderer

log = structlog.get_logger(__name__)

_FPS = 24

# textanimation template value → internal effect name used by _make_text_clip
_ANIMATION_MAP: dict[str, str] = {
    "slam":        "zoomin",
    "lyric":       "fadein",
    "float":       "slideup",
    "typewriter":  "typewriter",
    "countdown":   "fadein",   # Phase 2: implement countdown overlays
    # Pass-through aliases (already in internal format)
    "fadein":      "fadein",
    "zoomin":      "zoomin",
    "slideup":     "slideup",
}

_DEFAULT_ANIMATION = "fadein"


class KineticRenderer(BaseVideoRenderer):
    """Kinetic typography: animated text phrases over a configurable background."""

    async def render(self) -> RenderResult:
        script = self.job.script or self.job.title
        w, h = self._get_resolution()
        primary, secondary = self._get_brand_colors()

        # ── Resolve template-specific settings ────────────────────────────────
        # bgcolor overrides primarycolor specifically for the BG layer
        bg_color_hex: str = (
            str(self.settings.get("bgcolor") or "").strip() or primary
        )
        text_color_hex: str = secondary if secondary.startswith("#") else "#FFFFFF"

        # textanimation from template → internal effect
        raw_animation: str = str(
            self.settings.get("textanimation") or _DEFAULT_ANIMATION
        ).lower()
        default_effect: str = _ANIMATION_MAP.get(raw_animation, _DEFAULT_ANIMATION)

        # wordspacing: 0–20 extra pixels (used as cosmetic hint for fontsize scaling)
        try:
            word_spacing = max(0, min(20, int(self.settings.get("wordspacing") or 0)))
        except (ValueError, TypeError):
            word_spacing = 0

        # Font resolution — try template fontfamily via _get_font_path
        loop = asyncio.get_running_loop()
        font_path: Path | None = await loop.run_in_executor(
            None, self._get_font_path, True
        )
        font_name_for_moviepy: str = font_path.stem if font_path else "DejaVu-Sans-Bold"

        transition_dur = self._get_transition_duration()
        music_volume   = self._get_music_volume()
        voice_volume   = self._get_voice_volume()

        # ── Phase 1: plan phrases ─────────────────────────────────────────────
        await self._update_progress(20, "Planning kinetic phrases...")
        phrases = await self._plan_scenes(script)
        if not phrases:
            phrases = [{"text": script, "effect": default_effect, "duration": 5}]

        # Apply template default_effect to phrases that don't specify one
        for p in phrases:
            if not p.get("effect"):
                p["effect"] = default_effect
            else:
                raw_p = str(p["effect"]).lower()
                p["effect"] = _ANIMATION_MAP.get(raw_p, default_effect)

        # ── Phase 2: synthesize narration ─────────────────────────────────────
        await self._update_progress(35, "Synthesizing narration...")
        audio_path = self.tmp_dir / "narration.mp3"
        try:
            tts_duration = await self._synthesize_tts(script, audio_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("kinetic_tts_failed", error=str(exc))
            tts_duration = 0.0
        if tts_duration <= 0:
            tts_duration = sum(float(p.get("duration", 3)) for p in phrases)

        # ── Phase 3: optional background music ───────────────────────────────
        music_url = self.assets.get("music_url") or self.assets.get("kinetic_music_url")
        music_path: Path | None = None
        if music_url:
            try:
                music_path = self.tmp_dir / "music.mp3"
                await self._download_asset(music_url, music_path)
            except Exception as exc:  # noqa: BLE001
                log.warning("kinetic_music_download_failed", error=str(exc))
                music_path = None

        # ── Phase 4: assemble video ───────────────────────────────────────────
        await self._update_progress(50, "Building kinetic text animation...")
        output_path = self.tmp_dir / "raw.mp4"

        fn = functools.partial(
            _assemble_kinetic,
            phrases=phrases,
            audio_path=audio_path if audio_path.exists() else None,
            music_path=music_path,
            tts_duration=tts_duration,
            music_volume=music_volume,
            voice_volume=voice_volume,
            w=w, h=h,
            bg_color_hex=bg_color_hex,
            text_color_hex=text_color_hex,
            font_name=font_name_for_moviepy,
            word_spacing=word_spacing,
            transition_dur=transition_dur,
            tmp_dir=self.tmp_dir,
            output_path=output_path,
            fps=_FPS,
        )
        duration = await loop.run_in_executor(None, fn)

        await self._update_progress(75, "Kinetic render complete.")
        return RenderResult(
            raw_mp4_path=output_path,
            duration_seconds=duration,
            metadata={
                "phrase_count": len(phrases),
                "textanimation": raw_animation,
                "bgcolor": bg_color_hex,
            },
        )


# ── Synchronous MoviePy assembly (runs in thread executor) ───────────────────

def _assemble_kinetic(
    *,
    phrases: list[dict],
    audio_path: Path | None,
    music_path: Path | None,
    tts_duration: float,
    music_volume: float,
    voice_volume: float,
    w: int,
    h: int,
    bg_color_hex: str,
    text_color_hex: str,
    font_name: str,
    word_spacing: int,
    transition_dur: float,
    tmp_dir: Path,
    output_path: Path,
    fps: int,
) -> float:
    from moviepy import (
        AudioFileClip,
        ColorClip,
        CompositeVideoClip,
        TextClip,
    )
    from app.services.video import vfx_compat as vfx

    total_duration = max(tts_duration, sum(float(p.get("duration", 3)) for p in phrases))
    bg_rgb = _hex_to_rgb(bg_color_hex)
    bg = ColorClip(size=(w, h), color=bg_rgb, duration=total_duration)

    # Adjust fontsize slightly by word_spacing (cosmetic spacing hint)
    # h//14 ≈ 77px at 1080p — large enough to read, small enough not to overflow
    base_fontsize = max(28, h // 14)
    fontsize = base_fontsize + word_spacing

    text_clips = []
    t_cursor = 0.0
    for phrase in phrases:
        text   = str(phrase.get("text", "")).strip()
        d      = float(phrase.get("duration", 3))
        effect = str(phrase.get("effect", "fadein"))
        if not text:
            t_cursor += d
            continue

        try:
            txt = _make_text_clip(
                text, d, w, h, text_color_hex, font_name, effect,
                fontsize=fontsize, transition_dur=transition_dur,
            )
            txt = txt.with_start(t_cursor).with_position("center")
            text_clips.append(txt)
        except Exception as exc:  # noqa: BLE001
            log.warning("kinetic_text_clip_failed", text=text[:40], error=str(exc))

        t_cursor += d

    layers = [bg] + text_clips
    final = CompositeVideoClip(layers, size=(w, h)).with_duration(total_duration)

    # ── Audio ─────────────────────────────────────────────────────────────────
    final = _apply_audio(
        final, audio_path, music_path,
        music_volume=music_volume, voice_volume=voice_volume,
        duration=total_duration, tmp_dir=tmp_dir,
    )

    _write(final, output_path, tmp_dir, fps)
    final.close()
    return total_duration


def _make_text_clip(
    text: str,
    duration: float,
    w: int,
    h: int,
    color_hex: str,
    font_name: str,
    effect: str,
    fontsize: int = 72,
    transition_dur: float = 0.35,
) -> "TextClip":  # type: ignore[name-defined]
    from moviepy import TextClip
    from app.services.video import vfx_compat as vfx

    color_str = _hex_to_moviepy_color(color_hex)
    fade = min(transition_dur, duration * 0.25)

    # Try requested font → DejaVu-Sans-Bold → no-font fallback
    for font_try in (font_name, "DejaVu-Sans-Bold", None):
        try:
            kw: dict = dict(
                text=text,
                font_size=fontsize,
                color=color_str,
                size=(w - 120, h - 120),
                method="caption",
                text_align="center",
            )
            if font_try:
                kw["font"] = font_try
            clip = TextClip(**kw).with_duration(duration)
            break
        except Exception:  # noqa: BLE001
            if font_try is None:
                raise
            continue

    if effect == "zoomin":   # "slam" in templates
        clip = clip.resized(
            lambda t, d=duration: min(1.0, 0.4 + 0.6 * (t / max(0.01, d * 0.4)))
        )
        clip = clip.with_effects([vfx.FadeOut(fade)])

    elif effect == "slideup":   # "float" in templates
        start_y = h + 50
        mid_y   = h // 2
        clip = clip.with_position(
            lambda t, d=duration, sy=start_y, my=mid_y: (
                "center",
                max(my, sy - int((sy - my) * min(1.0, t / max(0.01, d * 0.4)))),
            )
        )
        clip = clip.with_effects([vfx.FadeOut(fade)])

    else:  # fadein (lyric, typewriter placeholder, countdown placeholder)
        clip = clip.with_effects([vfx.FadeIn(fade), vfx.FadeOut(fade)])

    return clip


# ── Shared audio / write helpers ─────────────────────────────────────────────

def _apply_audio(
    clip,
    audio_path: Path | None,
    music_path: Path | None,
    *,
    music_volume: float,
    voice_volume: float,
    duration: float,
    tmp_dir: Path,
):
    from moviepy import AudioFileClip, CompositeAudioClip, concatenate_audioclips
    from moviepy.audio.fx import MultiplyVolume

    audio_tracks = []

    if audio_path and audio_path.exists():
        narration = AudioFileClip(str(audio_path))
        if narration.duration > duration:
            narration = narration.subclipped(0, duration)
        if voice_volume < 1.0:
            narration = narration.with_effects([MultiplyVolume(voice_volume)])
        audio_tracks.append(narration)

    if music_path and music_path.exists() and music_volume > 0:
        try:
            music = AudioFileClip(str(music_path)).with_effects([MultiplyVolume(music_volume)])
            if music.duration < duration:
                loops = int(duration / music.duration) + 1
                music = concatenate_audioclips([music] * loops)
            music = music.subclipped(0, duration)
            audio_tracks.append(music)
        except Exception as exc:  # noqa: BLE001
            log.warning("music_overlay_failed", error=str(exc))

    if not audio_tracks:
        return clip
    if len(audio_tracks) == 1:
        return clip.with_audio(audio_tracks[0])
    return clip.with_audio(CompositeAudioClip(audio_tracks))


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


def _hex_to_moviepy_color(hex_color: str) -> str:
    """Convert hex to 'rgb(R,G,B)' string accepted by MoviePy TextClip."""
    r, g, b = _hex_to_rgb(hex_color)
    return f"rgb({r},{g},{b})"


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
