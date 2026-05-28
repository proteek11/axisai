"""
ConversationalRenderer — 2-3 character scripted dialogue video.

Structure:
  - LLM breaks script into turns (who speaks, what they say, voice hint)
  - Characters A (left) and B (right) take turns speaking
  - Active speaker: slightly larger, speech bubble above head
  - Inactive speaker: slightly dimmed, neutral pose
  - TTS voice switches per character (voice_map in settings or auto-assigned)
  - Caption bar at bottom showing current text
  - Optional background image/colour behind both characters
  - Fade transitions between scenes; continuous narration track

Character images:
  Expects PNG with transparency (RGBA).
  character_urls from _resolved_assets: ["url_char_A", "url_char_B", ...]
  If none, Pillow silhouettes are drawn as placeholders.

Template settings consumed
--------------------------
  primarycolor / accentcolor — brand colours
  fontfamily                 — caption font
  bgmvolume / voicevolume    — volume levels
  aspectratio / resolution   — output dimensions
  overlayopacity             — caption bar opacity
  transitionduration         — fade between turns
  # Type-specific
  voice_a / voice_b / voice_c — TTS voice IDs per character
  character_names             — comma-separated names (e.g. "Alex,Jamie")
  show_names                  — bool: show character names above heads
"""
from __future__ import annotations

import asyncio
import functools
import math
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from app.services.video import RenderResult
from app.services.video.base_renderer import BaseVideoRenderer

log = structlog.get_logger(__name__)

_FPS = 24
_MIN_TURN_DURATION = 2.0

# Active-speaker scale vs inactive
_ACTIVE_SCALE   = 1.0
_INACTIVE_SCALE = 0.80
_INACTIVE_DIM   = 0.55   # brightness factor for inactive characters

# Silhouette colours when no character image available
_SILHOUETTE_COLORS = [
    (60, 120, 200),    # blue — character A
    (200, 80, 60),     # red  — character B
    (60, 180, 120),    # green — character C
]

# Character positions as x-fraction of canvas (character centred around this x)
_CHAR_X_FRACS = [0.22, 0.78, 0.50]   # A=left, B=right, C=centre

# Bob animation
_BOB_AMPLITUDE_PX = 5
_BOB_FREQ_HZ = 0.8


@dataclass
class _TurnData:
    character_index: int
    character_name: str
    text: str
    narration_audio: Path | None
    duration: float


@dataclass
class _SceneCache:
    """Pre-rendered numpy frame array for a single animation frame."""
    frames: list  # list of numpy uint8 arrays  (h, w, 3)
    duration: float
    character_index: int


