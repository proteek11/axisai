# AXIS AI Video Builder — FastAPI Developer Guide

Complete reference for the AXIS AI video creation service: architecture, all 10
video types, provider configuration, API usage, and deployment.

---

## Architecture Overview

```
Moodle Plugin / NextJS Frontend
         │  REST (JWT)
         ▼
   FastAPI  (port 8001)
   app/api/v1/video/
         │
         ├─ POST /jobs         ← create render job
         ├─ GET  /jobs/{id}    ← poll progress
         ├─ GET  /jobs         ← list jobs
         └─ GET  /assets       ← list rendered videos per content item
         │
         ▼
   Celery Worker  (queue: video_render)
   app/tasks/render_video.py
         │
         ├─ ProviderRegistry  → resolves TTS / Avatar / ImageGen / Stock providers
         ├─ LLMPlanner        → breaks script into typed scene dicts
         └─ Renderer          → one of 10 renderer classes
                   │
                   ▼
             raw.mp4  →  FFmpeg post-process  →  S3 / local storage
                                                       │
                                                  Thumbnail
```

### Data Flow

1. API receives `POST /jobs` → creates `VideoJob` row (status=`queued`), enqueues
   Celery task.
2. Celery worker picks up task → resolves providers from tenant config → runs
   `renderer.render()` → reports progress via DB updates.
3. Renderer calls LLM planner to break script into scenes → synthesizes TTS per
   scene → renders frames (Pillow) or fetches media (Pexels/AI gen) → assembles
   with MoviePy → writes raw.mp4.
4. Post-processing: FFmpeg watermark/trim → upload to S3 → generate thumbnail →
   update job status to `completed`.
5. API response on poll includes signed video URL + thumbnail URL.

---

## Directory Structure

```
axis-ai/app/services/video/
├── __init__.py                   # RenderResult dataclass
├── base_renderer.py              # BaseVideoRenderer abstract class
├── ffmpeg_gate.py                # FFmpeg availability check + post-process
├── llm_planner.py                # LLMScenePlanner + per-type fallback scenes
├── registry.py                   # ProviderRegistry — resolves all providers
├── storage.py                    # StorageBackend (S3 + local)
├── thumbnail.py                  # ThumbnailGenerator (FFmpeg + Pillow)
├── renderers/
│   ├── kinetic.py                # Phase 1 — Kinetic typography
│   ├── slideshow.py              # Phase 1 — Photo slideshow
│   ├── stockfootage.py           # Phase 1 — Stock footage + narration
│   ├── avatar.py                 # Phase 1 — HeyGen/Synthesia avatar
│   ├── explainer.py              # Phase 2 — AI-illustrated explainer
│   ├── whiteboard.py             # Phase 2 — Whiteboard animation
│   ├── motion.py                 # Phase 2 — Motion graphics slides
│   ├── illustrative.py           # Phase 2 — Character + background
│   ├── presentation.py           # Phase 2 — PowerPoint-style deck
│   └── screencast.py             # Phase 2 — Tutorial / IDE screencast
└── providers/
    ├── base.py                   # Abstract provider interfaces
    ├── tts/
    │   ├── edge_tts.py           # Free: Microsoft Edge TTS
    │   └── openai_tts.py         # Paid: OpenAI TTS
    ├── avatar/
    │   └── heygen.py             # HeyGen talking-head avatar
    ├── stock/
    │   └── pexels.py             # Pexels free stock photos
    └── image_gen/
        ├── dalle3.py             # OpenAI DALL-E 3 (paid)
        └── sdxl_local.py         # Stable Diffusion XL local (free, GPU)
```

---

## Environment Variables

```bash
# ── Core ──────────────────────────────────────────────────────────────────────
VIDEO_ENABLED=true
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/axisai
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# ── TTS ───────────────────────────────────────────────────────────────────────
VIDEO_TTS=edge_tts                # edge_tts | openai_tts
VIDEO_OPENAI_TTS_KEY=sk-...       # required when VIDEO_TTS=openai_tts

# ── Image Generation ──────────────────────────────────────────────────────────
VIDEO_IMAGE_GEN=none              # none | dalle3 | sdxl_local
VIDEO_SDXL_LOCAL_URL=http://localhost:7860   # required when IMAGE_GEN=sdxl_local

# ── Stock Photos ──────────────────────────────────────────────────────────────
VIDEO_STOCK=none                  # none | pexels
VIDEO_PEXELS_KEY=...              # required when VIDEO_STOCK=pexels

# ── Avatar ────────────────────────────────────────────────────────────────────
VIDEO_AVATAR=none                 # none | heygen
VIDEO_HEYGEN_API_KEY=...          # required when VIDEO_AVATAR=heygen

# ── Storage ───────────────────────────────────────────────────────────────────
VIDEO_STORAGE=local               # local | s3
VIDEO_LOCAL_STORAGE_PATH=/tmp/axis_videos
AWS_S3_BUCKET=my-bucket
AWS_S3_REGION=ap-south-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...

# ── LLM (scene planning) ──────────────────────────────────────────────────────
LLM_PROVIDER=openai               # openai | anthropic | local
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini

# ── Quality / Performance ─────────────────────────────────────────────────────
VIDEO_DEFAULT_RESOLUTION=1920x1080    # or 1280x720, 3840x2160
VIDEO_DEFAULT_TRANSITION=fade         # fade | cut
VIDEO_DEFAULT_MUSIC_VOLUME=0.15
```

