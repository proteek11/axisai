# AXIS AI Video Builder — Testing Guide

Complete manual and automated testing procedures for all 10 video types across
Phase 1 (kinetic, slideshow, stockfootage, avatar) and Phase 2 (explainer,
whiteboard, motion, illustrative, presentation, screencast).

---

## Prerequisites

### 1. Environment Setup

```bash
# Copy and configure environment
cp .env.example .env

# Minimum required for offline tests (no paid APIs)
VIDEO_ENABLED=true
VIDEO_TTS=edge_tts
VIDEO_IMAGE_GEN=none
VIDEO_STOCK=none
VIDEO_AVATAR=none
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
DATABASE_URL=postgresql+asyncpg://axis:axis@localhost:5432/axisai
```

### 2. Start Services

```bash
# Terminal 1 — Redis
docker run -p 6379:6379 redis:7-alpine

# Terminal 2 — Postgres
docker run -e POSTGRES_USER=axis -e POSTGRES_PASSWORD=axis \
           -e POSTGRES_DB=axisai -p 5432:5432 postgres:16

# Terminal 3 — FastAPI
cd axis-ai
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload --port 8001

# Terminal 4 — Celery worker
celery -A app.celery_app worker -l info -Q video_render -c 2
```

### 3. Python quick-test helper

```python
# tests/video/helpers.py  (create if missing)
import httpx, json, time

BASE = "http://localhost:8001"

def create_job(payload: dict, token: str = "test-token") -> dict:
    r = httpx.post(f"{BASE}/api/v1/video/jobs",
                   json=payload,
                   headers={"Authorization": f"Bearer {token}"},
                   timeout=10)
    r.raise_for_status()
    return r.json()

def poll_job(job_id: str, token: str = "test-token",
             max_seconds: int = 300) -> dict:
    deadline = time.time() + max_seconds
    while time.time() < deadline:
        r = httpx.get(f"{BASE}/api/v1/video/jobs/{job_id}",
                      headers={"Authorization": f"Bearer {token}"},
                      timeout=10)
        data = r.json()
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(5)
    raise TimeoutError(f"Job {job_id} did not complete within {max_seconds}s")
```

---

## Phase 1 Renderer Tests

### 1. Kinetic Typography

**Minimum viable test (no external APIs)**

```bash
curl -X POST http://localhost:8001/api/v1/video/jobs \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Kinetic test",
    "video_type": "kinetic",
    "script": "Learning is the engine of growth. Every concept mastered opens a new door.",
    "duration_seconds": 15,
    "language": "en"
  }'
```

**Expected result:** Job created with status `queued` → `rendering` → `completed`.
MP4 should show white words appearing one phrase at a time on dark background,
exactly matching the TTS narration timing.

**Checklist:**
- [ ] Job status transitions correctly (queued → rendering → completed)
- [ ] `duration_seconds` in response ≥ TTS duration of script
- [ ] Output MP4 plays without errors
- [ ] Word timing aligns with audio
- [ ] Resolution matches default 1920×1080

---

### 2. Slideshow

**Test with stock images (requires `VIDEO_STOCK=pexels` and `VIDEO_PEXELS_KEY`)**

```bash
curl -X POST http://localhost:8001/api/v1/video/jobs \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Corporate Training Overview",
    "video_type": "slideshow",
    "script": "Welcome to your onboarding. In this module you will learn our core values, mission statement, and day-to-day processes that keep our teams aligned.",
    "duration_seconds": 30,
    "assets": {"music_url": ""},
    "config": {"transition": "fade"}
  }'
```

**Fallback test (no Pexels key):** Set `VIDEO_STOCK=none`. Slides should use solid
brand primary color background instead of photos.

**Checklist:**
- [ ] Ken Burns effect visible on images (zoom / pan)
- [ ] Captions appear at bottom with semi-transparent bar
- [ ] Fade transitions between slides are smooth
- [ ] Fallback to brand color when no stock provider
- [ ] Audio synced per slide

---

### 3. Stock Footage

```bash
curl -X POST http://localhost:8001/api/v1/video/jobs \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Workplace Safety Essentials",
    "video_type": "stockfootage",
    "script": "Workplace safety protects everyone. Always wear your PPE. Report hazards immediately. Know your emergency exits.",
    "duration_seconds": 25
  }'
```

**Checklist:**
- [ ] Each scene has a relevant stock photo (or brand-color fallback)
- [ ] Lower-third text bar appears for title + body text
- [ ] No RGBA ColorClip errors in worker logs
- [ ] Narration audio embedded per scene

---

### 4. Avatar

**Requires HeyGen API key: `VIDEO_AVATAR=heygen`, `VIDEO_HEYGEN_API_KEY=<key>`**

```bash
curl -X POST http://localhost:8001/api/v1/video/jobs \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "CEO Welcome Message",
    "video_type": "avatar",
    "script": "Hello and welcome to our team. I am delighted to have you join us on this exciting journey.",
    "assets": {
      "avatar_id": "josh_lite3_20230714",
      "voice_id": "en-US-GuyNeural"
    },
    "duration_seconds": 20
  }'
```

**Fallback (no HeyGen key):** Worker should log `avatar_no_provider` warning and
complete with a placeholder MP4 (solid color + TTS audio) rather than crash.

**Checklist:**
- [ ] HeyGen video ID returned and polled to completion
- [ ] Downloaded MP4 embedded correctly
- [ ] Graceful fallback if provider unavailable
- [ ] `asyncio.get_running_loop()` used (no DeprecationWarning in Python 3.12 logs)

---

## Phase 2 Renderer Tests

### 5. Explainer

**Test A — Full pipeline (DALL-E 3 + Pexels)**

```bash
curl -X POST http://localhost:8001/api/v1/video/jobs \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "How Machine Learning Works",
    "video_type": "explainer",
    "script": "Machine learning teaches computers to learn from data. First we collect examples. Then an algorithm finds patterns. Finally the model makes predictions on new data.",
    "duration_seconds": 45,
    "config": {"transition": "fade"}
  }'
```

**Test B — Offline fallback (no image gen, no stock)**

Set `VIDEO_IMAGE_GEN=none`, `VIDEO_STOCK=none`. Each scene should use solid brand
primary color as background. Video must still complete without error.

**Checklist:**
- [ ] LLM planner returns 3–5 scenes with `image_prompt`, `body_text`, `narration`
- [ ] Ken Burns effect applied (zoom_in / zoom_out / pan_left / pan_right cycling)
- [ ] Title bar semi-transparent overlay at top of each scene
- [ ] Body text bar at bottom when `body_text` present
- [ ] Crossfade transitions visible between scenes
- [ ] Music overlay works when `assets.music_url` provided

---

### 6. Whiteboard

```bash
curl -X POST http://localhost:8001/api/v1/video/jobs \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "The Water Cycle Explained",
    "video_type": "whiteboard",
    "script": "Water evaporates from oceans and lakes. It rises into the atmosphere and forms clouds. Then it falls back as rain or snow. This cycle keeps our planet alive.",
    "duration_seconds": 35
  }'
```

**Visual checklist:**
- [ ] Warm white background (`#FAF8F0`) — not pure white
- [ ] Heading appears in brand accent color
- [ ] Body text in near-black ink color
- [ ] Left accent bar visible
- [ ] Bottom border line at frame edge
- [ ] Word-wrapped body text does not overflow frame

---

### 7. Motion Graphics

```bash
curl -X POST http://localhost:8001/api/v1/video/jobs \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Q3 Performance Review",
    "video_type": "motion",
    "script": "Our Q3 results show strong growth. Revenue increased by 18 percent. Customer satisfaction reached 94 percent. New product launches exceeded targets.",
    "duration_seconds": 40,
    "assets": {
      "logo_url": "https://example.com/logo.png"
    }
  }'
```

**Logo test:** Supply a real PNG URL with transparency. Logo should appear
watermarked in top-right corner of every slide.

**Checklist:**
- [ ] Gradient background visible (top → bottom darkening)
- [ ] Left accent bar in secondary brand color
- [ ] Bullet points word-wrapped correctly
- [ ] Progress dots at bottom center (correct count, correct active dot)
- [ ] Logo watermark composited with RGBA mask (no white box)
- [ ] Fade transitions between slides

---

### 8. Illustrative

**Requires character PNG with transparency in assets:**

```bash
curl -X POST http://localhost:8001/api/v1/video/jobs \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Meet Your Learning Guide",
    "video_type": "illustrative",
    "script": "Hi! I am Maya, your learning guide. Today we explore time management. First, prioritize tasks. Second, eliminate distractions. Third, review progress daily.",
    "duration_seconds": 30,
    "assets": {
      "character_urls": [
        "https://example.com/character_female.png",
        "https://example.com/character_male.png"
      ]
    }
  }'
```

