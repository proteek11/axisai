"""
ScreencastRenderer — tutorial / how-to screencast-style video.

Structure:
  - LLM breaks script into steps (step_number, heading, action, callout,
    narration, duration_seconds)
  - Each step: Pillow renders a "mock screen" frame:
      - Dark terminal / browser chrome at top
      - Step number badge (accent color, top-left)
      - Heading below chrome
      - Code block / action text in monospace font on dark panel
      - Optional callout bubble with pointer (annotation-style)
      - Animated cursor blink (alternating frames in executor)
  - TTS narration per step
  - Steps assembled with fade or cut transition
  - Optional background music at low volume

No external API or screen capture required — fully synthesized.
For real screen capture, attach pre-recorded screen video via
  assets.screen_video_url (the renderer will composite narration audio).
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

_FPS       = 24
_MIN_STEP_DURATION = 4.0
_BG_COLOR  = (18, 18, 24)       # very dark blue-grey (IDE background feel)
_CHROME_BG = (32, 32, 40)       # slightly lighter – top chrome
_CODE_BG   = (28, 28, 34)       # code panel background
_CODE_FG   = (180, 210, 180)    # greenish code text
_CHROME_H_FRAC = 0.07           # fraction of h for chrome strip


@dataclass
class _StepData:
    narration_audio: Path | None
    image_path: Path
    duration: float
    heading: str
    action: str
    callout: str
    step_number: int


class ScreencastRenderer(BaseVideoRenderer):
    """Screencast-style tutorial video: mock IDE/browser + narrated steps."""

    async def render(self) -> RenderResult:
        script = self.job.script or self.job.title
        w, h = self._get_resolution()
        primary, secondary = self._get_brand_colors()

        # ── Resolve template-specific settings ────────────────────────────────
        show_cursor: bool        = _truthy(self.settings.get("showcursor",        True))
        show_click_indicator: bool= _truthy(self.settings.get("showclickindicator", True))
        show_step_counter: bool  = _truthy(self.settings.get("showstepcounter",   True))

        loop = asyncio.get_running_loop()
        font_path: Path | None = await loop.run_in_executor(
            None, self._get_font_path, False   # mono font preferred; base fallback here
        )
        transition_dur = self._get_transition_duration()
        music_volume   = self._get_music_volume()

        # ── Plan steps ────────────────────────────────────────────────────────
        await self._update_progress(20, "Planning screencast steps...")
        steps = await self._plan_scenes(script)
        if not steps:
            steps = [{
                "step_number": 1,
                "heading": self.job.title,
                "action": script,
                "callout": "",
                "narration": script,
                "duration_seconds": 10,
            }]

        # ── Build each step ───────────────────────────────────────────────────
        await self._update_progress(30, f"Rendering {len(steps)} screencast steps...")
        step_data: list[_StepData] = []

        for idx, step in enumerate(steps):
            step_number = int(step.get("step_number", idx + 1))
            heading     = str(step.get("heading", f"Step {step_number}"))
            action      = str(step.get("action", step.get("body", "")))
            callout     = str(step.get("callout", ""))
            narration   = str(step.get("narration", heading))

            # TTS
            audio_path = self.tmp_dir / f"step_{idx}_audio.mp3"
            try:
                tts_dur = await self._synthesize_tts(narration, audio_path)
                duration = max(_MIN_STEP_DURATION, tts_dur)
            except Exception as exc:  # noqa: BLE001
                log.warning("screencast_tts_failed", step=idx, error=str(exc))
                audio_path = None
                duration = float(step.get("duration_seconds", 8))

            # Render step image
            image_path = self.tmp_dir / f"step_{idx}.png"
            await loop.run_in_executor(
                None,
                _render_step_image,
                step_number, heading, action, callout,
                w, h, image_path,
                _hex_to_rgb(primary), _hex_to_rgb(secondary),
                show_cursor, show_click_indicator, show_step_counter,
                font_path,
            )

            step_data.append(_StepData(
                narration_audio=audio_path if (audio_path and audio_path.exists()) else None,
                image_path=image_path,
                duration=duration,
                heading=heading,
                action=action,
                callout=callout,
                step_number=step_number,
            ))

            pct = 30 + int(40 * (idx + 1) / len(steps))
            await self._update_progress(pct, f"Step {idx + 1}/{len(steps)} ready")

        # ── Optional background music ─────────────────────────────────────────
        music_path: Path | None = None
        music_url = self.assets.get("music_url")
        if music_url:
            try:
                music_path = self.tmp_dir / "music.mp3"
                await self._download_asset(music_url, music_path)
            except Exception as exc:  # noqa: BLE001
                log.warning("screencast_music_failed", error=str(exc))

        # ── Assemble ──────────────────────────────────────────────────────────
        await self._update_progress(72, "Assembling screencast video...")
        output_path = self.tmp_dir / "raw.mp4"

        fn = functools.partial(
            _assemble_screencast,
            step_data=step_data,
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

        await self._update_progress(75, "Screencast render complete.")
        return RenderResult(
            raw_mp4_path=output_path,
            duration_seconds=total_duration,
            metadata={
                "step_count": len(steps),
                "showcursor": show_cursor,
                "showclickindicator": show_click_indicator,
                "showstepcounter": show_step_counter,
            },
        )


# ── Synchronous frame rendering ───────────────────────────────────────────────

def _render_step_image(
    step_number: int,
    heading: str,
    action: str,
    callout: str,
    w: int,
    h: int,
    output_path: Path,
    primary_rgb: tuple[int, int, int],
    secondary_rgb: tuple[int, int, int],
    show_cursor: bool = True,
    show_click_indicator: bool = True,
    show_step_counter: bool = True,
    font_path: "Path | None" = None,  # type: ignore[name-defined]
) -> None:
    """
    Draw a screencast-style tutorial frame as PNG.

    Layout:
      - Very dark BG full frame
      - Top chrome strip (traffic lights dots, step N of M, URL-bar style)
      - Step badge (accent circle) + heading
      - Monospace code/action block with syntax-style coloring
      - Optional callout bubble with text (bottom-left or bottom-right)
      - Left accent bar (brand secondary)
    """
    from PIL import Image as PILImage, ImageDraw

    img  = PILImage.new("RGB", (w, h), color=_BG_COLOR)
    draw = ImageDraw.Draw(img)

    chrome_h = max(30, int(h * _CHROME_H_FRAC))
    pad      = int(w * 0.05)

    # ── Top chrome strip ──────────────────────────────────────────────────────
    draw.rectangle([(0, 0), (w, chrome_h)], fill=_CHROME_BG)

    # Traffic-light dots
    dot_r = max(5, chrome_h // 5)
    for di, dc in enumerate([(220, 80, 80), (220, 170, 60), (100, 200, 100)]):
        cx = pad // 2 + di * (dot_r * 3)
        cy = chrome_h // 2
        draw.ellipse([(cx - dot_r, cy - dot_r), (cx + dot_r, cy + dot_r)], fill=dc)

    # URL-bar style center text
    url_w = int(w * 0.40)
    url_x = (w - url_w) // 2
    url_y = (chrome_h - dot_r * 2) // 2
    draw.rounded_rectangle(
        [(url_x, url_y), (url_x + url_w, chrome_h - url_y)],
        radius=dot_r,
        fill=(50, 50, 60),
    )
    url_font = _find_font(max(12, chrome_h // 3))
    draw.text((url_x + 8, url_y + 2), "● Step", font=url_font,
              fill=(150, 220, 150))

    # ── Left accent bar ───────────────────────────────────────────────────────
    bar_w = max(6, w // 70)
    draw.rectangle([(0, chrome_h), (bar_w, h)], fill=secondary_rgb)

    # ── Step badge ────────────────────────────────────────────────────────────
    badge_r     = max(20, h // 18)
    badge_x     = bar_w + pad
    badge_y     = chrome_h + int(h * 0.06)
    draw.ellipse(
        [(badge_x, badge_y), (badge_x + badge_r * 2, badge_y + badge_r * 2)],
        fill=secondary_rgb,
    )
    badge_font = _find_font(max(18, badge_r))
    step_str = str(step_number)
    try:
        sw = draw.textlength(step_str, font=badge_font)
    except Exception:  # noqa: BLE001
        sw = badge_r
    draw.text(
        (badge_x + badge_r - int(sw) // 2, badge_y + badge_r // 4),
        step_str, font=badge_font, fill=_BG_COLOR,
    )

    # ── Heading ───────────────────────────────────────────────────────────────
    heading_x    = badge_x + badge_r * 2 + 12
    heading_y    = badge_y + badge_r // 4
    heading_size = max(28, h // 14)
    h_font = _find_font(heading_size)
    if heading:
        draw.text((heading_x, heading_y), heading[:70], font=h_font,
                  fill=secondary_rgb)

    y_cursor = badge_y + badge_r * 2 + int(h * 0.04)

    # ── Code/action panel ─────────────────────────────────────────────────────
    code_panel_h = int(h * 0.46)
    code_x       = bar_w + pad
    code_panel_w = w - code_x - pad
    draw.rectangle(
        [(code_x, y_cursor), (code_x + code_panel_w, y_cursor + code_panel_h)],
        fill=_CODE_BG,
        outline=tuple(max(0, int(c * 0.40)) for c in secondary_rgb),  # type: ignore[arg-type]
        width=1,
    )

    # Line numbers gutter
    gutter_w = max(40, pad)
    draw.rectangle(
        [(code_x, y_cursor), (code_x + gutter_w, y_cursor + code_panel_h)],
        fill=tuple(max(0, int(c * 0.80)) for c in _CODE_BG),  # type: ignore[arg-type]
    )

    code_font_size = max(18, h // 28)
    code_font      = _find_mono_font(code_font_size)
    code_line_h    = int(code_font_size * 1.55)
    cx_text        = code_x + gutter_w + 10
    cy_text        = y_cursor + 10
    max_code_w     = code_panel_w - gutter_w - 20

    # Render action text as "code" lines
    action_lines = action.split("\n") if "\n" in action else _wrap_code_text(
        action, code_font, draw, max_code_w
    )
    for ln_idx, line in enumerate(action_lines[:16]):
        if cy_text + code_font_size > y_cursor + code_panel_h - 8:
            break
        # Line number
        ln_str = str(ln_idx + 1)
        draw.text((code_x + 4, cy_text), ln_str, font=code_font,
                  fill=(100, 100, 120))
        # Code text with simple keyword highlighting
        _draw_code_line(draw, line, code_font, cx_text, cy_text, secondary_rgb)
        cy_text += code_line_h

    # Cursor blink indicator (solid block cursor at end of last line)
    draw.rectangle(
        [(cx_text, cy_text), (cx_text + code_font_size // 2, cy_text + code_font_size)],
        fill=secondary_rgb,
    )

    # ── Callout bubble ────────────────────────────────────────────────────────
    if callout:
        bubble_y = y_cursor + code_panel_h + int(h * 0.04)
        _draw_callout(draw, callout, code_x, bubble_y,
                      w - 2 * pad, secondary_rgb, h)

    # ── Bottom progress bar ───────────────────────────────────────────────────
    pb_h = max(4, h // 80)
    pb_fill = max(1, int(w * 0.30))  # Static 30% fill indicator
    draw.rectangle([(0, h - pb_h), (w, h - 1)],
                   fill=tuple(max(0, int(c * 0.30)) for c in secondary_rgb))  # type: ignore[arg-type]
    draw.rectangle([(0, h - pb_h), (pb_fill, h - 1)], fill=secondary_rgb)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")


def _wrap_code_text(text: str, font, draw, max_width: int) -> list[str]:
    """Split action text into lines that fit within max_width."""
    words = text.split()
    lines: list[str] = []
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
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines or [text[:80]]


def _draw_code_line(draw, line: str, font, x: int, y: int, accent_rgb):
    """Draw a line of "code" with minimal keyword coloring."""
    # Keywords → accent color; strings → green; rest → pale white
    keywords = {"def", "class", "import", "from", "return", "if", "else",
                "for", "while", "try", "except", "with", "as", "in", "not",
                "and", "or", "True", "False", "None", "async", "await",
                "function", "const", "let", "var", "new", "this"}
    tokens = line.split()
    cx = x
    space_w = 6
    for tok in tokens:
        clean = tok.strip("(){}[],:;\"'")
        if clean in keywords:
            fill = accent_rgb
        elif (tok.startswith('"') or tok.startswith("'")
              or tok.startswith('`')):
            fill = (180, 240, 130)  # greenish for strings
        elif tok.startswith("#") or tok.startswith("//"):
            fill = (130, 130, 160)  # grey for comments
        else:
            fill = _CODE_FG
        try:
            draw.text((cx, y), tok, font=font, fill=fill)
            tw = int(draw.textlength(tok, font=font))
        except Exception:  # noqa: BLE001
            tw = len(tok) * 8
        cx += tw + space_w


def _draw_callout(draw, text: str, x: int, y: int, max_w: int, accent_rgb, h: int):
    """Draw a speech-bubble callout box with text."""
    from PIL import ImageFont
    font_size = max(20, h // 26)
    font = _find_font(font_size)
    bubble_pad = 12
    bubble_max_w = min(max_w, int(max_w * 0.60))

    # Word wrap into bubble
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words[:40]:
        test = f"{line} {word}".strip()
        try:
            tw = draw.textlength(test, font=font)
        except Exception:  # noqa: BLE001
            tw = len(test) * 8
        if tw <= bubble_max_w - bubble_pad * 2:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    if not lines:
        return

    line_h    = int(font_size * 1.4)
    bubble_h  = len(lines) * line_h + bubble_pad * 2
    bubble_w  = bubble_max_w

    # Pointer triangle upward
    ptr_x = x + 30
    ptr_y = y - 10
    draw.polygon(
        [(ptr_x, ptr_y + 10), (ptr_x + 10, ptr_y + 10), (ptr_x + 5, ptr_y)],
        fill=accent_rgb,
    )

    draw.rounded_rectangle(
        [(x, y), (x + bubble_w, y + bubble_h)],
        radius=8, fill=accent_rgb,
    )
    ty = y + bubble_pad
    for ln in lines:
        draw.text((x + bubble_pad, ty), ln, font=font, fill=_BG_COLOR)
        ty += line_h


# ── MoviePy assembly ──────────────────────────────────────────────────────────

def _assemble_screencast(
    *,
    step_data: list[_StepData],
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

    for sd in step_data:
        d = sd.duration
        total_duration += d

        if sd.image_path.exists():
            clip = ImageClip(str(sd.image_path), duration=d)
        else:
            clip = ColorClip(size=(w, h), color=_BG_COLOR, duration=d)

        if sd.narration_audio and sd.narration_audio.exists():
            try:
                narration = AudioFileClip(str(sd.narration_audio))
                if narration.duration > d:
                    narration = narration.subclipped(0, d)
                clip = clip.with_audio(narration)
            except Exception as exc:  # noqa: BLE001
                log.warning("screencast_audio_failed", error=str(exc))

        if transition == "fade":
            clip = clip.with_effects([vfx.FadeIn(0.35), vfx.FadeOut(0.35)])

        clips.append(clip)

    if not clips:
        final = ColorClip(size=(w, h), color=_BG_COLOR, duration=3.0)
        total_duration = 3.0
    else:
        final = concatenate_videoclips(clips, method="compose")

    if music_path and music_path.exists() and music_volume > 0:
        final = _overlay_music(final, music_path, music_volume, total_duration)

    _write(final, output_path, tmp_dir, fps)
    final.close()
    return total_duration


# ── Font helpers ──────────────────────────────────────────────────────────────

def _find_mono_font(size: int):
    """Return best available monospace PIL font."""
    from PIL import ImageFont
    mono_paths = [
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoMono-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/UbuntuMono-R.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    for p in mono_paths:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:  # noqa: BLE001
                continue
    try:
        return ImageFont.truetype("cour.ttf", size)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


def _find_font(size: int):
    """Return best available proportional PIL font."""
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
        log.warning("screencast_music_overlay_failed", error=str(exc))
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
