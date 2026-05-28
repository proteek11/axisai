# Axis AI — Video API Local Testing (curl)

All 8 video types covered, starting with **slideshow**.  
Run services first, then copy-paste the curl commands.

---

## 0. Pre-flight — Start Services

Open **4 terminals** and run one per terminal:

```bash
# Terminal 1 — Redis
docker run --rm -p 6379:6379 redis:7-alpine

# Terminal 2 — Postgres
docker run --rm \
  -e POSTGRES_USER=axis \
  -e POSTGRES_PASSWORD=axisdev \
  -e POSTGRES_DB=axis_ai \
  -p 5432:5432 postgres:16-alpine

# Terminal 3 — FastAPI  (from axis-ai/ folder)
cd axis-ai
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Terminal 4 — Celery video worker  (from axis-ai/ folder)
cd axis-ai
source .venv/bin/activate
celery -A app.tasks.celery_app worker \
  --loglevel=info --concurrency=2 -Q video
```

### Env vars you need in `.env` for local (no paid APIs)

```bash
VIDEO_ENABLED=true
VIDEO_TTS=edge_tts          # free, no API key
VIDEO_IMAGE_GEN=none        # slideshow uses Pexels; set none to skip
VIDEO_STOCK=none            # set to pexels + PEXELS_API_KEY for real images
VIDEO_AVATAR=none
MASTER_API_KEY=dev-master-key-change-in-production
```

> **Note:** `MASTER_API_KEY` is the bearer token for all curl calls below.

---

## 1. Helper Env Variables (set once, reuse everywhere)

```bash
export BASE="http://localhost:8000"
export TOKEN="dev-master-key-change-in-production"
export HDR='Content-Type: application/json'
```

---

## 2. Health Check

```bash
curl -s "$BASE/health" | python3 -m json.tool
```

Expected: `{"status": "ok", ...}`

---

## ═══════════════════════════════════════════════
## TYPE 1 — SLIDESHOW
## Pure image compositing, no external APIs required
## ═══════════════════════════════════════════════

### 2a. Create slideshow job (minimal)

```bash
curl -s -X POST "$BASE/api/v1/video/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": 1001,
    "video_type": "slideshow",
    "title": "Introduction to Machine Learning",
    "language": "en",
    "script": "Machine learning is a subset of artificial intelligence that enables systems to learn from data. It has three main types: supervised learning, unsupervised learning, and reinforcement learning. Each type has unique applications in the real world.",
    "callback_url": "http://localhost/moodle/local/edzaxisvideo/callback.php",
    "settings": {
      "duration_seconds": 60,
      "resolution": "1080p",
      "aspect_ratio": "16:9",
      "transition": "fade",
      "brand_color_primary": "#2563EB",
      "brand_color_secondary": "#FFFFFF",
      "slidestyle": "standard",
      "slideperscene": 1,
      "music_volume": 0.2
    }
  }' | python3 -m json.tool
```

**Save the returned `job_id` UUID:**
```bash
export SLIDESHOW_JOB_ID="<uuid-from-response>"
```

---

### 2b. Create slideshow job (with Pexels images + captions)

> Requires `VIDEO_STOCK=pexels` and `VIDEO_PEXELS_API_KEY=your_key` in `.env`

```bash
curl -s -X POST "$BASE/api/v1/video/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": 1002,
    "video_type": "slideshow",
    "title": "Benefits of Online Learning",
    "language": "en",
    "script": "Online learning offers flexibility that traditional classrooms cannot match. Students can learn at their own pace, from anywhere in the world. The vast library of courses covers every subject imaginable. Interactive tools and AI tutors make studying more engaging than ever before.",
    "callback_url": "http://localhost/moodle/local/edzaxisvideo/callback.php",
    "settings": {
      "duration_seconds": 90,
      "resolution": "1080p",
      "aspect_ratio": "16:9",
      "voice": "en-US-AriaNeural",
      "transition": "fade",
      "brand_color_primary": "#7C3AED",
      "brand_color_secondary": "#F9FAFB",
      "slidestyle": "cinematic",
      "slideperscene": 2,
      "music_volume": 0.25
    }
  }' | python3 -m json.tool
```

---

### 2c. Slideshow — Portrait / mobile aspect ratio (9:16)