---

## Provider Configuration

Providers can be configured globally via env vars **or** overridden per tenant
via `tenant.config.video` JSONB column.

### Tenant-level override example

```json
{
  "video": {
    "tts": "openai_tts",
    "api_keys": {
      "openai_tts": "sk-tenant-specific-key"
    },
    "image_gen": "dalle3",
    "dalle3_quality": "hd",
    "stock": "pexels",
    "api_keys": {
      "pexels": "tenant-pexels-key"
    },
    "brand_primary": "#1A3A6B",
    "brand_secondary": "#F5A623",
    "resolution": "1280x720",
    "transition": "fade",
    "music_volume": 0.10
  }
}
```

### Provider priority

```
Tenant config  >  Environment variable  >  Hardcoded default
```

---

## Video Types Reference

All 10 types accept the same base payload. Type-specific fields go in `assets`
or are derived from the script by the LLM planner.

### Common Request Schema

```json
{
  "title": "string (required)",
  "video_type": "kinetic | slideshow | stockfootage | avatar | explainer | whiteboard | motion | illustrative | presentation | screencast",
  "script": "string — raw content, narration, or bullet points",
  "duration_seconds": 30,
  "language": "en",
  "config": {
    "transition": "fade",
    "resolution": "1920x1080",
    "music_volume": 0.15
  },
  "assets": {}
}
```

---

### 1. Kinetic Typography

Text phrases appear one at a time, synchronized with TTS narration.
Each phrase fades/slides in on a dark background.

```json
{
  "video_type": "kinetic",
  "script": "Learning is the engine of growth. Every concept mastered opens a new door.",
  "assets": {}
}
```

**LLM scene schema:** `{text, effect, duration}`
**Fallback:** script split into 1 scene with full text.
**External APIs:** TTS only.

---

### 2. Slideshow

Photo slideshow with Ken Burns zoom/pan, optional captions, and narration.

```json
{
  "video_type": "slideshow",
  "script": "Our company culture is built on trust and innovation...",
  "assets": {
    "music_url": "https://example.com/bgmusic.mp3"
  }
}
```

**LLM scene schema:** `{id, narration, caption, ken_burns, search_keywords}`
**Image source:** Pexels (via `search_keywords`) → brand color fallback.
**External APIs:** TTS + Pexels.

---

### 3. Stock Footage

Like slideshow but scenes have `title` + `body_text` lower-third overlays.

```json
{
  "video_type": "stockfootage",
  "script": "Workplace safety protects everyone. Always wear PPE...",
  "assets": {}
}
```

**LLM scene schema:** `{id, title, body_text, narration, search_keywords}`
**External APIs:** TTS + Pexels.

---

### 4. Avatar

HeyGen-powered talking-head video. Script → HeyGen video → download → embed.

```json
{
  "video_type": "avatar",
  "script": "Hello and welcome to our leadership program...",
  "assets": {
    "avatar_id": "josh_lite3_20230714",
    "voice_id": "en-US-GuyNeural"
  }
}
```

**LLM scene schema:** `{id, script, duration_hint}`
**External APIs:** HeyGen + TTS fallback.
**Note:** HeyGen typically takes 60–120 s to render. Poll with `max_seconds=300`.

---

### 5. Explainer

AI-illustrated scenes with Ken Burns, title bar overlay, and body text.

```json
{
  "video_type": "explainer",
  "script": "Machine learning teaches computers to learn from data...",
  "config": {"transition": "fade"}
}
```

**LLM scene schema:** `{title, body_text, narration, image_prompt, image_style, duration_seconds}`
**Image acquisition:** DALL-E 3 / SDXL → Pexels → brand color.
**External APIs:** TTS + image gen (optional) + Pexels (fallback).
**Note:** Requires ImageMagick for `TextClip`. See troubleshooting.

---

### 6. Whiteboard

Hand-written style steps on warm white canvas. Great for how-to explanations.

```json
{
  "video_type": "whiteboard",
  "script": "Water evaporates from oceans. It rises and forms clouds. It falls as rain."
}
```

**LLM scene schema:** `{heading, body, narration, duration_seconds}`
**Background:** Warm white `#FAF8F0` with brand accent bar.
**External APIs:** TTS only — fully offline.

---

### 7. Motion Graphics

Branded gradient slides with bullets, progress dots, and optional logo watermark.

```json
{
  "video_type": "motion",
  "script": "Q3 revenue grew 18%. Customer satisfaction 94%. New launches exceeded targets.",
  "assets": {
    "logo_url": "https://example.com/logo.png",
    "music_url": "https://example.com/bg.mp3"
  }
}
```

**LLM scene schema:** `{title, bullets, narration, bg_color_hint, accent}`
**External APIs:** TTS only — fully offline (logo/music URLs optional).

---

### 8. Illustrative

Character PNG composited on background with bob animation and caption bar.

```json
{
  "video_type": "illustrative",
  "script": "Hi! I am Maya. Today we explore time management. Prioritize tasks first.",
  "assets": {
    "character_urls": [
      "https://example.com/character_female.png"
    ],
    "music_url": ""
  }
}
```

**LLM scene schema:** `{title, caption, narration, background_hint, character_position, duration_seconds}`
**Character positions:** `left | right | center | center_left | center_right`
**Character PNG:** Must be RGBA (transparent background). Resized to 60% of frame height.
**External APIs:** TTS + Pexels (background) + character URLs.