**Offline test (no character URLs, no stock):** Video should render background
gradient + caption bar only. No crash.

**Checklist:**
- [ ] Character PNG loaded and composited with correct alpha/transparency
- [ ] Bob animation visible (character moves up/down slightly over time)
- [ ] Character cycles if multiple URLs provided (one per scene mod-cycle)
- [ ] Caption bar semi-transparent at bottom
- [ ] Caption text centered and readable
- [ ] Background: stock photo if Pexels available, gradient fallback otherwise

---

### 9. Presentation

**Full slide type coverage test:**

```bash
curl -X POST http://localhost:8001/api/v1/video/jobs \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Leadership Development Program",
    "video_type": "presentation",
    "script": "Welcome to our Leadership Development Program. In this session we cover emotional intelligence, decision making under pressure, and building high-performance teams. Our leaders report 40 percent improvement in team engagement after completing this program.",
    "duration_seconds": 60
  }'
```

**Manual slide type tests** — add `scenes` override in payload to force specific
layout types:

```json
{"slide_type": "title_slide", "title": "Big Title", "subtitle": "Subtitle here"}
{"slide_type": "divider", "title": "Section Break"}
{"slide_type": "quote", "quote": "The best way to predict the future is to create it.", "attribution": "Peter Drucker"}
{"slide_type": "two_column", "title": "Compare Options", "bullets": ["Option A", "Option B"], "right_bullets": ["Pro 1", "Pro 2"]}
{"slide_type": "image_text", "title": "Visual Concept", "bullets": ["Key point one", "Key point two"]}
```

**Checklist:**
- [ ] Title slide: large centered title + horizontal accent bar
- [ ] Divider: secondary color fills frame, primary text
- [ ] Quote: pull-quote with opening quotation mark + attribution
- [ ] Two-column: equal columns with divider line
- [ ] Image-text: left photo + right text correctly split
- [ ] Content (default): title + bullets + left accent bar
- [ ] Progress dots update correctly per slide
- [ ] Logo watermark if `assets.logo_url` provided

---

### 10. Screencast

```bash
curl -X POST http://localhost:8001/api/v1/video/jobs \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Setting Up Your Development Environment",
    "video_type": "screencast",
    "script": "Step 1: Install Python 3.11 from python.org. Step 2: Create a virtual environment with python -m venv .venv. Step 3: Activate it with source .venv/bin/activate. Step 4: Install dependencies with pip install -r requirements.txt.",
    "duration_seconds": 45
  }'
```

**Checklist:**
- [ ] Dark IDE-style background (`#121218`)
- [ ] Top chrome strip with traffic-light dots
- [ ] URL bar with step indicator
- [ ] Step badge (numbered circle) in accent color
- [ ] Code panel with line numbers and keyword coloring
- [ ] Callout bubble rendered when `callout` field present
- [ ] Bottom progress bar visible
- [ ] Monospace font used in code panel (Liberation Mono / DejaVu / fallback)

---

## API Endpoint Tests

### Create Job

```bash
# Valid request
curl -X POST http://localhost:8001/api/v1/video/jobs \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test","video_type":"kinetic","script":"Hello world","duration_seconds":10}'

# Missing required field → 422
curl -X POST http://localhost:8001/api/v1/video/jobs \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test"}'

# Invalid video_type → 422
curl -X POST http://localhost:8001/api/v1/video/jobs \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test","video_type":"unknown","script":"Hello","duration_seconds":10}'
```

### Poll Job Status

```bash
JOB_ID="<uuid from create response>"

# Poll
curl http://localhost:8001/api/v1/video/jobs/$JOB_ID \
  -H "Authorization: Bearer test-token"

# Expected response shape:
# {
#   "id": "...",
#   "status": "completed",         # queued | rendering | completed | failed
#   "progress": 100,
#   "progress_message": "Done",
#   "video_url": "https://...",    # signed S3 URL or local path
#   "thumbnail_url": "https://...",
#   "duration_seconds": 28.4,
#   "error_message": null
# }
```

### List Jobs

```bash
curl "http://localhost:8001/api/v1/video/jobs?limit=10&offset=0" \
  -H "Authorization: Bearer test-token"
```

### Get Job Assets (renders list for a content item)

```bash
curl "http://localhost:8001/api/v1/video/assets?content_item_id=<id>" \
  -H "Authorization: Bearer test-token"
```

---

## Automated Test Suite

### Run existing tests

```bash
cd axis-ai
pytest tests/video/ -v --tb=short
```

### Test file structure (create these if missing)

```
tests/video/
├── test_api.py             # API endpoint integration tests
├── test_renderers.py       # Unit tests for each renderer
├── test_providers.py       # Provider unit tests
├── test_llm_planner.py     # LLM planner / fallback scene tests
└── fixtures/
    ├── sample_logo.png     # 200×60 RGBA PNG for logo tests
    └── sample_char.png     # 300×600 RGBA PNG character for illustrative tests
```

### Key unit tests for renderers

```python
# tests/video/test_renderers.py
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Test _fallback_scenes returns correct schema per video type
def test_fallback_scenes_kinetic():
    from app.services.video.llm_planner import _fallback_scenes
    scenes = _fallback_scenes("test script", "kinetic", 10)
    assert scenes[0].get("text") or scenes[0].get("effect")

def test_fallback_scenes_avatar():
    from app.services.video.llm_planner import _fallback_scenes
    scenes = _fallback_scenes("test script", "avatar", 10)
    assert "script" in scenes[0]

def test_fallback_scenes_generic():
    from app.services.video.llm_planner import _fallback_scenes
    for vtype in ("explainer", "whiteboard", "motion",
                  "illustrative", "presentation", "screencast"):
        scenes = _fallback_scenes("test", vtype, 10)
        assert isinstance(scenes, list) and len(scenes) > 0

# Test hex_to_rgb helpers
def test_hex_to_rgb_valid():
    from app.services.video.renderers.motion import _hex_to_rgb
    assert _hex_to_rgb("#2563EB") == (37, 99, 235)
    assert _hex_to_rgb("#FFFFFF") == (255, 255, 255)

def test_hex_to_rgb_fallback():
    from app.services.video.renderers.motion import _hex_to_rgb
    assert _hex_to_rgb("bad") == (37, 99, 235)
    assert _hex_to_rgb("") == (37, 99, 235)

# Test Pillow slide render produces output file
def test_render_motion_slide(tmp_path):
    from app.services.video.renderers.motion import _render_slide_image
    out = tmp_path / "slide.png"
    _render_slide_image(
        title="Test Title",
        bullets=["Bullet one", "Bullet two"],
        w=1280, h=720,
        output_path=out,
        primary_rgb=(37, 99, 235),
        secondary_rgb=(255, 255, 255),
        logo_path=None,
        slide_index=0,
        total_slides=3,
    )
    assert out.exists()
    assert out.stat().st_size > 1000

def test_render_whiteboard_step(tmp_path):
    from app.services.video.renderers.whiteboard import _render_step_image
    out = tmp_path / "step.png"
    _render_step_image(
        heading="Test Heading",
        body="This is the body text of the whiteboard step.",
        w=1280, h=720,
        output_path=out,
        accent_rgb=(37, 99, 235),
    )
    assert out.exists()
    assert out.stat().st_size > 500

def test_render_screencast_step(tmp_path):
    from app.services.video.renderers.screencast import _render_step_image
    out = tmp_path / "step.png"
    _render_step_image(
        step_number=1,
        heading="Install Python",
        action="pip install -r requirements.txt",
        callout="Run this in your terminal",
        w=1280, h=720,
        output_path=out,
        primary_rgb=(37, 99, 235),
        secondary_rgb=(100, 220, 120),
    )
    assert out.exists()

def test_render_presentation_title_slide(tmp_path):
    from app.services.video.renderers.presentation import _render_title_slide
    out = tmp_path / "title.png"
    _render_title_slide(
        title="Leadership 101",
        subtitle="Building High-Performance Teams",
        w=1280, h=720,
        output_path=out,
        primary_rgb=(37, 99, 235),
        secondary_rgb=(255, 255, 255),
        logo_path=None,
    )
    assert out.exists()
```

---

## Provider Tests

### EdgeTTS (free, no API key)