```bash
curl -s -X POST "$BASE/api/v1/video/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": 1003,
    "video_type": "slideshow",
    "title": "Quick Safety Tips",
    "language": "en",
    "script": "Always wear your seatbelt. Keep your workspace clean and organized. Report any hazards immediately to your supervisor. Stay hydrated and take regular breaks during long shifts.",
    "callback_url": "http://localhost/moodle/local/edzaxisvideo/callback.php",
    "settings": {
      "duration_seconds": 40,
      "resolution": "720p",
      "aspect_ratio": "9:16",
      "transition": "slide",
      "slidestyle": "minimal",
      "slideperscene": 1,
      "music_volume": 0.0
    }
  }' | python3 -m json.tool
```

---

### 2d. Poll slideshow job status

```bash
# Replace with your actual job UUID
curl -s -X GET "$BASE/api/v1/video/jobs/$SLIDESHOW_JOB_ID" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**Status flow:** `queued` → `processing` → `done` (or `failed`)

When done, response includes:
```json
{
  "status": "done",
  "progress": 100,
  "output_url": "/data/video_outputs/...",
  "thumbnail_url": "/data/video_outputs/.../thumb.jpg",
  "duration_seconds": 62
}
```

---

### 2e. Poll until done (bash loop)

```bash
while true; do
  STATUS=$(curl -s "$BASE/api/v1/video/jobs/$SLIDESHOW_JOB_ID" \
    -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'], d['progress'])")
  echo "[$(date +%H:%M:%S)] $STATUS"
  [[ "$STATUS" == done* ]] || [[ "$STATUS" == failed* ]] && break
  sleep 5
done
```

---

### 2f. List all video jobs

```bash
curl -s "$BASE/api/v1/video/jobs?video_type=slideshow&page=1&page_size=10" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

### 2g. Request a 30-second preview first (optional)

```bash
# Step 1 — request preview
curl -s -X POST "$BASE/api/v1/video/jobs/$SLIDESHOW_JOB_ID/preview" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Step 2 — poll until status == preview_ready
curl -s "$BASE/api/v1/video/jobs/$SLIDESHOW_JOB_ID" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Step 3 — approve full render
curl -s -X POST "$BASE/api/v1/video/jobs/$SLIDESHOW_JOB_ID/approve" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## ═══════════════════════════════════════════════
## TYPE 2 — MOTION
## Graphic overlays, local only, no external APIs
## ═══════════════════════════════════════════════

```bash
curl -s -X POST "$BASE/api/v1/video/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": 2001,
    "video_type": "motion",
    "title": "Company Values Overview",
    "language": "en",
    "script": "Our company stands on three pillars: Innovation, Integrity, and Impact. Innovation drives us to find better solutions every day. Integrity ensures we always do what is right. Impact measures our success by the difference we make.",
    "callback_url": "http://localhost/moodle/local/edzaxisvideo/callback.php",
    "settings": {
      "duration_seconds": 60,
      "resolution": "1080p",
      "transition": "zoom",
      "brand_color_primary": "#DC2626",
      "brand_color_secondary": "#FEF2F2",
      "kinetic_style": "slidein",
      "music_volume": 0.3
    }
  }' | python3 -m json.tool
```

---

## ═══════════════════════════════════════════════
## TYPE 3 — WHITEBOARD
## Draw-on effect, fully local
## ═══════════════════════════════════════════════

```bash
curl -s -X POST "$BASE/api/v1/video/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": 3001,
    "video_type": "whiteboard",
    "title": "How Neural Networks Work",
    "language": "en",
    "script": "A neural network is inspired by the human brain. It consists of layers of interconnected nodes called neurons. Data flows through the input layer, gets processed by hidden layers, and produces output. Training adjusts the connections to minimize errors.",
    "callback_url": "http://localhost/moodle/local/edzaxisvideo/callback.php",
    "settings": {
      "duration_seconds": 90,
      "resolution": "1080p",
      "transition": "none",
      "brand_color_primary": "#1D4ED8",
      "brand_color_secondary": "#FFFFFF",
      "music_volume": 0.15
    }
  }' | python3 -m json.tool
```

---

## ═══════════════════════════════════════════════
## TYPE 4 — ILLUSTRATIVE
## Image + narration (may use image gen if configured)
## ═══════════════════════════════════════════════

```bash
curl -s -X POST "$BASE/api/v1/video/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": 4001,
    "video_type": "illustrative",
    "title": "The Water Cycle Explained",
    "language": "en",
    "script": "Water evaporates from oceans and lakes when heated by the sun. It rises into the atmosphere and forms clouds through condensation. When clouds become heavy enough, precipitation falls as rain or snow. This water collects in rivers and flows back to the ocean, completing the cycle.",
    "callback_url": "http://localhost/moodle/local/edzaxisvideo/callback.php",
    "settings": {
      "duration_seconds": 75,
      "resolution": "1080p",
      "transition": "fade",
      "brand_color_primary": "#0369A1",
      "brand_color_secondary": "#E0F2FE",
      "music_volume": 0.2
    }
  }' | python3 -m json.tool