---

### 9. Presentation

PowerPoint-style slide deck with 6 layout types.

```json
{
  "video_type": "presentation",
  "script": "Welcome to our Leadership Development Program...",
  "assets": {
    "logo_url": "https://example.com/logo.png"
  }
}
```

**LLM scene schema:**
```json
{
  "slide_type": "title_slide | content | two_column | quote | image_text | divider",
  "title": "...",
  "subtitle": "...",          // title_slide only
  "bullets": ["..."],         // content, two_column, image_text
  "right_bullets": ["..."],   // two_column only
  "quote": "...",             // quote only
  "attribution": "...",       // quote only
  "speaker_notes": "...",     // used for TTS narration
  "duration_seconds": 8
}
```

**External APIs:** TTS + Pexels (image_text slides only).

---

### 10. Screencast

Tutorial-style IDE/browser mock with step badges, code panels, and callouts.

```json
{
  "video_type": "screencast",
  "script": "Step 1: Install Python. Step 2: Create virtual environment. Step 3: Install packages.",
  "assets": {}
}
```

**LLM scene schema:** `{step_number, heading, action, callout, narration, duration_seconds}`
**Background:** Dark IDE theme `#121218`.
**External APIs:** TTS only — fully offline.

---

## API Reference

### POST /api/v1/video/jobs

Create a new render job.

**Request:**
```json
{
  "title": "string",
  "video_type": "string",
  "script": "string",
  "duration_seconds": 30,
  "language": "en",
  "config": {},
  "assets": {}
}
```

**Response 201:**
```json
{
  "id": "uuid",
  "status": "queued",
  "video_type": "motion",
  "title": "...",
  "created_at": "2026-05-03T12:00:00Z"
}
```

### GET /api/v1/video/jobs/{id}

Poll job progress.

**Response:**
```json
{
  "id": "uuid",
  "status": "completed",
  "progress": 100,
  "progress_message": "Done",
  "video_url": "https://s3.../video.mp4",
  "thumbnail_url": "https://s3.../thumb.jpg",
  "duration_seconds": 28.4,
  "error_message": null,
  "metadata": {"slide_count": 5}
}
```

**Status values:** `queued` → `rendering` → `completed` | `failed`

### GET /api/v1/video/jobs

List jobs for the current tenant.

**Query params:** `limit` (default 20), `offset` (default 0), `video_type`, `status`

### GET /api/v1/video/assets

List rendered videos for a content item.

**Query params:** `content_item_id` (required)

---

## Renderer Architecture

All renderers extend `BaseVideoRenderer`:

```python
class BaseVideoRenderer(ABC):
    def __init__(self, job: VideoJob, providers: ProviderBundle,
                 tmp_dir: Path, settings: dict): ...

    @abstractmethod
    async def render(self) -> RenderResult: ...

    # Shared helpers available to all renderers:
    async def _plan_scenes(self, script: str) -> list[dict]: ...
    async def _synthesize_tts(self, text: str, output_path: Path) -> float: ...
    async def _download_asset(self, url: str, dest: Path, timeout_sec: int = 60) -> None: ...
    async def _update_progress(self, pct: int, message: str) -> None: ...

    def _get_resolution(self) -> tuple[int, int]: ...
    def _get_brand_colors(self) -> tuple[str, str]: ...
    def _get_transition(self) -> str: ...
    def _get_music_volume(self) -> float: ...
```

### ProviderBundle

All providers are resolved once per job and passed into the renderer:

```python
@dataclass
class ProviderBundle:
    tts: TTSProvider | None
    avatar: AvatarProvider | None
    stock: StockProvider | None
    image_gen: ImageGenProvider | None
    video_render: VideoRenderProvider | None
```

### LLM Scene Planning

The `LLMScenePlanner` sends a type-specific prompt to the configured LLM and
parses the JSON response into scene dicts. If the LLM call fails, `_fallback_scenes()`
returns a single scene with the full script, typed correctly for each renderer's
expected key schema:

| Video type    | Required scene keys                                  |
|--------------|------------------------------------------------------|
| kinetic      | `text`, `effect`, `duration`                         |
| avatar       | `id`, `script`, `duration_hint`                      |
| slideshow    | `id`, `narration`, `caption`, `ken_burns`            |
| stockfootage | `id`, `title`, `narration`, `search_keywords`        |
| explainer    | `title`, `body_text`, `narration`, `image_prompt`    |
| whiteboard   | `heading`, `body`, `narration`                       |
| motion       | `title`, `bullets`, `narration`                      |
| illustrative | `caption`, `narration`, `background_hint`            |
| presentation | `slide_type`, `title`, `speaker_notes`               |
| screencast   | `step_number`, `heading`, `action`, `narration`      |

---

## Blocking Work in Async

All CPU-intensive work (Pillow frame rendering, MoviePy assembly) runs in a
thread executor to avoid blocking the async event loop:

```python
loop = asyncio.get_running_loop()
await loop.run_in_executor(None, functools.partial(blocking_fn, ...))
```

`asyncio.get_running_loop()` is used throughout (not `get_event_loop()` which
is deprecated in Python 3.10+ and raises in 3.12+).

---

## Adding a New Video Type