class ConversationalRenderer(BaseVideoRenderer):
    """Two-character scripted dialogue video with speech turns and captions."""

    async def render(self) -> RenderResult:
        script = self.job.script or self.job.title
        w, h = self._get_resolution()
        primary, secondary = self._get_brand_colors()

        # ── Resolve template-specific settings ────────────────────────────────
        # Per-character voice overrides
        voice_a: str | None = self.settings.get("voice_a") or self.settings.get("voice")
        voice_b: str | None = self.settings.get("voice_b") or None
        voice_c: str | None = self.settings.get("voice_c") or None
        voices = [voice_a, voice_b, voice_c]

        # Character names
        raw_names = str(self.settings.get("character_names") or "Alex,Jamie").split(",")
        char_names = [n.strip() for n in raw_names][:3]
        while len(char_names) < 3:
            char_names.append(f"Character {len(char_names) + 1}")

        show_names: bool   = _truthy(self.settings.get("show_names", True))
        overlay_opacity    = self._get_overlay_opacity()
        transition_dur     = self._get_transition_duration()
        music_volume       = self._get_music_volume()
        voice_volume       = self._get_voice_volume()

        loop = asyncio.get_running_loop()
        font_path: Path | None = await loop.run_in_executor(
            None, self._get_font_path, True
        )

        # ── Download character images ─────────────────────────────────────────
        char_urls: list[str] = self.assets.get("character_urls", [])
        if isinstance(char_urls, str):
            char_urls = [char_urls]

        char_paths: list[Path | None] = []
        for ci, url in enumerate(char_urls[:3]):
            dest = self.tmp_dir / f"char_{ci}.png"
            try:
                await self._download_asset(url, dest, timeout_sec=30)
                char_paths.append(dest if dest.exists() else None)
            except Exception as exc:  # noqa: BLE001
                log.warning("conversational_char_download_failed", ci=ci, error=str(exc))
                char_paths.append(None)
        while len(char_paths) < 3:
            char_paths.append(None)

        # ── Optional background ───────────────────────────────────────────────
        bg_path: Path | None = None
        bg_url = self.assets.get("background_url") or self.assets.get("background_value")
        if bg_url and bg_url.startswith("http"):
            try:
                bg_path = self.tmp_dir / "background.jpg"
                await self._download_asset(bg_url, bg_path, timeout_sec=30)
                if not bg_path.exists():
                    bg_path = None
            except Exception as exc:  # noqa: BLE001
                log.warning("conversational_bg_download_failed", error=str(exc))

        # ── Plan turns ────────────────────────────────────────────────────────
        await self._update_progress(20, "Planning conversation turns...")
        turns_raw = await self._plan_scenes(
            script,
            extra_context={
                "character_names": char_names,
                "num_characters": min(2, len(char_urls) if char_urls else 2),
            },
        )
        if not turns_raw:
            turns_raw = [
                {"character": char_names[0], "character_index": 0,
                 "text": script, "duration_seconds": 10},
            ]

        # ── Build each turn: TTS + frames ─────────────────────────────────────
        await self._update_progress(30, f"Building {len(turns_raw)} dialogue turns...")
        turn_data: list[_TurnData] = []

        for idx, turn in enumerate(turns_raw):
            char_idx  = int(turn.get("character_index", 0)) % 3
            char_name = char_names[char_idx]
            text      = str(turn.get("text", turn.get("narration", "")))
            voice     = voices[char_idx]

            audio_path = self.tmp_dir / f"turn_{idx}_audio.mp3"
            try:
                tts_dur = await self._synthesize_tts(text, audio_path, voice=voice)
                duration = max(_MIN_TURN_DURATION, tts_dur)
            except Exception as exc:  # noqa: BLE001
                log.warning("conversational_tts_failed", idx=idx, error=str(exc))
                audio_path = None
                duration = float(turn.get("duration_seconds", 5))

            turn_data.append(_TurnData(
                character_index=char_idx,
                character_name=char_name,
                text=text,
                narration_audio=audio_path if (audio_path and audio_path.exists()) else None,
                duration=duration,
            ))

            pct = 30 + int(35 * (idx + 1) / len(turns_raw))
            await self._update_progress(pct, f"Turn {idx + 1}/{len(turns_raw)} ready")

        # ── Optional background music ─────────────────────────────────────────
        music_path: Path | None = None
        music_url = self.assets.get("music_url")
        if music_url:
            try:
                music_path = self.tmp_dir / "music.mp3"
                await self._download_asset(music_url, music_path)
            except Exception as exc:  # noqa: BLE001
                log.warning("conversational_music_failed", error=str(exc))

        # ── Assemble ──────────────────────────────────────────────────────────
        await self._update_progress(68, "Assembling dialogue video...")
        output_path = self.tmp_dir / "raw.mp4"

        fn = functools.partial(
            _assemble_conversational,
            turn_data=turn_data,
            char_paths=char_paths,
            char_names=char_names,
            bg_path=bg_path,
            music_path=music_path,
            music_volume=music_volume,
            voice_volume=voice_volume,
            w=w, h=h,
            primary_hex=primary,
            secondary_hex=secondary,
            font_path=font_path,
            show_names=show_names,
            overlay_opacity=overlay_opacity,
            transition_dur=transition_dur,
            tmp_dir=self.tmp_dir,
            output_path=output_path,
            fps=_FPS,
        )
        total_duration = await loop.run_in_executor(None, fn)

        await self._update_progress(75, "Conversational render complete.")
        return RenderResult(
            raw_mp4_path=output_path,
            duration_seconds=total_duration,
            metadata={
                "turn_count": len(turn_data),
                "character_names": char_names[:2],
                "show_names": show_names,
            },
        )


# ── Synchronous assembly (runs in executor) ───────────────────────────────────

