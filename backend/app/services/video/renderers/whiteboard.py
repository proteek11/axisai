"""
WhiteboardRenderer — whiteboard-style step-by-step animated video.

Structure:
  - LLM breaks script into steps (heading, body bullets, duration_seconds)
  - Each step: animated "writing" effect reveals text character-by-character
  - TTS narration per step, aligned to reveal speed
  - Steps assembled with fade transitions

Template settings consumed
--------------------------
  boardcolor       — canvas / background colour (default warm white #FAF8F0)
  markercolor      — ink / text colour (default near-black #1E1E1E)
  drawspeed        — "slow" | "normal" | "fast"
                       slow:   5 chars/s  → meditative, classroom style
                       normal: 12 chars/s → default (feels like real writing)
                       fast:   25 chars/s → snappy, highlight-reel
  primarycolor     — accent / heading colour
  accentcolor      — secondary accent
  fontfamily       — TTF font name (Google Font auto-download)
  aspectratio      — "16:9" | "9:16" | "1:1" | "4:3"
  resolution       — "720p" | "1080p" | "4k"
  transition       — "fade" | "wipe" etc.
  transitionduration — seconds
  bgmvolume        — background music volume

Phase 2: Per-frame progressive text reveal via VideoClip(make_frame, duration).
"""
from __future__ import annotations

import asyncio
import functools
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import structlog

from app.services.video import RenderResult
from app.services.video.base_renderer import BaseVideoRenderer

log = structlog.get_logger(__name__)

_FPS = 24
_MIN_STEP_DURATION = 3.0

_DEFAULT_BG_COLOR  = (250, 248, 240)   # warm white
_DEFAULT_INK_COLOR = (30, 30, 30)      # near-black ink

# drawspeed → chars revealed per second
_DRAWSPEED_CPS = {"slow": 5, "normal": 12, "fast": 25}

# Heading reveals first; body text then animates after
_HEADING_FRACTION = 0.25  # fraction of step duration used for heading reveal


@dataclass
class _CharSpan:
    """Position of a single character on the canvas."""
    char: str
    x: int
    y: int
    is_heading: bool


@dataclass
class _StepData:
    narration_audio: Path | None
    duration: float
    heading: str
    body: str
    bg_frame: np.ndarray           # H×W×3 uint8 background (no text)
    char_spans: list[_CharSpan]    # ordered list of characters to reveal
    accent_rgb: tuple[int, int, int]
    ink_rgb: tuple[int, int, int]
    heading_rgb: tuple[int, int, int]
    # chars_per_second resolved from drawspeed
    chars_per_sec: float = 12.0


class WhiteboardRenderer(BaseVideoRenderer):
    """
    Whiteboard animation: text is progressively "written" onto the canvas.

    Phase 2 uses VideoClip(make_frame, duration) so each frame draws only
    the characters revealed so far — giving a genuine writing effect.
    """

    async def render(self) -> RenderResult:
        script = self.job.script or self.job.title
        w, h = self._get_resolution()
        primary, _secondary = self._get_brand_colors()

        bg_color  = _hex_to_rgb(
            self.settings.get("boardcolor") or "", _DEFAULT_BG_COLOR
        )
        ink_color = _hex_to_rgb(
            self.settings.get("markercolor") or "", _DEFAULT_INK_COLOR
        )
        accent_rgb   = _hex_to_rgb(primary, (37, 99, 235))
        drawspeed: str = str(self.settings.get("drawspeed") or "normal").lower()
        chars_per_sec  = float(_DRAWSPEED_CPS.get(drawspeed, 12))

        font_path: Path | None = await asyncio.get_running_loop().run_in_executor(
            None, self._get_font_path, True
        )

        # ── Plan steps ────────────────────────────────────────────────────────
        await self._update_progress(20, "Planning whiteboard steps...")
        steps = await self._plan_scenes(script)
        if not steps:
            steps = [{
                "heading":          self.job.title,
                "body":             script,
                "duration_seconds": 10,
                "narration":        script,
            }]

        # ── Build step data ────────────────────────────────────────────────────
        await self._update_progress(30, f"Preparing {len(steps)} whiteboard steps...")
        step_data: list[_StepData] = []
        loop = asyncio.get_running_loop()

        for idx, step in enumerate(steps):
            heading   = str(step.get("heading", ""))
            body      = str(step.get("body", step.get("narration", "")))
            narration = str(step.get("narration", body or script))

            # TTS
            audio_path = self.tmp_dir / f"step_{idx}_audio.mp3"
            try:
                tts_dur  = await self._synthesize_tts(narration, audio_path)
                all_chars = len(heading) + len(body)
                min_dur_for_reveal = all_chars / chars_per_sec + 1.0
                duration = max(_MIN_STEP_DURATION, tts_dur, min_dur_for_reveal)
            except Exception as exc:  # noqa: BLE001
                log.warning("whiteboard_tts_failed", step=idx, error=str(exc))
                audio_path = None
                all_chars  = len(heading) + len(body)
                duration   = max(
                    _MIN_STEP_DURATION,
                    float(step.get("duration_seconds", 8)),
                    all_chars / chars_per_sec + 1.0,
                )

            # Pre-compute layout (blocking)
            bg_frame, char_spans = await loop.run_in_executor(
                None,
                _compute_layout,
                heading, body, w, h,
                accent_rgb, bg_color, ink_color, font_path,
            )

            step_data.append(_StepData(
                narration_audio=(
                    audio_path if (audio_path and audio_path.exists()) else None
                ),
                duration=duration,
                heading=heading,
                body=body,
                bg_frame=bg_frame,
                char_spans=char_spans,
                accent_rgb=accent_rgb,
                ink_rgb=ink_color,
                heading_rgb=accent_rgb,
                chars_per_sec=chars_per_sec,
            ))

            pct = 30 + int(40 * (idx + 1) / len(steps))
            await self._update_progress(pct, f"Step {idx + 1}/{len(steps)} ready")

        # ── Assemble ──────────────────────────────────────────────────────────
        await self._update_progress(72, "Assembling whiteboard video...")
        output_path = self.tmp_dir / "raw.mp4"

        fn = functools.partial(
            _assemble_whiteboard,
            step_data=step_data,
            w=w, h=h,
            bg_color=bg_color,
            transition=self._get_transition(),
            transition_dur=self._get_transition_duration(),
            tmp_dir=self.tmp_dir,
            output_path=output_path,
            fps=_FPS,
        )
        total_duration = await loop.run_in_executor(None, fn)

        await self._update_progress(75, "Whiteboard render complete.")
        return RenderResult(
            raw_mp4_path=output_path,
            duration_seconds=total_duration,
            metadata={
                "step_count":  len(steps),
                "boardcolor":  _rgb_to_hex(bg_color),
                "markercolor": _rgb_to_hex(ink_color),
                "drawspeed":   drawspeed,
                "phase":       2,
            },
        )