1. Create `app/services/video/renderers/mytype.py` extending `BaseVideoRenderer`.
2. Define `render() -> RenderResult` using `_plan_scenes()`, `_synthesize_tts()`, etc.
3. Add `"mytype"` to the `VideoType` enum in `app/models/video.py`.
4. Add a `_fallback_scenes()` branch in `llm_planner.py`.
5. Wire the renderer in `app/tasks/render_video.py` dispatch dict.
6. Add the LLM system prompt for scene planning in `llm_planner.py`.
7. Add test cases to `videobuilder-testing.md`.

---

## Deployment

### Docker Compose

```yaml
# docker-compose.yml (video services)
services:
  api:
    build: .
    ports: ["8001:8001"]
    env_file: .env
    command: uvicorn app.main:app --host 0.0.0.0 --port 8001

  celery:
    build: .
    env_file: .env
    command: >
      celery -A app.celery_app worker
      -l info -Q video_render -c 2
    volumes:
      - /tmp/axis_videos:/tmp/axis_videos

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
```

### System Dependencies

```bash
# Required on the Celery worker host
apt-get install -y \
  ffmpeg \
  imagemagick \
  fonts-liberation \
  fonts-noto \
  fonts-ubuntu \
  python3-dev

# Fix ImageMagick policy for TextClip (explainer renderer)
sed -i 's/rights="none" pattern="@\*"/rights="read|write" pattern="@*"/' \
  /etc/ImageMagick-6/policy.xml
```

### Python Dependencies

```toml
# pyproject.toml (video-related)
moviepy = "^1.0.3"
pillow = ">=9.2.0"
edge-tts = ">=6.1.9"
pexelsapi = ">=1.0.0"   # or httpx direct
numpy = ">=1.24"
httpx = ">=0.27"
structlog = ">=24.0"
```

---

## Known Limitations

- **MoviePy 1.x**: `TextClip` requires ImageMagick. The explainer renderer uses
  `TextClip` for title/body overlays. If ImageMagick is unavailable, the renderer
  catches the exception and skips text overlays (video still renders).
- **MoviePy 1.x RGBA**: `ColorClip` only accepts RGB 3-tuples. Transparency is
  achieved via `.set_opacity()`. All overlay clips follow this pattern.
- **Illustrative bob animation**: Pre-renders all frames in memory (PIL Image
  list). For long scenes (>30 s at 24 fps), memory use is ~500 MB. Chunked
  rendering is planned for Phase 3.
- **SDXL local**: Requires NVIDIA GPU with ≥6 GB VRAM. Rendering one image
  takes 10–30 s on a mid-range GPU at 20 steps.
- **DALL-E 3**: Supports only 3 fixed sizes. The renderer picks the closest
  aspect ratio; the Ken Burns crop handles any remaining size mismatch.
- **Avatar fallback**: If HeyGen job fails (e.g. invalid avatar_id), the renderer
  currently falls back to a solid-color placeholder with TTS audio rather than
  retrying. Retry logic is planned for Phase 3.

---

## Steps 7–10: Advanced Renderers, Asset Library & Preview Flow

> Added in this session. All items below are fully implemented and tested.

---

### Step 7 — ConversationalRenderer

**Type slug:** `conversational`

The conversational renderer produces a scripted 2–3 character dialogue video. Characters appear side by side; the active speaker bobs gently at 0.8 Hz while inactive speakers are dimmed and scaled down.

**Scene schema sent to LLM:**

```json
{
  "turns": [
    {
      "character": "Alex",
      "character_index": 0,
      "position": "left",
      "voice_hint": "female_friendly",
      "text": "What the character says in this turn",
      "duration_seconds": 5
    },
    {
      "character": "Jamie",
      "character_index": 1,
      "position": "right",
      "voice_hint": "male_calm",
      "text": "The other character's reply",
      "duration_seconds": 4
    }
  ]
}
```

**Template settings consumed:**

| Key              | Type    | Default         | Description                                  |
|------------------|---------|-----------------|----------------------------------------------|
| `voice_a`        | string  | `en-US-AriaNeural` | TTS voice for character 0                 |
| `voice_b`        | string  | `en-US-GuyNeural`  | TTS voice for character 1                 |
| `voice_c`        | string  | `en-US-JennyNeural`| TTS voice for character 2                 |
| `character_names`| string  | `"Alex,Jamie"`  | Comma-separated display names                |
| `show_names`     | bool    | `true`          | Show name labels above character             |
| `primarycolor`   | hex     | `#2563EB`       | Caption bar and bubble background             |
| `accentcolor`    | hex     | `#FFFFFF`       | Caption text + speech bubble text             |
| `bgmvolume`      | float   | `0.2`           | Background music volume (0.0–1.0)            |
| `voicevolume`    | float   | `1.0`           | TTS voice volume (0.0–1.0)                   |
| `aspectratio`    | string  | `16:9`          | `16:9` / `9:16` / `1:1` / `4:3`             |
| `overlayopacity` | float   | `0.75`          | Caption bar overlay transparency             |

**Resolved assets consumed:**

```json
"_resolved_assets": {
  "character_urls": ["https://cdn.../alex.png", "https://cdn.../jamie.png"],
  "music_url": "https://cdn.../bg.mp3"
}
```

Character images should be RGBA PNGs. If none are provided the renderer auto-generates silhouettes in distinct brand colours.

**Visual layout (16:9 example):**