```

---

## ═══════════════════════════════════════════════
## TYPE 5 — CONVERSATIONAL
## Talking-head style, multi-character, local TTS
## ═══════════════════════════════════════════════

```bash
curl -s -X POST "$BASE/api/v1/video/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": 5001,
    "video_type": "conversational",
    "title": "Interview: Starting Your Career in Tech",
    "language": "en",
    "script": "Alex: Welcome to the show! Today we are talking about breaking into the tech industry. Jamie, you made the switch from marketing to software development. How did you do it? Jamie: Thanks Alex! I started with free online courses and built small projects. The key was consistency — coding every day for at least an hour. Alex: That is great advice. What resources would you recommend for complete beginners? Jamie: I would start with freeCodeCamp for web development or Python for data science. The community support is incredible.",
    "callback_url": "http://localhost/moodle/local/edzaxisvideo/callback.php",
    "settings": {
      "duration_seconds": 120,
      "resolution": "1080p",
      "transition": "fade",
      "brand_color_primary": "#059669",
      "brand_color_secondary": "#ECFDF5",
      "voice_a": "en-US-AriaNeural",
      "voice_b": "en-US-GuyNeural",
      "character_names": "Alex,Jamie",
      "show_names": true,
      "music_volume": 0.1
    }
  }' | python3 -m json.tool
```

---

## ═══════════════════════════════════════════════
## TYPE 6 — STOCKFOOTAGE
## Stock video assets (Pexels video)
## Requires: VIDEO_STOCK=pexels + PEXELS_API_KEY
## ═══════════════════════════════════════════════

```bash
curl -s -X POST "$BASE/api/v1/video/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": 6001,
    "video_type": "stockfootage",
    "title": "The Future of Remote Work",
    "language": "en",
    "script": "Remote work has transformed the modern workplace. Employees now collaborate across continents without leaving their homes. Companies report higher productivity and lower overhead costs. The tools enabling this revolution improve every year, making distance truly irrelevant.",
    "callback_url": "http://localhost/moodle/local/edzaxisvideo/callback.php",
    "settings": {
      "duration_seconds": 90,
      "resolution": "1080p",
      "transition": "fade",
      "brand_color_primary": "#7C3AED",
      "brand_color_secondary": "#FFFFFF",
      "music_volume": 0.3
    }
  }' | python3 -m json.tool
```

---

## ═══════════════════════════════════════════════
## TYPE 7 — EXPLAINER
## May call image generation if configured
## ═══════════════════════════════════════════════

```bash
curl -s -X POST "$BASE/api/v1/video/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": 7001,
    "video_type": "explainer",
    "title": "What is Blockchain?",
    "language": "en",
    "script": "Blockchain is a distributed ledger technology that records transactions across many computers. Once data is recorded, it cannot be altered retroactively. Each block contains a cryptographic hash of the previous block, forming a chain. This makes blockchain extremely secure and transparent, ideal for cryptocurrencies and supply chain tracking.",
    "callback_url": "http://localhost/moodle/local/edzaxisvideo/callback.php",
    "settings": {
      "duration_seconds": 90,
      "resolution": "1080p",
      "transition": "slide",
      "brand_color_primary": "#F59E0B",
      "brand_color_secondary": "#1C1917",
      "music_volume": 0.2
    }
  }' | python3 -m json.tool
```

---

## ═══════════════════════════════════════════════
## TYPE 8 — PRESENTATION
## Slide-based, narrated slides
## ═══════════════════════════════════════════════

```bash
curl -s -X POST "$BASE/api/v1/video/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": 8001,
    "video_type": "presentation",
    "title": "Q1 2025 Marketing Strategy",
    "language": "en",
    "script": "Welcome to our Q1 2025 marketing strategy presentation. Our goal this quarter is to grow brand awareness by 40 percent. We will focus on three channels: social media, content marketing, and email campaigns. Social media will target LinkedIn and Instagram with daily posts. Content marketing will produce two blog posts per week. Email campaigns will run bi-weekly with personalized segmentation.",
    "callback_url": "http://localhost/moodle/local/edzaxisvideo/callback.php",
    "settings": {
      "duration_seconds": 120,
      "resolution": "1080p",
      "aspect_ratio": "16:9",
      "transition": "slide",
      "brand_color_primary": "#1D4ED8",
      "brand_color_secondary": "#FFFFFF",
      "font_name": "Montserrat",
      "music_volume": 0.15
    }
  }' | python3 -m json.tool