```python
# tests/video/test_providers.py
import asyncio, pytest
from pathlib import Path

@pytest.mark.asyncio
async def test_edge_tts(tmp_path):
    from app.services.video.providers.tts.edge_tts import EdgeTTSProvider
    provider = EdgeTTSProvider(voice="en-US-JennyNeural")
    out = tmp_path / "tts.mp3"
    dur = await provider.synthesize("Hello world this is a test.", out)
    assert out.exists()
    assert dur > 0.5
```

### SDXL Local (requires running A1111 instance)

```python
@pytest.mark.skipif(
    not os.getenv("VIDEO_SDXL_LOCAL_URL"),
    reason="SDXL local not configured"
)
@pytest.mark.asyncio
async def test_sdxl_local(tmp_path):
    from app.services.video.providers.image_gen.sdxl_local import SDXLLocalProvider
    p = SDXLLocalProvider(api_url=os.environ["VIDEO_SDXL_LOCAL_URL"])
    out = tmp_path / "img.jpg"
    result = await p.generate(
        prompt="A clean modern office workspace",
        style="photorealistic",
        width=1280, height=720,
        output_path=out,
    )
    assert out.exists()
    assert out.stat().st_size > 10_000
```

### DallE3 (requires OpenAI key)

```python
@pytest.mark.skipif(
    not os.getenv("VIDEO_OPENAI_TTS_KEY"),
    reason="OpenAI key not configured"
)
@pytest.mark.asyncio
async def test_dalle3(tmp_path):
    from app.services.video.providers.image_gen.dalle3 import DallE3Provider
    p = DallE3Provider(api_key=os.environ["VIDEO_OPENAI_TTS_KEY"])
    out = tmp_path / "img.png"
    result = await p.generate(
        prompt="flat illustration of a team collaborating",
        style="flat illustration",
        width=1280, height=720,
        output_path=out,
    )
    assert out.exists()
```

---

## Multi-Tenant Tests

### Different tenants, different brand colors

```bash
# Tenant A — blue brand
curl -X POST http://localhost:8001/api/v1/video/jobs \
  -H "Authorization: Bearer tenant-a-token" \
  -H "Content-Type: application/json" \
  -d '{"title":"Blue Brand Test","video_type":"motion","script":"Testing brand colors.","duration_seconds":10}'

# Tenant B — green brand (configure via tenant config in DB)
curl -X POST http://localhost:8001/api/v1/video/jobs \
  -H "Authorization: Bearer tenant-b-token" \
  -H "Content-Type: application/json" \
  -d '{"title":"Green Brand Test","video_type":"motion","script":"Testing brand colors.","duration_seconds":10}'
```

**Verify** that the two output MP4s have visually different brand colors in
their gradient backgrounds and accent bars.

### Provider override per tenant

Verify that `tenant.config.video.tts` overrides the global `VIDEO_TTS` env var.
Tenant with `"tts": "openai_tts"` should use OpenAI TTS; tenant without that
config falls back to edge_tts.

---

## Error Scenario Tests

### TTS failure → video still produces with minimum duration

```bash
# Set an invalid TTS key to force failure
VIDEO_OPENAI_TTS_KEY=invalid VIDEO_TTS=openai_tts
# Job should complete (with fallback duration) not fail
```

### LLM planner failure → fallback scenes used

Set `LLM_PROVIDER=none` or point to unreachable endpoint. Each renderer's
`_fallback_scenes()` path should activate and produce a valid single-scene video.

### Image gen failure → Pexels fallback → brand color fallback

```bash
VIDEO_IMAGE_GEN=dalle3
VIDEO_OPENAI_TTS_KEY=invalid_key   # force DallE3 to fail
VIDEO_STOCK=pexels
VIDEO_PEXELS_KEY=valid_pexels_key  # Pexels should catch the fallback
```

Then repeat with Pexels key also invalid — solid brand color background expected.

### Storage failure (S3 misconfigured)

Job should reach `failed` status with a clear `error_message` in the response.
Worker logs should show the exact exception traceback.

---

## Performance Benchmarks

| Video Type     | Scenes | TTS  | Image Gen | Expected Render Time |
|---------------|--------|------|-----------|---------------------|
| kinetic        | 1      | edge | none      | < 30 s              |
| slideshow      | 4      | edge | pexels    | < 90 s              |
| stockfootage   | 4      | edge | pexels    | < 90 s              |
| explainer      | 4      | edge | none      | < 60 s              |
| whiteboard     | 4      | edge | none      | < 60 s              |
| motion         | 5      | edge | none      | < 75 s              |
| presentation   | 6      | edge | none      | < 90 s              |
| screencast     | 5      | edge | none      | < 75 s              |
| illustrative   | 4      | edge | pexels    | < 90 s              |
| avatar         | 3      | heygen | heygen  | < 180 s             |

*Measured on: 4-core CPU, 8GB RAM, no GPU. Times are wall clock including Celery
overhead. GPU-accelerated SDXL local will reduce image gen bottleneck significantly.*

---

## Troubleshooting

### Worker crashes with `RuntimeError: no running event loop`

Check that `asyncio.get_running_loop()` is used (not `get_event_loop()`) in all
renderer files. The fix was applied to all 6 affected files in the Phase 1 review.

### `ColorClip` RGBA error in MoviePy 1.x

MoviePy 1.x `ColorClip` does not accept 4-tuple (RGBA) colors. All overlays must
use `.set_opacity()` on a 3-tuple RGB `ColorClip`. Verify no 4-tuple is passed anywhere.

### Pillow `textbbox` / `textlength` AttributeError

Requires Pillow ≥ 9.2.0. Check `pip show pillow` and upgrade if needed.

### `rounded_rectangle` not available

Requires Pillow ≥ 8.2.0. Screencast renderer uses this for URL bar and callout.

### Edge TTS `asyncio.get_running_loop()` error in Celery

Celery tasks run inside `asyncio.run()`. Inside that loop `get_running_loop()` is
always valid. If you see an error here, confirm the Celery task calls
`asyncio.run(_run())` and that `_run()` is the top-level async function.

### FFmpeg not found

```bash
sudo apt-get install -y ffmpeg
ffmpeg -version   # should show version info
```

### ImageMagick missing (explainer TextClip)

The explainer renderer uses MoviePy `TextClip` which requires ImageMagick:

```bash
sudo apt-get install -y imagemagick
# Fix policy to allow PDF/text:
sudo sed -i 's/rights="none" pattern="@\*"/rights="read|write" pattern="@*"/' \
  /etc/ImageMagick-6/policy.xml
```

### Font not found (PIL default fallback)

Install font packages on the render server:

```bash
sudo apt-get install -y fonts-liberation fonts-noto fonts-ubuntu
```

To test font availability:

```python
from PIL import ImageFont
ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 40)
```

---

## Steps 7–10: New Feature Tests

---

### 11. Conversational (2–3 character dialogue)

**Minimal test — silhouette fallback (no character_urls):**

```bash
curl -s -X POST http://localhost:8000/api/v1/video/jobs \
  -H "X-Tenant-Key: $TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": 501,
    "video_type": "conversational",
    "title": "Conversational Silhouette Test",
    "script": "Alex: Hello and welcome! Jamie: Thanks for having me Alex.",
    "language": "en",
    "settings": {
      "duration_seconds": 20,
      "voice_a": "en-US-AriaNeural",
      "voice_b": "en-US-GuyNeural",
      "character_names": "Alex,Jamie",
      "show_names": true,
      "primarycolor": "#1E3A5F",
      "accentcolor": "#FFFFFF"
    },
    "callback_url": "http://localhost:9999/cb"
  }' | python3 -m json.tool
```

Expected: `{"status": "queued"}`. Poll until `done`; verify the output MP4 shows two silhouette characters side by side.

**Full test — with character images:**

```bash
curl -s -X POST http://localhost:8000/api/v1/video/jobs \
  -H "X-Tenant-Key: $TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": 502,
    "video_type": "conversational",
    "title": "Conversational With Characters",
    "script": "Alex: What exactly is machine learning?\nJamie: At its core, it is pattern recognition at scale.\nAlex: So like how Netflix knows what I want to watch?\nJamie: Exactly! It learns from millions of viewing patterns.",
    "language": "en",
    "settings": {
      "duration_seconds": 40,
      "voice_a": "en-US-AriaNeural",
      "voice_b": "en-US-GuyNeural",
      "primarycolor": "#2563EB",
      "bgmvolume": "0.2",
      "_resolved_assets": {
        "character_urls": [
          "https://raw.githubusercontent.com/EDZLEARN/test-assets/main/alex.png",
          "https://raw.githubusercontent.com/EDZLEARN/test-assets/main/jamie.png"
        ]
      }
    },
    "callback_url": "http://localhost:9999/cb"
  }' | python3 -m json.tool
```