```
┌─────────────────────────────────┐
│                                 │
│  [ALEX]          [JAMIE]        │  ← characters at 22% / 78% x-fracs
│  (active, full   (dimmed 55%,   │    active bobs at 0.8 Hz / 5 px amplitude
│   brightness)    80% scale)     │
│                                 │
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │  ← caption bar: bottom 14% of frame
│  Alex                           │
│  "What the character says…"     │
└─────────────────────────────────┘
```

**Full request example:**

```bash
curl -X POST http://localhost:8000/api/v1/video/jobs \
  -H "X-Tenant-Key: $TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": 501,
    "video_type": "conversational",
    "title": "AI Explained Simply",
    "script": "Alex: What exactly is machine learning?\nJamie: Great question! At its core it is pattern recognition at scale.\nAlex: So like how Netflix knows what I want to watch?",
    "language": "en",
    "settings": {
      "duration_seconds": 60,
      "voice_a": "en-US-AriaNeural",
      "voice_b": "en-US-GuyNeural",
      "character_names": "Alex,Jamie",
      "show_names": true,
      "primarycolor": "#1E3A5F",
      "accentcolor": "#FFFFFF",
      "_resolved_assets": {
        "character_urls": [
          "https://your-cdn.com/alex_transparent.png",
          "https://your-cdn.com/jamie_transparent.png"
        ]
      }
    },
    "callback_url": "https://your-moodle.com/local/edzaxisvideo/callback.php"
  }'
```

---

### Step 8 — AutoRenderer

**Type slug:** `auto`

The AutoRenderer is a meta-renderer. It uses the LLM to analyse the script, available assets, and settings then picks the single best concrete video type and delegates all rendering to it.

**How selection works:**

1. `auto_select_type()` in `llm_planner.py` sends a compact prompt to the configured LLM (`VIDEO_LLM_PLANNER_MODEL`).
2. The LLM returns `{"video_type": "explainer"}` (or another eligible type).
3. The AutoRenderer patches `job.video_type` in memory, instantiates the chosen renderer, and runs it.
4. The DB record retains `video_type = "auto"`; `settings["_auto_chosen_type"]` records the actual choice.

**Eligible auto-selection types:**

```
stockfootage  kinetic  slideshow  explainer  whiteboard
motion  illustrative  presentation  conversational
```

Avatar and screencast are excluded because they require specialised external assets (HeyGen avatar ID, screen recording upload).

**LLM selection heuristics (communicated in the system prompt):**

| Script characteristic | Chosen type |
|-----------------------|-------------|
| Dialogue / multiple speakers | `conversational` |
| Short motivational / key-message (< 60 s) | `kinetic` |
| Step-by-step process or concept | `explainer` |
| Rich image_urls available | `slideshow` |
| Character images + narrative tone | `illustrative` |
| Clear headings / sections | `presentation` |
| Educational sketch feel | `whiteboard` |
| Bold brand / marketing | `motion` |
| Documentary / general (default) | `stockfootage` |

**Full request example:**

```bash
curl -X POST http://localhost:8000/api/v1/video/jobs \
  -H "X-Tenant-Key: $TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": 600,
    "video_type": "auto",
    "title": "Introduction to Photosynthesis",
    "script": "Photosynthesis is how plants convert sunlight into food. In the first stage chlorophyll absorbs light energy. In the second stage water molecules are split to release oxygen. Finally carbon dioxide is combined with hydrogen to form glucose.",
    "language": "en",
    "settings": {
      "duration_seconds": 90,
      "primarycolor": "#2D6A4F",
      "accentcolor": "#FFFFFF"
    },
    "callback_url": "https://your-moodle.com/local/edzaxisvideo/callback.php"
  }'
```

**Checking the chosen type after completion:**

```bash
# The chosen type is stored in settings._auto_chosen_type
curl http://localhost:8000/api/v1/video/jobs/600 \
  -H "X-Tenant-Key: $TENANT_KEY"
# Response includes: "video_type": "auto"
# Check job settings in DB: settings['_auto_chosen_type'] = "explainer"
```

---

### Step 9 — Asset Library API

The Asset Library stores reusable tenant-scoped media files (character PNGs, logos, music, background images, custom fonts) so they can be referenced across many video jobs without re-uploading each time.

**Base URL:** `GET|POST|PATCH|DELETE /api/v1/video/assets`

**Asset types:**

| Type        | Usage                                              |
|-------------|----------------------------------------------------|
| `character` | RGBA PNG used by ConversationalRenderer + Illustrative |
| `logo`      | Transparent PNG overlaid on finished videos        |
| `music`     | Background MP3/WAV for any renderer                |
| `background`| Full-frame background image for renderers          |
| `font`      | Custom TTF/OTF font file                           |

#### POST /api/v1/video/assets — Register asset

```bash
curl -X POST http://localhost:8000/api/v1/video/assets \
  -H "X-Tenant-Key: $TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alex Character",
    "asset_type": "character",
    "url": "https://cdn.your-domain.com/characters/alex_transparent.png",
    "mime_type": "image/png",
    "file_size_bytes": 245000,
    "metadata": {
      "name": "Alex",
      "voice_hint": "female_friendly",
      "position": "left"
    }
  }'
# Response: 201 Created
# { "id": "uuid", "name": "Alex Character", "asset_type": "character", ... }
```

#### GET /api/v1/video/assets — List assets

```bash
# All active character assets
curl "http://localhost:8000/api/v1/video/assets?asset_type=character&active_only=true&page=1&page_size=20" \
  -H "X-Tenant-Key: $TENANT_KEY"

# All music assets (active + archived)
curl "http://localhost:8000/api/v1/video/assets?asset_type=music&active_only=false" \
  -H "X-Tenant-Key: $TENANT_KEY"
```