```

---

## ═══════════════════════════════════════════════
## TYPE 9 — AVATAR
## Needs HeyGen API key — skip if not configured
## ═══════════════════════════════════════════════

```bash
# Only run if VIDEO_AVATAR=heygen and HEYGEN_API_KEY is set in .env
curl -s -X POST "$BASE/api/v1/video/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": 9001,
    "video_type": "avatar",
    "title": "Course Welcome from Your Instructor",
    "language": "en",
    "script": "Hello and welcome to this course. I am so excited to have you here. Over the next few weeks, we will explore the fascinating world of data science together. You will learn to analyse data, build models, and draw meaningful insights. Let us get started!",
    "callback_url": "http://localhost/moodle/local/edzaxisvideo/callback.php",
    "settings": {
      "duration_seconds": 60,
      "resolution": "1080p",
      "heygen_avatar_id": "YOUR_AVATAR_ID",
      "heygen_voice_id": "YOUR_VOICE_ID",
      "music_volume": 0.0
    }
  }' | python3 -m json.tool
```

---

## ═══════════════════════════════════════════════
## TYPE 10 — SCREENCAST
## Screen recording based
## ═══════════════════════════════════════════════

```bash
# Requires a pre-uploaded screencast_url in resolved_assets
curl -s -X POST "$BASE/api/v1/video/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": 10001,
    "video_type": "screencast",
    "title": "How to Use the Student Dashboard",
    "language": "en",
    "script": "In this tutorial we will walk through the student dashboard. First, log in with your credentials. Navigate to My Courses to see all enrolled courses. Click on any course to access lessons, quizzes, and your progress tracker.",
    "callback_url": "http://localhost/moodle/local/edzaxisvideo/callback.php",
    "settings": {
      "duration_seconds": 120,
      "resolution": "1080p",
      "transition": "fade",
      "music_volume": 0.1,
      "_resolved_assets": {
        "screencast_url": "https://your-moodle.com/pluginfile.php/.../screen_recording.mp4"
      }
    }
  }' | python3 -m json.tool
```

---

## 3. Utility Calls

### List all jobs (any type)
```bash
curl -s "$BASE/api/v1/video/jobs?page=1&page_size=20" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### Filter by status
```bash
curl -s "$BASE/api/v1/video/jobs?status=failed" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### Check Celery is processing (Flower UI)
```
http://localhost:5555
```

---

## 4. Expected Status Flow

```
queued  →  processing  →  done
                       →  failed   (check error_message)
queued  →  preview_pending  →  preview_ready  →  queued  →  done
```

---

## 5. Slideshow-Specific Settings Reference

| Setting | Values | Default | Notes |
|---|---|---|---|
| `slidestyle` | `standard`, `cinematic`, `minimal`, `corporate` | `standard` | Visual treatment |
| `slideperscene` | `1`, `2`, `3` | `1` | Pexels images per LLM scene |
| `transition` | `fade`, `slide`, `zoom`, `none` | `fade` | Clip transition |
| `music_volume` | `0.0` – `1.0` | `0.3` | 0 = no music |
| `resolution` | `720p`, `1080p`, `4k` | `1080p` | Output resolution |
| `aspect_ratio` | `16:9`, `9:16`, `1:1` | `16:9` | Landscape / portrait / square |
| `voice` | EdgeTTS voice ID | system default | e.g. `en-US-AriaNeural` |
| `brand_color_primary` | hex | `#2563EB` | Background fallback color |
| `brand_color_secondary` | hex | `#FFFFFF` | Caption text color |

---

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| `422 Unprocessable Entity` | Check `video_type` spelling — must match exactly |
| `401 Unauthorized` | Check `MASTER_API_KEY` matches your `.env` |
| Job stuck at `queued` | Celery worker not running or not consuming `video` queue |
| `TTS failed` | Install `edge-tts`: `pip install edge-tts` |
| Images not loading | Set `VIDEO_STOCK=pexels` + `VIDEO_PEXELS_API_KEY` in `.env` |
| `MoviePy error` | Install deps: `pip install moviepy pillow` |
| `ImageMagick` error on captions | Install ImageMagick: `brew install imagemagick` (mac) |