def _assemble_conversational(
    *,
    turn_data: list[_TurnData],
    char_paths: list[Path | None],
    char_names: list[str],
    bg_path: Path | None,
    music_path: Path | None,
    music_volume: float,
    voice_volume: float,
    w: int,
    h: int,
    primary_hex: str,
    secondary_hex: str,
    font_path: Path | None,
    show_names: bool,
    overlay_opacity: float,
    transition_dur: float,
    tmp_dir: Path,
    output_path: Path,
    fps: int,
) -> float:
    import numpy as np
    from PIL import Image as PILImage
    from moviepy import (
        AudioFileClip,
        ColorClip,
        CompositeAudioClip,
        VideoClip,
        concatenate_videoclips,
        concatenate_audioclips,
    )
    from app.services.video import vfx_compat as vfx

    primary_rgb   = _hex_to_rgb(primary_hex)
    secondary_rgb = _hex_to_rgb(secondary_hex)

    # Load + pre-process character images (RGBA, resized to 60% frame height)
    char_height = int(h * 0.60)
    char_imgs: list[PILImage.Image | None] = []
    for cp in char_paths:
        if cp and cp.exists():
            try:
                img = PILImage.open(str(cp)).convert("RGBA")
                ratio = char_height / img.height
                img   = img.resize((int(img.width * ratio), char_height), PILImage.LANCZOS)
                char_imgs.append(img)
            except Exception as exc:  # noqa: BLE001
                log.warning("conversational_char_open_failed", error=str(exc))
                char_imgs.append(None)
        else:
            char_imgs.append(None)
    while len(char_imgs) < 3:
        char_imgs.append(None)

    # Load background
    bg_img: PILImage.Image | None = None
    if bg_path and bg_path.exists():
        try:
            bg_img = PILImage.open(str(bg_path)).convert("RGB").resize((w, h), PILImage.LANCZOS)
        except Exception:  # noqa: BLE001
            pass

    clips = []
    total_duration = 0.0

    for td in turn_data:
        d = td.duration
        total_duration += d
        active_idx = td.character_index
        caption    = td.text
        char_name  = td.character_name

        # Pre-render all frames for this turn into a VideoClip
        def make_frame(t: float, _active=active_idx, _cap=caption, _name=char_name,
                       _d=d) -> np.ndarray:
            return _render_frame(
                t=t, duration=_d,
                active_idx=_active,
                char_imgs=char_imgs,
                bg_img=bg_img,
                w=w, h=h,
                primary_rgb=primary_rgb,
                secondary_rgb=secondary_rgb,
                caption=_cap,
                char_name=_name,
                char_names=char_names,
                font_path=font_path,
                show_names=show_names,
                overlay_opacity=overlay_opacity,
            )

        clip = VideoClip(make_frame, duration=d)

        if td.narration_audio:
            try:
                narr = AudioFileClip(str(td.narration_audio))
                if narr.duration > d:
                    narr = narr.subclipped(0, d)
                if voice_volume < 1.0:
                    narr = narr.with_effects([MultiplyVolume(voice_volume)])
                clip = clip.with_audio(narr)
            except Exception as exc:  # noqa: BLE001
                log.warning("conversational_audio_failed", error=str(exc))

        if transition_dur > 0:
            clip = clip.with_effects([vfx.FadeIn(min(transition_dur, d * 0.2)]))
            clip = clip.with_effects([vfx.FadeOut(min(transition_dur, d * 0.2)]))

        clips.append(clip)

    if not clips:
        bg_c = primary_rgb
        clips = [ColorClip(size=(w, h), color=bg_c, duration=3.0)]
        total_duration = 3.0

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
            log.warning("conversational_music_overlay_failed", error=str(exc))

    _write(final, output_path, tmp_dir, fps)
    final.close()
    return total_duration