#### PATCH /api/v1/video/assets/{id} — Update

```bash
# Update the URL (e.g. after re-uploading)
curl -X PATCH "http://localhost:8000/api/v1/video/assets/$ASSET_ID" \
  -H "X-Tenant-Key: $TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://cdn.your-domain.com/characters/alex_v2.png"}'

# Archive (soft-delete) an asset
curl -X PATCH "http://localhost:8000/api/v1/video/assets/$ASSET_ID" \
  -H "X-Tenant-Key: $TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'
```

#### DELETE /api/v1/video/assets/{id} — Soft delete

```bash
# Sets is_active=false; the row is preserved so existing VideoJob URLs still work
curl -X DELETE "http://localhost:8000/api/v1/video/assets/$ASSET_ID" \
  -H "X-Tenant-Key: $TENANT_KEY"
# Response: 204 No Content
```

**Migration:** `alembic/versions/006_add_video_assets.py`

Composite index `ix_video_assets_tenant_type_active` on `(tenant_id, asset_type, is_active)` optimises the renderer query pattern.

---

### Step 10 — Preview / Approval Flow

The preview flow allows a human reviewer to approve a 30-second sample before committing to a full render. This is useful for long or expensive renders (avatar, explainer with DALL-E 3).

#### Extended status lifecycle

```
queued
  ↓ (Celery render_video)
processing
  ↓
done | failed

── Preview path ──────────────────────
queued
  ↓ POST /{id}/preview
preview_pending
  ↓ (Celery generate_video_preview — renders first 30 s)
preview_ready            ← poll until here, preview_url populated
  ↓ POST /{id}/approve
queued                   ← full render re-queued
  ↓ (Celery render_video)
processing → done | failed
```

#### POST /api/v1/video/jobs/{id}/preview — Request 30-second preview

```bash
# Step 1: Create the job as a draft (any status except processing/preview_pending/done)
curl -X POST http://localhost:8000/api/v1/video/jobs \
  -H "X-Tenant-Key: $TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": 701,
    "video_type": "explainer",
    "title": "Neural Networks Deep Dive",
    "script": "... long script ...",
    "settings": {"duration_seconds": 300},
    "callback_url": "https://your-moodle.com/local/edzaxisvideo/callback.php"
  }'
# Returns: {"job_id": "uuid-xxx", "status": "queued"}

# Step 2: Request a 30-second preview instead of full render
# First cancel the queued task if needed, or simply call /preview which overrides
curl -X POST "http://localhost:8000/api/v1/video/jobs/uuid-xxx/preview" \
  -H "X-Tenant-Key: $TENANT_KEY"
# Returns 202: {"status": "preview_pending", "message": "Preview render queued..."}

# Step 3: Poll until preview_ready
curl "http://localhost:8000/api/v1/video/jobs/uuid-xxx" \
  -H "X-Tenant-Key: $TENANT_KEY"
# When ready: {"status": "preview_ready", "preview_url": "https://cdn.../preview_uuid-xxx.mp4"}
```

#### POST /api/v1/video/jobs/{id}/approve — Trigger full render

```bash
# Step 4: Approve the preview and start full render
curl -X POST "http://localhost:8000/api/v1/video/jobs/uuid-xxx/approve" \
  -H "X-Tenant-Key: $TENANT_KEY"
# Returns 202: {"status": "queued", "message": "Full render queued after approval..."}

# Step 5: Poll until done
curl "http://localhost:8000/api/v1/video/jobs/uuid-xxx" \
  -H "X-Tenant-Key: $TENANT_KEY"
# When done: {"status": "done", "output_url": "https://cdn.../uuid-xxx.mp4"}
```

#### Preview status guard rules

| Current status       | /preview allowed | /approve allowed |
|----------------------|:---:|:---:|
| `queued`             | ✅  | ❌  |
| `processing`         | ❌  | ❌  |
| `preview_pending`    | ❌  | ❌  |
| `preview_ready`      | ✅ (re-preview) | ✅ |
| `approved`           | ✅  | ❌  |
| `done`               | ❌  | ❌  |
| `failed`             | ✅  | ❌  |

#### Migration

`alembic/versions/007_video_job_preview_approval.py`:
- Adds `preview_url TEXT` column to `video_jobs`
- Widens `status VARCHAR(20)` → `VARCHAR(25)` (non-blocking on PostgreSQL)

---

### Updated VideoJob Status Reference

| Value              | Meaning                                              |
|--------------------|------------------------------------------------------|
| `queued`           | Waiting in Celery video queue                        |
| `processing`       | Celery worker actively rendering                     |
| `done`             | Full render complete; `output_url` populated         |
| `failed`           | Render failed; `error_message` populated             |
| `draft`            | Created but not yet dispatched (future UI use)       |
| `preview_pending`  | 30-s preview render in Celery queue                  |
| `preview_ready`    | Preview clip ready; `preview_url` populated          |
| `approved`         | Human approved preview; re-queued for full render    |

---