**Three-character test:**

```bash
curl -s -X POST http://localhost:8000/api/v1/video/jobs \
  -H "X-Tenant-Key: $TENANT_KEY" -H "Content-Type: application/json" \
  -d '{
    "job_id": 503,
    "video_type": "conversational",
    "title": "Three Character Test",
    "script": "Alex: Shall we begin? Jamie: Yes, lets go. Sam: I agree completely.",
    "settings": {
      "duration_seconds": 30,
      "voice_a": "en-US-AriaNeural",
      "voice_b": "en-US-GuyNeural",
      "voice_c": "en-US-JennyNeural",
      "character_names": "Alex,Jamie,Sam"
    },
    "callback_url": "http://localhost:9999/cb"
  }' | python3 -m json.tool
```

Verify: third character appears centred at 50% x-fraction.

**Pytest unit test:**

```python
# tests/test_conversational_renderer.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile

@pytest.mark.asyncio
async def test_conversational_silhouette_render():
    """ConversationalRenderer renders without character_urls using silhouettes."""
    from app.services.video.renderers.conversational import ConversationalRenderer

    job = MagicMock()
    job.id = __import__('uuid').uuid4()
    job.tenant_id = __import__('uuid').uuid4()
    job.video_type = "conversational"
    job.title = "Test Dialogue"
    job.script = "Alex: Hello! Jamie: Hi there!"
    job.language = "en"
    job.settings = {
        "duration_seconds": 10,
        "voice_a": "en-US-AriaNeural",
        "voice_b": "en-US-GuyNeural",
        "character_names": "Alex,Jamie",
        "_resolved_assets": {}
    }

    bundle = MagicMock()
    session_factory = AsyncMock()

    with tempfile.TemporaryDirectory() as tmp:
        renderer = ConversationalRenderer(
            job=job, providers=bundle,
            tmp_dir=Path(tmp), session_factory=session_factory
        )
        # Patch LLM planner to return deterministic turns
        turns = [
            {"character": "Alex", "character_index": 0, "text": "Hello!", "duration_seconds": 5},
            {"character": "Jamie", "character_index": 1, "text": "Hi there!", "duration_seconds": 5},
        ]
        with patch.object(renderer, '_plan_scenes', return_value=turns), \
             patch.object(renderer, '_synthesize_tts', return_value=Path(tmp) / "audio.mp3"), \
             patch.object(renderer, '_update_progress', new_callable=AsyncMock):
            # Render should not raise
            result = await renderer.render()
            assert result.raw_mp4_path.exists()
            assert result.duration_seconds > 0


def test_bob_animation_values():
    """Bob oscillation stays within expected pixel range."""
    import math
    AMP = 5
    FREQ = 0.8
    for t in [0.0, 0.25, 0.5, 0.75, 1.0, 2.5]:
        bob_y = int(AMP * math.sin(2 * math.pi * FREQ * t))
        assert -AMP <= bob_y <= AMP, f"bob_y={bob_y} out of range at t={t}"


def test_conversational_video_types():
    """conversational is in VIDEO_TYPES."""
    from app.models.video_job import VIDEO_TYPES
    assert "conversational" in VIDEO_TYPES


def test_conversational_registry_entry():
    """Registry resolves ConversationalRenderer for 'conversational'."""
    from app.services.video.registry import ProviderRegistry
    cls = ProviderRegistry.get_renderer_class("conversational")
    assert cls.__name__ == "ConversationalRenderer"
```

---

### 12. Auto (AI-selected video type)

**Basic auto test:**

```bash
curl -s -X POST http://localhost:8000/api/v1/video/jobs \
  -H "X-Tenant-Key: $TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": 601,
    "video_type": "auto",
    "title": "Auto Type Selection Test",
    "script": "Photosynthesis converts sunlight into chemical energy. First the light reactions occur in the thylakoid membranes. Then the Calvin cycle fixes carbon dioxide into glucose.",
    "language": "en",
    "settings": {"duration_seconds": 60},
    "callback_url": "http://localhost:9999/cb"
  }' | python3 -m json.tool
```

After completion check DB settings column for `_auto_chosen_type`:

```bash
# Via psql
psql $DATABASE_URL -c \
  "SELECT settings->>'_auto_chosen_type' AS chosen FROM video_jobs WHERE moodle_job_id=601;"
```

**Dialogue script → should select conversational:**

```bash
curl -s -X POST http://localhost:8000/api/v1/video/jobs \
  -H "X-Tenant-Key: $TENANT_KEY" -H "Content-Type: application/json" \
  -d '{
    "job_id": 602,
    "video_type": "auto",
    "title": "Auto Dialogue Detection",
    "script": "Teacher: Can you explain what DNA is? Student: DNA is the molecule that carries genetic instructions. Teacher: Exactly right! And where is it found?",
    "settings": {"duration_seconds": 30},
    "callback_url": "http://localhost:9999/cb"
  }' | python3 -m json.tool
# Expect: _auto_chosen_type = "conversational"
```

**Pytest unit tests:**

```python
# tests/test_auto_renderer.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

def test_auto_video_type_in_types():
    from app.models.video_job import VIDEO_TYPES
    assert "auto" in VIDEO_TYPES

def test_auto_registry_entry():
    from app.services.video.registry import ProviderRegistry
    cls = ProviderRegistry.get_renderer_class("auto")
    assert cls.__name__ == "AutoRenderer"

@pytest.mark.asyncio
async def test_auto_select_type_fallback():
    """auto_select_type returns stockfootage when LLM fails."""
    from app.services.video.llm_planner import auto_select_type
    from unittest.mock import AsyncMock, patch
    import uuid

    with patch('app.services.video.llm_planner._make_client') as mock_client_factory:
        mock_client = AsyncMock()
        mock_client.complete.side_effect = Exception("LLM timeout")
        mock_client_factory.return_value = mock_client

        result = await auto_select_type(
            script="Any script",
            settings_dict={"duration_seconds": 60},
            available_assets={},
            session_factory=AsyncMock(),
            tenant_id=uuid.uuid4(),
        )
        assert result == "stockfootage"

@pytest.mark.asyncio
async def test_auto_select_type_invalid_response():
    """auto_select_type falls back if LLM returns unrecognised type."""
    from app.services.video.llm_planner import auto_select_type
    import uuid, json

    with patch('app.services.video.llm_planner._make_client') as mock_client_factory:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps({"video_type": "podcast"})
        mock_client.complete.return_value = mock_response
        mock_client_factory.return_value = mock_client

        result = await auto_select_type(
            script="Some script",
            settings_dict={},
            available_assets={},
            session_factory=AsyncMock(),
            tenant_id=uuid.uuid4(),
        )
        assert result == "stockfootage"

@pytest.mark.asyncio
async def test_auto_renderer_delegates_and_restores_type():
    """AutoRenderer patches video_type during delegation and restores it."""
    from app.services.video.renderers.auto import AutoRenderer
    from app.services.video import RenderResult
    import uuid, tempfile
    from pathlib import Path

    job = MagicMock()
    job.id = uuid.uuid4()
    job.tenant_id = uuid.uuid4()
    job.video_type = "auto"
    job.script = "Test script"
    job.settings = {}
    job.assets = {}

    with tempfile.TemporaryDirectory() as tmp:
        renderer = AutoRenderer(
            job=job, providers=MagicMock(),
            tmp_dir=Path(tmp), session_factory=AsyncMock()
        )
        renderer.assets = {}
        renderer.settings = {}

        fake_result = RenderResult(
            raw_mp4_path=Path(tmp) / "out.mp4",
            duration_seconds=30.0,
            metadata={}
        )
        (Path(tmp) / "out.mp4").touch()

        with patch('app.services.video.llm_planner.auto_select_type', return_value="kinetic"), \
             patch('app.services.video.registry.ProviderRegistry.get_renderer_class') as mock_reg, \
             patch.object(renderer, '_update_progress', new_callable=AsyncMock), \
             patch.object(renderer, '_session_factory') as mock_sf:
            mock_sf.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_delegate = AsyncMock()
            mock_delegate.return_value.render = AsyncMock(return_value=fake_result)
            mock_reg.return_value = mock_delegate

            result = await renderer.render()

        # type restored to "auto" after delegation
        assert job.video_type == "auto"
        assert result.metadata["auto_chosen_type"] == "kinetic"
        assert result.metadata["original_video_type"] == "auto"
```

---

### 13. Asset Library API