def _render_frame(
    t: float,
    duration: float,
    active_idx: int,
    char_imgs: list,
    bg_img,
    w: int,
    h: int,
    primary_rgb: tuple,
    secondary_rgb: tuple,
    caption: str,
    char_name: str,
    char_names: list,
    font_path: Path | None,
    show_names: bool,
    overlay_opacity: float,
) -> "np.ndarray":
    import numpy as np
    from PIL import Image as PILImage, ImageDraw, ImageFilter

    # Background
    if bg_img is not None:
        frame = bg_img.copy()
    else:
        frame = PILImage.new("RGB", (w, h), color=primary_rgb)

    draw = ImageDraw.Draw(frame)

    # Draw characters
    num_chars = min(2, sum(1 for ci in char_imgs if ci is not None) or 2)
    char_y_base = int(h * 0.22)   # top of character area

    for ci in range(num_chars):
        is_active = (ci == active_idx)
        scale = _ACTIVE_SCALE if is_active else _INACTIVE_SCALE
        bob_y = 0
        if is_active:
            bob_y = int(_BOB_AMPLITUDE_PX * math.sin(2 * math.pi * _BOB_FREQ_HZ * t))

        x_frac = _CHAR_X_FRACS[ci]
        char_img = char_imgs[ci]

        if char_img is not None:
            sw = int(char_img.width * scale)
            sh = int(char_img.height * scale)
            c_img = char_img.resize((sw, sh), PILImage.LANCZOS)
            if not is_active:
                # Dim inactive character
                import PIL.ImageEnhance as IE
                c_img = IE.Brightness(c_img).enhance(_INACTIVE_DIM)
            cx = int(w * x_frac) - sw // 2
            cy = char_y_base + bob_y
            if c_img.mode == "RGBA":
                frame.paste(c_img, (cx, cy), c_img)
            else:
                frame.paste(c_img, (cx, cy))
        else:
            # Draw silhouette placeholder
            sc = _SILHOUETTE_COLORS[ci % len(_SILHOUETTE_COLORS)]
            if not is_active:
                sc = tuple(int(c * _INACTIVE_DIM) for c in sc)
            cx = int(w * x_frac)
            cy = char_y_base + int(h * 0.15) + bob_y
            head_r = int(h * 0.07 * scale)
            body_h = int(h * 0.28 * scale)
            body_w = int(h * 0.12 * scale)
            draw.ellipse(
                [(cx - head_r, cy - head_r), (cx + head_r, cy + head_r)],
                fill=sc,
            )
            draw.rounded_rectangle(
                [(cx - body_w // 2, cy + head_r),
                 (cx + body_w // 2, cy + head_r + body_h)],
                radius=10,
                fill=sc,
            )

        # Speech bubble (active only)
        if is_active and ci == active_idx:
            bx = int(w * x_frac)
            by = char_y_base + bob_y - int(h * 0.04)
            bw, bh = int(w * 0.25), int(h * 0.08)
            _draw_speech_bubble(draw, bx, by, bw, bh, secondary_rgb)

        # Name label
        if show_names:
            name = char_names[ci] if ci < len(char_names) else f"Char{ci}"
            name_y = char_y_base + int(h * 0.56)
            lf = _load_font(max(18, h // 32), font_path)
            name_fill = secondary_rgb if is_active else tuple(int(c * 0.7) for c in secondary_rgb)
            try:
                bbox = draw.textbbox((0, 0), name, font=lf)
                tw = bbox[2] - bbox[0]
                nx = int(w * x_frac) - tw // 2
                draw.text((nx, name_y), name, font=lf, fill=name_fill)
            except Exception:  # noqa: BLE001
                pass

    # Caption bar at bottom
    _draw_caption_bar(
        frame=frame,
        draw=draw,
        text=caption[:120],
        char_name=char_name,
        w=w, h=h,
        secondary_rgb=secondary_rgb,
        primary_rgb=primary_rgb,
        font_path=font_path,
        opacity=overlay_opacity,
    )

    return np.array(frame)


def _draw_speech_bubble(
    draw,
    cx: int, cy: int,
    bw: int, bh: int,
    color: tuple,
) -> None:
    """Draw a small speech bubble indicator above active character."""
    bubble_alpha = 160
    x0, y0 = cx - bw // 2, cy - bh
    x1, y1 = cx + bw // 2, cy
    # Bubble body — can't do true alpha with ImageDraw on RGB, just use fill
    draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=bh // 3, fill=color)
    # Pointer triangle
    draw.polygon(
        [(cx - bh // 4, y1), (cx + bh // 4, y1), (cx, y1 + bh // 3)],
        fill=color,
    )


def _draw_caption_bar(
    frame,
    draw,
    text: str,
    char_name: str,
    w: int, h: int,
    secondary_rgb: tuple,
    primary_rgb: tuple,
    font_path: Path | None,
    opacity: float,
) -> None:
    from PIL import Image as PILImage

    bar_h = int(h * 0.14)
    bar_y = h - bar_h
    alpha = int(opacity * 255)

    overlay = PILImage.new("RGBA", (w, bar_h), (*primary_rgb, alpha))
    frame_rgba = frame.convert("RGBA")
    frame_rgba.paste(overlay, (0, bar_y), overlay)
    merged = frame_rgba.convert("RGB")
    frame.paste(merged)
    draw = draw._image.paste if hasattr(draw, "_image") else None  # noqa: SLF001

    # Redraw on merged image
    from PIL import ImageDraw
    draw2 = ImageDraw.Draw(frame)

    name_font = _load_font(max(16, h // 36), font_path)
    text_font = _load_font(max(20, h // 28), font_path)
    pad = int(w * 0.04)

    # Character name
    draw2.text((pad, bar_y + int(bar_h * 0.08)), char_name,
               font=name_font, fill=secondary_rgb)

    # Caption text (word-wrapped)
    y_text = bar_y + int(bar_h * 0.40)
    _draw_wrapped_text(
        draw=draw2,
        text=text,
        font=text_font,
        x=pad,
        y=y_text,
        max_width=w - 2 * pad,
        line_spacing=int(h // 28 * 1.4),
        fill=secondary_rgb,
        max_y=h - int(h * 0.01),
    )


def _draw_wrapped_text(draw, text, font, x, y, max_width, line_spacing, fill, max_y=99999):
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


def _load_font(size: int, font_path: Path | None = None):
    from PIL import ImageFont
    if font_path and font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:  # noqa: BLE001
            pass
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    ]:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:  # noqa: BLE001
                continue
    return ImageFont.load_default()


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