### Updated GET /api/v1/video/jobs/{id} Response

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "moodle_job_id": 701,
  "video_type": "explainer",
  "status": "preview_ready",
  "progress": 100,
  "progress_message": "Preview ready",
  "output_url": null,
  "thumbnail_url": null,
  "preview_url": "https://cdn.your-domain.com/video/preview_550e8400.mp4",
  "duration_seconds": null,
  "error_message": null,
  "created_at": "2026-05-04T10:00:00Z",
  "started_at": "2026-05-04T10:00:05Z",
  "completed_at": null
}
```

---

### Updated VIDEO_TYPES Reference

```python
VIDEO_TYPES = frozenset({
    # Phase 1
    "stockfootage", "kinetic", "slideshow", "avatar",
    # Phase 2
    "explainer", "whiteboard", "motion", "illustrative",
    "presentation", "screencast",
    # Step 7–8
    "conversational", "auto",
})
```


---

## Steps 11–17 — Providers, Encryption, and Renderer Upgrades

### Provider Overview (Updated)

| Capability | Providers (wired) | Config key(s) |
|---|---|---|
| **TTS** | `edge_tts` (free), `openai` (tts-1/hd), `elevenlabs` (multilingual v2) | `VIDEO_TTS_PROVIDER`, `VIDEO_OPENAI_TTS_KEY`, `VIDEO_ELEVENLABS_KEY` |
| **Avatar** | `heygen`, `d_id`, `sadtalker` (local GPU) | `VIDEO_HEYGEN_KEY`, `VIDEO_D_ID_KEY`, `sadtalker_url` |
| **Platform** | `pictory` | `VIDEO_PICTORY_KEY`, `pictory_user_id` |
| **Stock** | `pexels` | `VIDEO_PEXELS_API_KEY` |
| **Image Gen** | `dalle3`, `sdxl_local` | `VIDEO_OPENAI_TTS_KEY`, `sdxl_local_url` |

### Step 11 — OpenAITTSProvider (`providers/tts/openai_tts.py`)

- Models: `tts-1` (low latency) / `tts-1-hd` (high quality)
- Voices: alloy, echo, fable, onyx, nova, shimmer
- Duration measured via mutagen → ffprobe → file-size estimate fallback
- Tenant config keys: `openai_tts_model`, `openai_tts_voice`
- Env: `VIDEO_OPENAI_TTS_KEY`

### Step 12 — ElevenLabsProvider (`providers/tts/elevenlabs.py`)

- Model: `eleven_multilingual_v2` (default), `eleven_turbo_v2_5`
- Default voice: Rachel (`EXAVITQu4vr4xnSDxMaL`)
- Supports `clone_voice(audio_sample, name)` → voice_id for custom cloning
- Tenant config keys: `elevenlabs_default_voice`, `elevenlabs_model`
- Env: `VIDEO_ELEVENLABS_KEY`

### Step 13 — DIDProvider (`providers/avatar/d_id.py`)

- D-ID Talks API flow: POST /talks → poll GET /talks/{id} → download MP4
- Auth: HTTP Basic (base64 of `api_key:`)
- Voice format: `"microsoft|en-US-JennyNeural"` or language-auto mapping
- Tenant config keys: `d_id_presenter_id`, `d_id_driver_id`, `d_id_stitch`, `d_id_fluent`, `d_id_crop_type`
- Env: `VIDEO_D_ID_KEY`
- Polling: every 5 s, 10-minute timeout

### Step 14 — SadTalkerProvider (`providers/avatar/sadtalker.py`)

- Local GPU lip-sync — no cloud API key required
- REST server at `sadtalker_url` (default: `http://localhost:7860`)
- Accepts both JSON and streaming MP4 responses from server
- `voice_id` is the **path to a pre-synthesised WAV/MP3 file** — TTS must run first
- Tenant config keys: `sadtalker_url`, `sadtalker_preprocess`, `sadtalker_still`, `sadtalker_enhancer`

### Step 15 — PictoryProvider (`providers/platform/pictory.py`)

- Full-platform AI video: submit script → storyboard → render → download MP4
- Two-phase polling: storyboard (120 s max) → render (900 s max)
- Script assembled from all scene `narration`/`text` fields in render_plan
- Tenant config keys: `pictory_user_id`, `pictory_brand_logo_url`, `pictory_voiceover_lang`, `pictory_music_volume`, `pictory_highlight_colour`
- Env: `VIDEO_PICTORY_KEY`

### Step 16 — AES-256 API Key Encryption (`registry.py`)

All per-tenant API keys in `tenant.config.video.api_keys` can be stored
encrypted. Keys starting with `enc::` are automatically decrypted at runtime
using `VIDEO_ENCRYPTION_KEY` (32-byte hex string).

**Encrypting a key:**
```python
from cryptography.fernet import Fernet
import base64

raw_hex   = "YOUR_VIDEO_ENCRYPTION_KEY_FROM_ENV"   # 64 hex chars
key_bytes = bytes.fromhex(raw_hex)
fernet    = Fernet(base64.urlsafe_b64encode(key_bytes))
encrypted = "enc::" + fernet.encrypt(b"sk-YOUR_OPENAI_KEY").decode()
# Store `encrypted` in tenant.config.video.api_keys.openai_tts
```

**Generating the master key:**
```bash
openssl rand -hex 32   # → set as VIDEO_ENCRYPTION_KEY in .env
```

### Step 17 — Renderer Upgrades