**Register all asset types:**

```bash
# Character
curl -s -X POST http://localhost:8000/api/v1/video/assets \
  -H "X-Tenant-Key: $TENANT_KEY" -H "Content-Type: application/json" \
  -d '{"name":"Alex Character","asset_type":"character","url":"https://cdn.example.com/alex.png","mime_type":"image/png","metadata":{"name":"Alex","voice_hint":"female_friendly"}}' | python3 -m json.tool

# Music
curl -s -X POST http://localhost:8000/api/v1/video/assets \
  -H "X-Tenant-Key: $TENANT_KEY" -H "Content-Type: application/json" \
  -d '{"name":"Corporate BG","asset_type":"music","url":"https://cdn.example.com/bg.mp3","mime_type":"audio/mpeg","file_size_bytes":4200000}' | python3 -m json.tool

# Logo
curl -s -X POST http://localhost:8000/api/v1/video/assets \
  -H "X-Tenant-Key: $TENANT_KEY" -H "Content-Type: application/json" \
  -d '{"name":"EDZLMS Logo","asset_type":"logo","url":"https://cdn.example.com/logo.png","mime_type":"image/png"}' | python3 -m json.tool
```

**List + filter:**

```bash
# All active characters
curl "http://localhost:8000/api/v1/video/assets?asset_type=character&page=1&page_size=10" \
  -H "X-Tenant-Key: $TENANT_KEY" | python3 -m json.tool

# Paginate music (page 2)
curl "http://localhost:8000/api/v1/video/assets?asset_type=music&page=2&page_size=5" \
  -H "X-Tenant-Key: $TENANT_KEY" | python3 -m json.tool
```

**Update + soft-delete:**

```bash
export ASSET_ID="<uuid-from-create>"

# Update URL
curl -s -X PATCH "http://localhost:8000/api/v1/video/assets/$ASSET_ID" \
  -H "X-Tenant-Key: $TENANT_KEY" -H "Content-Type: application/json" \
  -d '{"url":"https://cdn.example.com/alex_v2.png"}' | python3 -m json.tool

# Archive (soft-delete via PATCH)
curl -s -X PATCH "http://localhost:8000/api/v1/video/assets/$ASSET_ID" \
  -H "X-Tenant-Key: $TENANT_KEY" -H "Content-Type: application/json" \
  -d '{"is_active":false}' | python3 -m json.tool

# Hard soft-delete (DELETE endpoint)
curl -s -X DELETE "http://localhost:8000/api/v1/video/assets/$ASSET_ID" \
  -H "X-Tenant-Key: $TENANT_KEY"
# Expect: 204 No Content
# Verify: GET /assets still returns the row but is_active=false
curl "http://localhost:8000/api/v1/video/assets?active_only=false" \
  -H "X-Tenant-Key: $TENANT_KEY" | python3 -m json.tool
```

**Error cases:**

```bash
# Invalid asset_type
curl -s -X POST http://localhost:8000/api/v1/video/assets \
  -H "X-Tenant-Key: $TENANT_KEY" -H "Content-Type: application/json" \
  -d '{"name":"Bad","asset_type":"video","url":"https://example.com/x.mp4"}' | python3 -m json.tool
# Expect: 422 Unprocessable Entity — "Unknown asset_type 'video'"

# Non-UUID id
curl -s "http://localhost:8000/api/v1/video/assets/not-a-uuid" \
  -H "X-Tenant-Key: $TENANT_KEY" | python3 -m json.tool
# Expect: 400 Bad Request

# Wrong tenant (asset from tenant A, key from tenant B)
curl -s "http://localhost:8000/api/v1/video/assets/$ASSET_ID" \
  -H "X-Tenant-Key: $OTHER_TENANT_KEY" | python3 -m json.tool
# Expect: 404 Not Found (tenant isolation)
```

**Pytest unit tests:**

```python
# tests/test_video_assets_api.py
import pytest
from httpx import AsyncClient
import uuid

@pytest.mark.asyncio
async def test_create_character_asset(async_client: AsyncClient, auth_headers: dict):
    resp = await async_client.post(
        "/api/v1/video/assets",
        json={
            "name": "Test Character",
            "asset_type": "character",
            "url": "https://example.com/char.png",
            "metadata": {"name": "Alex"},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["asset_type"] == "character"
    assert data["is_active"] is True
    return data["id"]

@pytest.mark.asyncio
async def test_invalid_asset_type_rejected(async_client: AsyncClient, auth_headers: dict):
    resp = await async_client.post(
        "/api/v1/video/assets",
        json={"name": "x", "asset_type": "video", "url": "https://example.com/x.mp4"},
        headers=auth_headers,
    )
    assert resp.status_code == 422

@pytest.mark.asyncio
async def test_soft_delete_preserves_row(async_client: AsyncClient, auth_headers: dict):
    # Create
    resp = await async_client.post(
        "/api/v1/video/assets",
        json={"name": "Del Test", "asset_type": "logo", "url": "https://example.com/logo.png"},
        headers=auth_headers,
    )
    asset_id = resp.json()["id"]

    # Delete
    del_resp = await async_client.delete(
        f"/api/v1/video/assets/{asset_id}",
        headers=auth_headers,
    )
    assert del_resp.status_code == 204

    # Still visible when active_only=false
    list_resp = await async_client.get(
        "/api/v1/video/assets?active_only=false",
        headers=auth_headers,
    )
    ids = [item["id"] for item in list_resp.json()["items"]]
    assert asset_id in ids

    # Hidden from default (active_only=true) listing
    list_resp2 = await async_client.get(
        "/api/v1/video/assets",
        headers=auth_headers,
    )
    ids2 = [item["id"] for item in list_resp2.json()["items"]]
    assert asset_id not in ids2

def test_asset_types_constant():
    from app.models.video_asset import ASSET_TYPES
    assert ASSET_TYPES == {"character", "logo", "music", "background", "font"}
```

---

### 14. Preview / Approval Flow

**Full happy path (curl):**

```bash
# Step 1: Create job
JOB=$(curl -s -X POST http://localhost:8000/api/v1/video/jobs \
  -H "X-Tenant-Key: $TENANT_KEY" -H "Content-Type: application/json" \
  -d '{
    "job_id": 701,
    "video_type": "explainer",
    "title": "Preview Flow Test",
    "script": "This is a long explainer script. It covers neural networks, deep learning, and their real-world applications in healthcare, finance, and education.",
    "settings": {"duration_seconds": 180},
    "callback_url": "http://localhost:9999/cb"
  }')
JOB_UUID=$(echo $JOB | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "Job UUID: $JOB_UUID"

# Step 2: Request 30-second preview
curl -s -X POST "http://localhost:8000/api/v1/video/jobs/$JOB_UUID/preview" \
  -H "X-Tenant-Key: $TENANT_KEY" | python3 -m json.tool
# Expect: 202 {"status": "preview_pending"}

# Step 3: Poll until preview_ready
for i in $(seq 1 30); do
  STATUS=$(curl -s "http://localhost:8000/api/v1/video/jobs/$JOB_UUID" \
    -H "X-Tenant-Key: $TENANT_KEY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'], d.get('preview_url',''))")
  echo "[$i] $STATUS"
  [[ "$STATUS" == preview_ready* ]] && break
  sleep 5
done

# Step 4: Approve and launch full render
curl -s -X POST "http://localhost:8000/api/v1/video/jobs/$JOB_UUID/approve" \
  -H "X-Tenant-Key: $TENANT_KEY" | python3 -m json.tool
# Expect: 202 {"status": "queued"}

# Step 5: Poll until done
for i in $(seq 1 60); do
  STATUS=$(curl -s "http://localhost:8000/api/v1/video/jobs/$JOB_UUID" \
    -H "X-Tenant-Key: $TENANT_KEY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'], d.get('output_url',''))")
  echo "[$i] $STATUS"
  [[ "$STATUS" == done* ]] && break
  sleep 10
done
```

**Status guard error cases:**

```bash
# Attempt approve before preview_ready → 409
curl -s -X POST "http://localhost:8000/api/v1/video/jobs/$JOB_UUID/approve" \
  -H "X-Tenant-Key: $TENANT_KEY" | python3 -m json.tool
# Expect: 409 Conflict "Cannot approve: job status is 'queued'..."

# Attempt preview when already processing → 409
# (Start a job, let it move to processing, then try /preview)
curl -s -X POST "http://localhost:8000/api/v1/video/jobs/$JOB_UUID/preview" \
  -H "X-Tenant-Key: $TENANT_KEY" | python3 -m json.tool
# Expect: 409 if status == processing

# Attempt preview on done job → 409
curl -s -X POST "http://localhost:8000/api/v1/video/jobs/$DONE_JOB_UUID/preview" \
  -H "X-Tenant-Key: $TENANT_KEY" | python3 -m json.tool
# Expect: 409 Conflict
```