# ── Layout pre-computation ────────────────────────────────────────────────────

def _compute_layout(
    heading: str,
    body: str,
    w: int,
    h: int,
    accent_rgb: tuple[int, int, int],
    bg_color: tuple[int, int, int],
    ink_color: tuple[int, int, int],
    font_path: Path | None,
) -> tuple[np.ndarray, list[_CharSpan]]:
    """
    Pre-compute:
      1. bg_frame — the canvas with accent bar, divider, bottom border (no text).
      2. char_spans — ordered list of (_CharSpan) for progressive reveal.

    Returns (bg_frame_ndarray, char_spans).
    """
    from PIL import Image as PILImage, ImageDraw

    pad          = int(w * 0.06)
    heading_size = max(36, h // 12)
    body_size    = max(22, h // 20)

    heading_font = _load_font(heading_size, font_path)
    body_font    = _load_font(body_size, font_path)

    # ── Background frame (accent bar + divider line + bottom border) ──────────
    bg_img  = PILImage.new("RGB", (w, h), color=bg_color)
    bg_draw = ImageDraw.Draw(bg_img)

    bar_w = max(8, w // 80)
    bg_draw.rectangle(
        [(pad - bar_w - 4, pad // 2), (pad - 4, h - pad // 2)],
        fill=accent_rgb,
    )
    bg_draw.line([(0, h - 4), (w, h - 4)], fill=accent_rgb, width=4)
    bg_frame = np.array(bg_img)

    # ── Char spans — heading ──────────────────────────────────────────────────
    char_spans: list[_CharSpan] = []
    y_cursor = int(h * 0.10)

    if heading:
        # Lay out heading characters one by one to get exact x positions
        x = pad
        for ch in heading:
            char_spans.append(_CharSpan(char=ch, x=x, y=y_cursor, is_heading=True))
            try:
                advance = int(bg_draw.textlength(ch, font=heading_font))
            except Exception:  # noqa: BLE001
                advance = heading_size // 2
            x += max(1, advance)

        # Advance y_cursor past heading + divider (same as Phase 1)
        try:
            bbox     = bg_draw.textbbox((pad, y_cursor), heading, font=heading_font)
            y_cursor = bbox[3] + int(h * 0.04)
        except AttributeError:
            y_cursor += heading_size + int(h * 0.04)
        y_cursor += int(h * 0.03)

    # ── Char spans — body (word-wrapped) ─────────────────────────────────────
    if body:
        # Estimate chars per line
        avg_char_w = max(1, body_size // 2)
        chars_per_line = max(20, (w - 2 * pad) // avg_char_w)
        wrapped_lines  = textwrap.wrap(body, width=chars_per_line) or [body]
        line_h         = int(body_size * 1.5)

        for line in wrapped_lines:
            if y_cursor > h - pad:
                break
            x = pad
            for ch in line:
                if y_cursor > h - pad:
                    break
                char_spans.append(
                    _CharSpan(char=ch, x=x, y=y_cursor, is_heading=False)
                )
                try:
                    advance = int(bg_draw.textlength(ch, font=body_font))
                except Exception:  # noqa: BLE001
                    advance = avg_char_w
                x += max(1, advance)
            # Newline → add a space span that advances y
            char_spans.append(
                _CharSpan(char="\n", x=pad, y=y_cursor, is_heading=False)
            )
            y_cursor += line_h

    return bg_frame, char_spans


# ── Per-frame renderer ────────────────────────────────────────────────────────

def _make_frame_fn(
    sd: "_StepData",
    total_chars: int,
    heading_char_count: int,
    font_path: Path | None,
    w: int,
    h: int,
) -> Callable[[float], np.ndarray]:
    """
    Return a make_frame(t) callable for MoviePy's VideoClip.

    At time t, reveals the first N characters where
      N = chars_per_sec * t   (capped at total_chars).

    Heading characters and body characters use different fonts.
    """
    # Pre-load fonts once (shared across all frames)
    heading_size = max(36, h // 12)
    body_size    = max(22, h // 20)
    h_font       = _load_font(heading_size, font_path)
    b_font       = _load_font(body_size, font_path)

    bg      = sd.bg_frame
    spans   = sd.char_spans
    h_rgb   = sd.heading_rgb
    ink_rgb = sd.ink_rgb
    cps     = sd.chars_per_sec

    def make_frame(t: float) -> np.ndarray:
        revealed = min(total_chars, int(cps * t))
        frame    = bg.copy()  # copy background (accent bar already drawn)

        from PIL import Image as PILImage, ImageDraw
        img  = PILImage.fromarray(frame)
        draw = ImageDraw.Draw(img)

        drawn = 0
        for span in spans:
            if drawn >= revealed:
                break
            if span.char == "\n":
                # Newline span — counts as 0 chars toward reveal
                continue
            font  = h_font if span.is_heading else b_font
            color = h_rgb  if span.is_heading else ink_rgb
            draw.text((span.x, span.y), span.char, font=font, fill=color)
            drawn += 1

            # Draw heading underline once entire heading is revealed
            if (
                span.is_heading
                and drawn == heading_char_count
                and heading_char_count > 0
            ):
                # Find y position just below last heading char
                try:
                    bbox = draw.textbbox(
                        (span.x, span.y), span.char, font=h_font
                    )
                    line_y = bbox[3] + max(4, h // 80)
                except Exception:  # noqa: BLE001
                    line_y = span.y + heading_size + 4
                pad = int(w * 0.06)
                draw.line(
                    [(pad, line_y), (w - pad, line_y)],
                    fill=h_rgb,
                    width=2,
                )

        return np.array(img)

    return make_frame


# ── Assembly ──────────────────────────────────────────────────────────────────

def _assemble_whiteboard(
    *,
    step_data: list[_StepData],
    w: int,
    h: int,
    bg_color: tuple[int, int, int],
    transition: str,
    transition_dur: float,
    tmp_dir: Path,
    output_path: Path,
    fps: int,
    font_path: Path | None = None,
) -> float:
    from moviepy import VideoClip
    from moviepy import AudioFileClip, ColorClip, concatenate_videoclips
    from app.services.video import vfx_compat as vfx

    clips = []
    total_duration = 0.0

    for sd in step_data:
        d = sd.duration

        # Count only non-newline characters
        total_chars    = sum(1 for sp in sd.char_spans if sp.char != "\n")
        heading_chars  = sum(
            1 for sp in sd.char_spans if sp.is_heading and sp.char != "\n"
        )

        make_frame = _make_frame_fn(
            sd=sd,
            total_chars=total_chars,
            heading_char_count=heading_chars,
            font_path=font_path,
            w=w,
            h=h,
        )

        clip = VideoClip(make_frame, duration=d)
        clip = clip.with_fps(fps)

        if sd.narration_audio and sd.narration_audio.exists():
            try:
                narration = AudioFileClip(str(sd.narration_audio))
                if narration.duration > d:
                    narration = narration.subclipped(0, d)
                clip = clip.with_audio(narration)
            except Exception as exc:  # noqa: BLE001
                log.warning("whiteboard_audio_attach_failed", error=str(exc))

        if transition == "fade":
            clip = clip.with_effects([vfx.FadeIn(transition_dur), vfx.FadeOut(transition_dur)])

        clips.append(clip)
        total_duration += d

    if not clips:
        final         = ColorClip(size=(w, h), color=bg_color, duration=3.0)
        total_duration = 3.0
    else:
        final = concatenate_videoclips(clips, method="compose")

    _write(final, output_path, tmp_dir, fps)
    final.close()
    return total_duration


# ── Shared helpers ────────────────────────────────────────────────────────────

def _load_font(size: int, font_path: Path | None):
    """Return best available PIL ImageFont at given size."""
    from PIL import ImageFont
    if font_path and font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:  # noqa: BLE001
            pass
    _fallbacks = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]
    for p in _fallbacks:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:  # noqa: BLE001
                continue
    return ImageFont.load_default()


def _hex_to_rgb(
    hex_color: str,
    default: tuple[int, int, int] = (37, 99, 235),
) -> tuple[int, int, int]:
    if not hex_color:
        return default
    h = str(hex_color).lstrip("#").strip()
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return default
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return default


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


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