#### WhiteboardRenderer Phase 2 (progressive text reveal)
- `VideoClip(make_frame, duration)` pattern — no frame pre-caching
- `_compute_layout()` pre-computes character positions as `_CharSpan` list
- `_make_frame_fn()` returns a closure that reveals first `cps × t` chars per frame
- `drawspeed` settings: `slow` = 5 cps, `normal` = 12 cps, `fast` = 25 cps
- Heading characters revealed first (with underline drawn once heading is complete)
- Body characters revealed after heading using word-wrapped spans

#### IllustrativeRenderer Chunked Rendering (O(1) RAM)
- **Before**: `_prerender_scene_frames()` built `list[PILImage]` for all frames → OOM on long videos
- **After**: `_prepare_scene_assets()` stores only background + character as numpy arrays; `_make_frame_fn()` composes each frame on demand in VideoClip
- Alpha blending done in numpy (`char_rgb × alpha + bg × (1-alpha)`) — no PIL per frame
- Caption bar pre-drawn once into `cap_overlay` numpy array; pasted per frame by slicing the bottom rows
- RAM footprint: ~3 × one-frame (O(1)) regardless of clip duration

#### AvatarRenderer Retry + Fallback
- **Retry logic**: up to 3 attempts with exponential back-off (5 s → 10 s → 20 s, capped at 60 s)
- **Retryable errors**: timeout, rate limit, 4xx/5xx transient codes
- **Permanent errors** (bad API key, invalid avatar, quota): raised immediately (no retry)
- **Fallback**: after all retries exhausted → `_render_placeholder_section()` generates a branded still-image video with TTS narration instead of crashing the entire job
- Fallback frame: brand primary colour background, warning banner, job title, section counter

---

## Code Review — Confirmed Bugs and Fixes (May 2026)

### BUG-1 [CRITICAL FIXED]: Avatar provider `TypeError` on extra kwargs

**Root cause:** `AvatarRenderer` called `provider.create_video()` with template
settings (`avatar_style`, `voice_speed`, `background_type`, `voice_emotion`,
`show_captions`, `avatar_position`) that were not in the `AvatarProvider` base
interface. `HeyGenProvider`, `DIDProvider`, and `SadTalkerProvider` all lacked
`**kwargs`, causing `TypeError: create_video() got an unexpected keyword argument`.

**Fix applied:**
- `HeyGenProvider.create_video()` now explicitly accepts all 7 template params and wires them into the HeyGen v2 API payload (`_submit()` updated):
  - `voice_speed` → `voice.speed` (clamped 0.5–2.0)
  - `voice_emotion` → `voice.emotion`
  - `avatar_style` → `character.avatar_style`
  - `background_type` + `background_value` → `background` block (color/image/video)
- `DIDProvider.create_video()` and `SadTalkerProvider.create_video()` both received `**kwargs` to safely absorb unsupported settings.

### BUG-2 [CRITICAL FIXED]: SadTalker requires pre-synthesised audio — AvatarRenderer wasn't doing TTS

**Root cause:** `SadTalkerProvider` does not perform TTS internally. It requires
`voice_id` to be a file path to a pre-synthesised WAV/MP3. `AvatarRenderer` was
passing a HeyGen voice name string (e.g. `"en-US-JennyNeural"` or `""`) causing
`ValueError("voice_id must be the path to a pre-synthesised audio file")` or
`FileNotFoundError`.

**Fix applied:**
- `SadTalkerProvider` now has a class-level flag `requires_pre_tts: bool = True`.
- `AvatarRenderer.render()` checks `getattr(self.providers.avatar, "requires_pre_tts", False)` at the start of the section loop.
- When `True`, it calls `self._synthesize_tts(section_script, tts_audio_path)` before each section and passes the resulting audio file path as `voice_id` to the provider.
- If TTS synthesis fails, a `RuntimeError` is raised immediately with a clear message (no silent data corruption).

### BUG-3 [FIXED]: `base_renderer.py` settings not deepcopied — in-place mutations leaked

**Root cause:** `self.settings: dict = job.settings or {}` assigned a reference
to the live SQLAlchemy ORM `job.settings` JSONB dict. Renderers that mutated
settings (e.g. `auto.py` writing `_auto_chosen_type`) were modifying the ORM
object's JSONB in-memory representation, causing potential data leaks between
retried renders.

**Fix applied:** `self.settings: dict = copy.deepcopy(job.settings or {})`

### BUG-4 [FIXED]: `registry.get_renderer_class()` unhelpful error on bad module

**Root cause:** A single `except (ImportError, AttributeError)` block gave
identical error messages for two very different failures: module not found vs.
class name mismatch.

**Fix applied:** Split into two separate `try/except` blocks — one for
`ImportError` (points to missing deps or syntax error in renderer file) and one
for `AttributeError` (points to class name typo in `_MAP`).

---

### Provider Settings Reference (Avatar)

| Setting | HeyGen | D-ID | SadTalker |
|---|---|---|---|
| `avatar_style` | ✅ wired → `character.avatar_style` | ✗ ignored | ✗ ignored |
| `voice_speed` | ✅ wired → `voice.speed` (0.5–2.0) | ✗ ignored | ✗ ignored |
| `voice_emotion` | ✅ wired → `voice.emotion` | ✗ ignored | ✗ ignored |
| `background_type` | ✅ wired → `background.type` (color/image/video) | ✗ ignored | ✗ ignored |
| `background_value` | ✅ wired → `background.value/url` | ✗ ignored | ✗ ignored |
| `requires_pre_tts` | `False` (HeyGen does own TTS) | `False` | **`True`** — TTS must run first |