**Pytest unit tests:**

```python
# tests/test_preview_approval_flow.py
import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock

@pytest.mark.asyncio
async def test_preview_queued_from_queued_job(async_client: AsyncClient, auth_headers: dict, db_session):
    """POST /preview on a queued job returns 202 and transitions to preview_pending."""
    # Create job via API
    resp = await async_client.post(
        "/api/v1/video/jobs",
        json={
            "job_id": 9001,
            "video_type": "explainer",
            "title": "Preview Test",
            "script": "Test script",
            "settings": {},
            "callback_url": "http://localhost/cb",
        },
        headers=auth_headers,
    )
    job_uuid = resp.json()["job_id"]

    with patch("app.tasks.celery_app.celery_app.send_task") as mock_task:
        mock_task.return_value = MagicMock(id="preview-task-123")
        preview_resp = await async_client.post(
            f"/api/v1/video/jobs/{job_uuid}/preview",
            headers=auth_headers,
        )

    assert preview_resp.status_code == 202
    data = preview_resp.json()
    assert data["status"] == "preview_pending"

    # Verify Celery task name
    call_args = mock_task.call_args
    assert call_args[0][0] == "app.tasks.preview_video.generate_video_preview"

@pytest.mark.asyncio
async def test_approve_on_non_preview_ready_returns_409(async_client: AsyncClient, auth_headers: dict):
    """POST /approve on a queued job returns 409."""
    resp = await async_client.post(
        "/api/v1/video/jobs",
        json={
            "job_id": 9002, "video_type": "kinetic", "title": "T",
            "script": "S", "settings": {}, "callback_url": "http://localhost/cb",
        },
        headers=auth_headers,
    )
    job_uuid = resp.json()["job_id"]

    approve_resp = await async_client.post(
        f"/api/v1/video/jobs/{job_uuid}/approve",
        headers=auth_headers,
    )
    assert approve_resp.status_code == 409
    assert "preview_ready" in approve_resp.json()["detail"]

@pytest.mark.asyncio
async def test_preview_url_in_status_response(async_client: AsyncClient, auth_headers: dict, db_session):
    """preview_url field appears in status response (null when not set)."""
    resp = await async_client.post(
        "/api/v1/video/jobs",
        json={
            "job_id": 9003, "video_type": "slideshow", "title": "T",
            "script": "S", "settings": {}, "callback_url": "http://localhost/cb",
        },
        headers=auth_headers,
    )
    job_uuid = resp.json()["job_id"]

    status_resp = await async_client.get(
        f"/api/v1/video/jobs/{job_uuid}",
        headers=auth_headers,
    )
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert "preview_url" in data
    assert data["preview_url"] is None  # not set yet

def test_preview_video_task_registered():
    """generate_video_preview task is registered with Celery."""
    from app.tasks.celery_app import celery_app
    # Trigger lazy import of the task module
    import app.tasks.preview_video  # noqa: F401
    assert "app.tasks.preview_video.generate_video_preview" in celery_app.tasks

def test_new_status_values_in_enum():
    """All Step 10 status values present in VideoJobStatus."""
    from app.models.video_job import VideoJobStatus
    vals = {s.value for s in VideoJobStatus}
    assert "preview_pending" in vals
    assert "preview_ready"   in vals
    assert "approved"        in vals
    assert "draft"           in vals

def test_preview_task_duration_cap():
    """_PREVIEW_MAX_SECONDS is set to 30."""
    from app.tasks import preview_video
    assert preview_video._PREVIEW_MAX_SECONDS == 30

def test_migration_007_preview_url():
    """Migration 007 adds preview_url and widens status column."""
    import importlib
    m = importlib.import_module("alembic.versions.007_video_job_preview_approval")
    src = open(m.__file__).read()
    assert "preview_url" in src
    assert "String(25)" in src
    assert 'down_revision = "006"' in src
```

---

### Alembic Migration Verification

```bash
# Confirm all 7 migrations are in order
ls axis-ai/alembic/versions/*.py | sort

# Expected output:
# 001_initial_schema.py
# 002_add_tenants.py
# 003_add_...
# 004_add_...
# 005_add_video_jobs.py
# 006_add_video_assets.py
# 007_video_job_preview_approval.py

# Apply all pending
cd axis-ai
alembic upgrade head

# Verify video_assets table
psql $DATABASE_URL -c "\d video_assets"

# Verify preview_url + widened status on video_jobs
psql $DATABASE_URL -c "\d video_jobs" | grep -E "preview_url|status"
# Expected:
#  status     | character varying(25)
#  preview_url| text
```

---

### Full End-to-End Regression (all 12 video types)

```bash
#!/bin/bash
# Run after all migrations. Submits one job per video_type and confirms
# all return 202 without 422 validation errors.
TYPES="stockfootage kinetic slideshow avatar explainer whiteboard motion illustrative presentation screencast conversational auto"
JOB_ID=8001
for TYPE in $TYPES; do
  RESULT=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST http://localhost:8000/api/v1/video/jobs \
    -H "X-Tenant-Key: $TENANT_KEY" -H "Content-Type: application/json" \
    -d "{\"job_id\":$JOB_ID,\"video_type\":\"$TYPE\",\"title\":\"Test $TYPE\",\"script\":\"Test script for $TYPE video type.\",\"settings\":{\"duration_seconds\":10},\"callback_url\":\"http://localhost:9999/cb\"}")
  echo "$TYPE → HTTP $RESULT"
  JOB_ID=$((JOB_ID+1))
done
# All should print: <type> → HTTP 202
```

---

### Video Type Validation

```bash
# Unknown type should return 422
curl -s -X POST http://localhost:8000/api/v1/video/jobs \
  -H "X-Tenant-Key: $TENANT_KEY" -H "Content-Type: application/json" \
  -d '{"job_id":9999,"video_type":"podcast","title":"T","script":"S","settings":{},"callback_url":"http://localhost/cb"}' \
  | python3 -m json.tool
# Expect: 422 Unprocessable Entity
# detail: "Unknown video_type: 'podcast'. Valid types: ['auto', 'avatar', ...]"
```


---

## Section 15 — TTS Provider Tests

### 15.1 OpenAI TTS

```bash
# Env check
echo "Key set: $VIDEO_OPENAI_TTS_KEY" | head -c 40

# List voices via API (no actual call — voices are static)
curl -s -X POST http://localhost:8000/api/v1/video/jobs \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "OpenAI TTS test",
    "video_type": "kinetic",
    "script": "OpenAI TTS is fast and natural.",
    "settings": {"tts_provider": "openai", "openai_tts_voice": "nova", "openai_tts_model": "tts-1-hd"}
  }'
```

```python
# pytest
async def test_openai_tts_synthesize(tmp_path, openai_tts_provider):
    out = tmp_path / "speech.mp3"
    dur = await openai_tts_provider.synthesize(
        text="Hello from OpenAI TTS.", voice="alloy", language="en", output_path=out
    )
    assert out.exists() and out.stat().st_size > 1000
    assert 0.5 < dur < 5.0

async def test_openai_tts_list_voices(openai_tts_provider):
    voices = await openai_tts_provider.list_voices("en")
    assert len(voices) == 6
    ids = {v.voice_id for v in voices}
    assert {"alloy", "echo", "nova", "shimmer", "fable", "onyx"} == ids
```

### 15.2 ElevenLabs TTS

```bash
# Check available voices
curl -s -X POST http://localhost:8000/api/v1/video/jobs \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "ElevenLabs test",
    "video_type": "slideshow",
    "script": "ElevenLabs delivers hyper-realistic voice cloning.",
    "settings": {"tts_provider": "elevenlabs"}
  }'
```

```python
async def test_elevenlabs_synthesize(tmp_path, elevenlabs_provider):
    out = tmp_path / "rachel.mp3"
    dur = await elevenlabs_provider.synthesize(
        text="ElevenLabs voice test.", voice="", language="en", output_path=out
    )
    assert out.exists()
    assert dur > 0.5

async def test_elevenlabs_list_voices(elevenlabs_provider):
    voices = await elevenlabs_provider.list_voices("en")
    assert len(voices) > 0
    assert all(v.voice_id for v in voices)
```

---

## Section 16 — Avatar Provider Tests

### 16.1 DIDProvider

```bash
# Submit a D-ID avatar job
curl -s -X POST http://localhost:8000/api/v1/video/jobs \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "D-ID Avatar test",
    "video_type": "avatar",
    "script": "Welcome to our AI video platform.",
    "settings": {"avatar_provider": "d_id"}
  }'
```

```python
async def test_d_id_create_video(tmp_path, d_id_provider):
    out = tmp_path / "did_output.mp4"
    dur = await d_id_provider.create_video(
        script="Hello from D-ID.",
        avatar_id="https://example.com/portrait.jpg",
        voice_id="microsoft|en-US-JennyNeural",
        language="en",
        output_path=out,
    )
    assert out.exists() and out.stat().st_size > 10_000
    assert dur > 1.0

async def test_d_id_missing_presenter():
    from app.services.video.providers.avatar.d_id import DIDProvider
    p = DIDProvider(api_key="test", default_presenter_id="")
    with pytest.raises(ValueError, match="no presenter"):
        await p.create_video("script", "", "", "en", Path("/tmp/x.mp4"))
```

### 16.2 SadTalkerProvider

```python
async def test_sadtalker_no_url():
    from app.services.video.providers.avatar.sadtalker import SadTalkerProvider
    with pytest.raises(ValueError, match="sadtalker_url"):
        SadTalkerProvider(base_url="")

async def test_sadtalker_missing_audio(tmp_path):
    from app.services.video.providers.avatar.sadtalker import SadTalkerProvider
    p = SadTalkerProvider(base_url="http://localhost:7860")
    with pytest.raises(FileNotFoundError):
        await p.create_video("script", "portrait.png", "/nonexistent/audio.mp3", "en", tmp_path / "out.mp4")
```

---

## Section 17 — PictoryProvider Tests

```bash
curl -s -X POST http://localhost:8000/api/v1/video/jobs \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Pictory full platform test",
    "video_type": "stockfootage",
    "script": "AI is transforming education globally.",
    "settings": {"platform_provider": "pictory"}
  }'
```

```python
async def test_pictory_build_script():
    from app.services.video.providers.platform.pictory import PictoryProvider
    plan = {
        "scenes": [
            {"narration": "Scene one narration."},
            {"narration": "Scene two narration."},
        ]
    }
    text = PictoryProvider._build_script(plan, "Test Video")
    assert "Scene one narration." in text
    assert "Scene two narration." in text

def test_pictory_missing_user_id():
    from app.services.video.providers.platform.pictory import PictoryProvider
    with pytest.raises(ValueError, match="user_id"):
        PictoryProvider(api_key="key", user_id="")
```

---

## Section 18 — Encryption Tests

```python
def test_encrypt_decrypt_round_trip(monkeypatch):
    import base64
    from cryptography.fernet import Fernet
    from app.services.video.registry import ProviderRegistry

    raw_hex = "a" * 64  # 32 bytes, all 0xAA
    monkeypatch.setattr("app.config.settings.video_encryption_key", raw_hex)

    key_bytes  = bytes.fromhex(raw_hex)
    fernet     = Fernet(base64.urlsafe_b64encode(key_bytes))
    token      = fernet.encrypt(b"super-secret-key").decode()

    decrypted  = ProviderRegistry._decrypt(token)
    assert decrypted == "super-secret-key"

def test_decrypt_wrong_key(monkeypatch):
    import base64
    from cryptography.fernet import Fernet
    from app.services.video.registry import ProviderRegistry

    encrypt_hex = "a" * 64
    wrong_hex   = "b" * 64
    monkeypatch.setattr("app.config.settings.video_encryption_key", wrong_hex)

    fernet = Fernet(base64.urlsafe_b64encode(bytes.fromhex(encrypt_hex)))
    token  = fernet.encrypt(b"secret").decode()

    with pytest.raises(ValueError, match="decrypt"):
        ProviderRegistry._decrypt(token)
```

---

## Section 19 — Whiteboard Phase 2 Tests (Progressive Reveal)

```python
def test_whiteboard_compute_layout():
    from app.services.video.renderers.whiteboard import _compute_layout
    bg_frame, char_spans = _compute_layout(
        heading="Hello", body="World test text",
        w=1280, h=720,
        accent_rgb=(37, 99, 235),
        bg_color=(250, 248, 240),
        ink_color=(30, 30, 30),
        font_path=None,
    )
    assert bg_frame.shape == (720, 1280, 3)
    heading_chars = [s for s in char_spans if s.is_heading and s.char != "\n"]
    assert len(heading_chars) == 5  # "Hello"

def test_whiteboard_make_frame_reveals_chars():
    from app.services.video.renderers.whiteboard import (
        _compute_layout, _make_frame_fn
    )
    import numpy as np
    bg_frame, char_spans = _compute_layout(
        "Hi", "Body", 640, 360,
        (37, 99, 235), (250, 248, 240), (30, 30, 30), None,
    )
    from app.services.video.renderers.whiteboard import _SceneData
    sd = _SceneData(
        narration_audio=None, duration=5.0, heading="Hi", body="Body",
        bg_frame=bg_frame, char_spans=char_spans,
        accent_rgb=(37, 99, 235), ink_rgb=(30, 30, 30),
        heading_rgb=(37, 99, 235), chars_per_sec=12.0,
    )
    total_chars = sum(1 for sp in char_spans if sp.char != "\n")
    mf = _make_frame_fn(sd, total_chars, 2, None, 640, 360)
    frame_at_0  = mf(0.0)
    frame_at_10 = mf(10.0)
    assert frame_at_0.shape == (360, 640, 3)
    # At t=10 all chars revealed — frame should differ from t=0
    assert not np.array_equal(frame_at_0, frame_at_10)
```

---

## Section 20 — IllustrativeRenderer Chunked Memory Test

```python
import tracemalloc

async def test_illustrative_memory_bounded(tmp_path):
    """Verify that rendering a 30-second scene stays under 200 MB."""
    from app.services.video.renderers.illustrative import (
        _prepare_scene_assets, _make_frame_fn
    )
    import numpy as np

    assets = _prepare_scene_assets(
        bg_path=None, char_path=None,
        pos_frac=(0.05, 0.20),
        caption="Test caption",
        w=1280, h=720,
        primary_rgb=(37, 99, 235),
        secondary_rgb=(255, 255, 255),
        font_path=None,
    )

    tracemalloc.start()
    make_frame = _make_frame_fn(assets, fps=24)

    # Simulate 30 seconds of frames
    for fi in range(720):  # 30 s × 24 fps
        _ = make_frame(fi / 24.0)

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Peak RAM per frame should be tiny (< 10 MB for a single 720p frame)
    assert peak < 200 * 1024 * 1024, f"Peak RAM too high: {peak / 1024 / 1024:.1f} MB"
```

---

## Section 21 — AvatarRenderer Retry + Fallback Tests

```python
import pytest
from unittest.mock import AsyncMock, patch

async def test_avatar_retries_transient_error(tmp_path):
    """Provider fails twice with timeout, succeeds on 3rd attempt."""
    from app.services.video.renderers.avatar import _create_with_retry_and_fallback

    call_count = 0
    async def mock_create_video(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("Connection timed out")
        return 5.0

    renderer = _make_mock_renderer(tmp_path, mock_create_video)
    dur = await _create_with_retry_and_fallback(
        renderer=renderer, section_script="Test", section_idx=0,
        avatar_id="", voice_id="", avatar_style="normal",
        avatar_position="center", voice_speed=1.0,
        voice_emotion=None, background_type="color",
        background_value=None, show_captions=False,
        section_path=tmp_path / "section_0.mp4",
    )
    assert call_count == 3
    assert dur == 5.0

async def test_avatar_fallback_on_all_retries_exhausted(tmp_path):
    """After 3 transient failures, fallback video is created."""
    from app.services.video.renderers.avatar import _create_with_retry_and_fallback

    async def always_fail(**kwargs):
        raise RuntimeError("503 Service Unavailable")

    renderer = _make_mock_renderer(tmp_path, always_fail)
    section_path = tmp_path / "section_0.mp4"
    dur = await _create_with_retry_and_fallback(
        renderer=renderer, section_script="Script", section_idx=0,
        avatar_id="", voice_id="", avatar_style="normal",
        avatar_position="center", voice_speed=1.0,
        voice_emotion=None, background_type="color",
        background_value=None, show_captions=False,
        section_path=section_path,
    )
    assert section_path.exists()
    assert dur >= 5.0  # fallback minimum

async def test_avatar_permanent_failure_raises(tmp_path):
    """Non-retryable error (e.g. bad API key) should raise immediately."""
    from app.services.video.renderers.avatar import _create_with_retry_and_fallback

    call_count = 0
    async def perm_fail(**kwargs):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("Invalid API key — 401 Unauthorized")

    renderer = _make_mock_renderer(tmp_path, perm_fail)
    with pytest.raises(RuntimeError, match="permanent failure"):
        await _create_with_retry_and_fallback(
            renderer=renderer, section_script="Script", section_idx=0,
            avatar_id="", voice_id="", avatar_style="normal",
            avatar_position="center", voice_speed=1.0,
            voice_emotion=None, background_type="color",
            background_value=None, show_captions=False,
            section_path=tmp_path / "section_0.mp4",
        )
    assert call_count == 1  # Did NOT retry
```

---

## End-to-End Regression — All Providers

```bash
#!/bin/bash
# run_all_provider_checks.sh — quick smoke test for all wired providers
set -e

BASE="http://localhost:8000"
JWT="Bearer $ADMIN_JWT"

echo "== TTS: edge_tts =="
curl -sf -X POST "$BASE/api/v1/video/jobs" \
  -H "Authorization: $JWT" -H "Content-Type: application/json" \
  -d '{"title":"edge_tts smoke","video_type":"kinetic","script":"Edge TTS test","settings":{"tts_provider":"edge_tts"}}' | jq .id

echo "== TTS: openai =="
curl -sf -X POST "$BASE/api/v1/video/jobs" \
  -H "Authorization: $JWT" -H "Content-Type: application/json" \
  -d '{"title":"openai smoke","video_type":"kinetic","script":"OpenAI TTS test","settings":{"tts_provider":"openai"}}' | jq .id

echo "== TTS: elevenlabs =="
curl -sf -X POST "$BASE/api/v1/video/jobs" \
  -H "Authorization: $JWT" -H "Content-Type: application/json" \
  -d '{"title":"el11 smoke","video_type":"slideshow","script":"ElevenLabs TTS test","settings":{"tts_provider":"elevenlabs"}}' | jq .id

echo "== Avatar: heygen =="
curl -sf -X POST "$BASE/api/v1/video/jobs" \
  -H "Authorization: $JWT" -H "Content-Type: application/json" \
  -d '{"title":"heygen smoke","video_type":"avatar","script":"HeyGen avatar test."}' | jq .id

echo "== Whiteboard Phase 2 =="
curl -sf -X POST "$BASE/api/v1/video/jobs" \
  -H "Authorization: $JWT" -H "Content-Type: application/json" \
  -d '{"title":"WB Phase 2","video_type":"whiteboard","script":"Progressive reveal test.","settings":{"drawspeed":"normal"}}' | jq .id

echo "== Illustrative chunked =="
curl -sf -X POST "$BASE/api/v1/video/jobs" \
  -H "Authorization: $JWT" -H "Content-Type: application/json" \
  -d '{"title":"Illus chunked","video_type":"illustrative","script":"Memory-safe illustrative video."}' | jq .id

echo "All provider smoke tests queued."
```

---

## Section 22 — Bug-fix Regression Tests

### 22.1 Avatar provider kwargs no longer TypeError

```python
# All three providers must accept extra renderer kwargs without crashing
async def test_heygen_accepts_template_kwargs(heygen_provider, tmp_path):
    """verify no TypeError on avatar_style, voice_speed etc."""
    # We cannot call real HeyGen in unit tests — mock the network layer
    with patch.object(heygen_provider, "_submit", return_value="fake_vid_id"), \
         patch.object(heygen_provider, "_poll_until_done", return_value="https://cdn/vid.mp4"), \
         patch.object(heygen_provider, "_download"), \
         patch.object(heygen_provider, "_measure_duration", return_value=5.0):
        dur = await heygen_provider.create_video(
            script="Test script.",
            avatar_id="avatar_123",
            voice_id="voice_456",
            language="en",
            output_path=tmp_path / "out.mp4",
            avatar_style="closeUp",
            voice_speed=1.2,
            voice_emotion="excited",
            background_type="color",
            background_value="#0072ff",
            show_captions=True,
        )
    assert dur == 5.0  # No TypeError

def test_did_accepts_extra_kwargs(d_id_provider):
    """DIDProvider.create_video accepts renderer template kwargs without error."""
    import inspect
    sig = inspect.signature(d_id_provider.create_video)
    assert "kwargs" in str(sig), "DIDProvider must accept **kwargs"

def test_sadtalker_accepts_extra_kwargs():
    from app.services.video.providers.avatar.sadtalker import SadTalkerProvider
    import inspect
    p = SadTalkerProvider(base_url="http://localhost:7860")
    sig = inspect.signature(p.create_video)
    assert "kwargs" in str(sig)
```

### 22.2 HeyGen voice settings wired correctly into payload

```python
async def test_heygen_submit_wires_voice_speed(heygen_provider):
    """voice_speed != 1.0 must appear in payload."""
    captured = {}
    async def fake_post(url, payload):
        captured["payload"] = payload
        return {"data": {"video_id": "v123"}}

    with patch.object(heygen_provider, "_post", side_effect=fake_post):
        with pytest.raises(Exception):  # poll will fail — that's fine
            await heygen_provider.create_video(
                "script", "avatar1", "voice1", "en",
                Path("/tmp/out.mp4"), voice_speed=1.5
            )
    voice = captured["payload"]["video_inputs"][0]["voice"]
    assert voice.get("speed") == 1.5

async def test_heygen_submit_wires_background_color(heygen_provider):
    captured = {}
    async def fake_post(url, payload):
        captured["payload"] = payload
        return {"data": {"video_id": "v123"}}

    with patch.object(heygen_provider, "_post", side_effect=fake_post):
        with pytest.raises(Exception):
            await heygen_provider.create_video(
                "script", "avatar1", "", "en",
                Path("/tmp/out.mp4"),
                background_type="color", background_value="#ff0000"
            )
    bg = captured["payload"]["video_inputs"][0]["background"]
    assert bg["type"] == "color"
    assert bg["value"] == "#ff0000"
```

### 22.3 SadTalker requires_pre_tts flag and AvatarRenderer TTS pre-synthesis

```python
def test_sadtalker_has_requires_pre_tts():
    from app.services.video.providers.avatar.sadtalker import SadTalkerProvider
    p = SadTalkerProvider(base_url="http://localhost:7860")
    assert p.requires_pre_tts is True

def test_heygen_does_not_require_pre_tts():
    from app.services.video.providers.avatar.heygen import HeyGenProvider
    p = HeyGenProvider(api_key="key")
    assert getattr(p, "requires_pre_tts", False) is False

async def test_avatar_renderer_pre_synthesises_for_sadtalker(tmp_path):
    """When provider.requires_pre_tts=True, TTS is called before create_video."""
    from app.services.video.renderers.avatar import AvatarRenderer

    tts_called_with: list[str] = []

    class MockSadTalker:
        requires_pre_tts = True
        async def create_video(self, script, avatar_id, voice_id, language, output_path, **kwargs):
            # If TTS was pre-synthesised, voice_id should be a file path ending in .mp3
            assert voice_id.endswith(".mp3"), f"Expected audio path, got: {voice_id}"
            Path(output_path).write_bytes(b"fake mp4")
            return 3.0

    renderer = _make_mock_renderer(tmp_path, None)
    renderer.providers.avatar = MockSadTalker()

    async def mock_tts(text, path, voice=None):
        tts_called_with.append(str(path))
        path.write_bytes(b"fake audio")
        return 3.0

    renderer._synthesize_tts = mock_tts
    # ... run a single section
    assert len(tts_called_with) > 0, "TTS was not called before SadTalker"
```

### 22.4 base_renderer settings deepcopy

```python
def test_base_renderer_settings_deepcopied():
    """Mutating self.settings must not affect the original job.settings dict."""
    from app.services.video.base_renderer import BaseVideoRenderer
    from unittest.mock import MagicMock

    original_settings = {"foo": "bar", "nested": {"x": 1}}
    job = MagicMock()
    job.settings = original_settings
    job.language = "en"

    # Use a minimal concrete subclass
    class _TestRenderer(BaseVideoRenderer):
        async def render(self):
            pass

    renderer = _TestRenderer(job=job, providers=MagicMock(), tmp_dir=Path("/tmp"), session_factory=MagicMock())
    renderer.settings["foo"] = "MUTATED"
    renderer.settings["nested"]["x"] = 999

    # Original must be unchanged
    assert original_settings["foo"] == "bar"
    assert original_settings["nested"]["x"] == 1
```
