# Phase 17 + 18 — Deployment & Testing Guide

> Auto-Course Builder (Phase 17) + Voice AI Tutor (Phase 18)  
> May 2026

---

## What was built

### Phase 17 — Auto-Course Builder
Creator uploads a PDF → AI drafts a lesson plan → creator reviews → system generates a full Learning Space (summaries, quizzes, flashcards, glossary) for every chapter in parallel.

### Phase 18 — Voice AI Tutor
Learner speaks → Web Speech API converts to text → RAG chat answers → EdgeTTS synthesizes MP3 → browser plays audio. Full voice loop, no new AI provider needed.

---

## Pre-deployment checklist

- [ ] SSH access to the server as `axisai` user
- [ ] `dev-video` branch has all changes pushed
- [ ] (Optional but recommended) `YOUTUBE_API_KEY` ready — free from [Google Cloud Console](https://console.cloud.google.com) → YouTube Data API v3

---

## Step 1 — Get a YouTube API key (optional — for Phase 17 YouTube search)

YouTube search works only if `YOUTUBE_API_KEY` is set. If you skip this, the course builder still works — creators just won't be able to search for videos.

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project (or use an existing one)
3. Enable **YouTube Data API v3**
4. Go to **Credentials → Create Credentials → API Key**
5. Copy the key — you'll add it to `.env` in Step 3

The free quota is 10,000 units/day. Each search costs 100 units → 100 searches/day free.

---

## Step 2 — SSH into the server

```bash
ssh axisai@your-server-ip
cd /home/axisai/axisai-backend
```

---

## Step 3 — Add YOUTUBE_API_KEY to .env

```bash
nano axis-ai/.env
```

Add this line (or update if it already exists):

```
YOUTUBE_API_KEY=your_key_here
```

Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).

---

## Step 4 — Run the deployment script

```bash
bash axis-ai/deploy-phase17-18.sh
```

This script will:
1. Pull latest code from `dev-video` branch (`git stash && git pull`)
2. Install/upgrade Python dependencies (`pip install -e .`)
3. Confirm `edge-tts` and `pdfplumber` are available (installs if missing)
4. Check `YOUTUBE_API_KEY` is set
5. Restart `axis-ai`, `axis-ai-worker`, `axis-ai-beat`
6. Smoke-test all 6 new endpoints

Expected output at the end:
```
[deploy] Phase 17 + 18 deployment complete! ✅
```

---

## Step 5 — Verify services

```bash
for svc in axis-ai axis-ai-worker axis-ai-beat; do
  systemctl is-active $svc && echo "$svc: OK" || echo "$svc: FAILED"
done
```

All three should show `OK`. If any fails:

```bash
sudo journalctl -u axis-ai -n 100 --no-pager
```

---

## Step 6 — Deploy the frontend (Next.js)

The frontend has new files too. On your frontend deploy server (or same server if using PM2):

```bash
cd /home/axisai/axisai-backend/axis-frontend  # adjust path as needed
git pull origin dev-video
npm install
npm run build
# Restart your frontend process (PM2 example):
pm2 restart axis-frontend
```

If using the same deploy.sh for the frontend, run it now.

---

## Step 7 — End-to-end testing

### 7a — Test Auto-Course Builder (Phase 17)

**As a creator:**

1. Log in at [axis.edzlms.com](https://axis.edzlms.com)
2. In the sidebar, click **Course Builder** (should have an "AI" badge)
3. Drag and drop a PDF (any text-based PDF, e.g. a textbook chapter or manual)
4. Wait for analysis — you should see a lesson plan appear (5–30 seconds depending on PDF size)
5. Review the chapters — toggle some off, adjust quiz counts
6. Click a chapter's "Add YouTube video" link → confirm videos appear (requires `YOUTUBE_API_KEY`)
7. Click **Generate Course →**
8. Watch the live progress screen — chapters should tick off one by one
9. When all complete, click **Open Learning Space**
10. Confirm the space has chapters with content tabs (Summary, Quiz, Flashcards, Glossary)

**Expected results:**
- Step 3: Lesson plan with 3–8 chapters, each with key topics and a YouTube search query
- Step 7: Progress screen shows chapters updating from "Queued" → "Processing" → "Done"
- Step 10: Learning Space opens with all AI content generated

**If YouTube search shows 503:**
- `YOUTUBE_API_KEY` is not set or is invalid — recheck Step 3

**If analysis fails with "PDF appears to be empty":**
- The PDF is image-based (scanned) — only text-based PDFs work currently

---

### 7b — Test Voice AI Tutor (Phase 18)

**As a learner:**

1. Log in and open any Learning Space that has content
2. Click a content item to open the study page
3. In the bottom-right corner, you'll see two buttons stacked:
   - Top: **mic icon** (Voice AI Tutor)
   - Bottom: **chat bubble icon** (Text AI Tutor)
4. Click the **mic icon** — the Voice Chat panel opens
5. Click the large **blue mic button** and speak a question (e.g. "Summarize the key points")
6. Your words appear as a transcript while you speak
7. When you stop speaking, the AI processes the question
8. The AI's answer plays back as audio automatically
9. Use the **speaker-mute button** (top-right of panel) to disable audio if needed

**Browser compatibility:**
- ✅ Chrome (recommended)
- ✅ Edge
- ✅ Firefox (partial — may need mic permission)
- ❌ Safari — Web Speech API not fully supported

**If voice input isn't working:**
- Browser may be blocking microphone — check the address bar for a mic blocked icon
- Try from Chrome/Edge if on Safari

**If TTS audio doesn't play:**
- Check browser console for errors on `/api/tts` call
- Confirm `axis-ai` service is running and `edge-tts` package is installed

---

## API test reference (curl)

Replace `YOUR_JWT_TOKEN` with a valid JWT from the login flow.

```bash
BASE="https://axisai.edzlms.com/api/v1"
TOKEN="YOUR_JWT_TOKEN"

# Health check
curl "$BASE/health"

# List TTS voices
curl -H "Authorization: Bearer $TOKEN" "$BASE/tts/voices?language=en"

# Synthesize TTS (saves to test.mp3)
curl -X POST "$BASE/tts/synthesize" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello, this is a test of the Voice AI Tutor.", "language": "en"}' \
  --output test.mp3
echo "TTS file size: $(wc -c < test.mp3) bytes"

# YouTube search (requires YOUTUBE_API_KEY)
curl -H "Authorization: Bearer $TOKEN" \
  "$BASE/course-builder/youtube?query=supervised+machine+learning+explained"

# Course builder analyze (upload a PDF)
curl -X POST "$BASE/course-builder/analyze" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/your/document.pdf"

# Course builder generate (use redis_token from analyze response)
curl -X POST "$BASE/course-builder/generate" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "redis_token": "TOKEN_FROM_ANALYZE",
    "space_title": "My Test Course",
    "space_description": "Auto-generated from PDF",
    "chapters": [
      {
        "title": "Chapter 1",
        "page_start": 1,
        "page_end": 10,
        "include": true,
        "generate_tasks": ["summary", "quiz", "flashcards", "glossary"],
        "quiz_count": 5
      }
    ],
    "youtube_videos": []
  }'

# Progress poll (use space_id from generate response)
curl -H "Authorization: Bearer $TOKEN" \
  "$BASE/course-builder/progress/SPACE_ID_FROM_GENERATE"
```

---

## Rollback

If something goes wrong:

```bash
cd /home/axisai/axisai-backend
git stash
git checkout HEAD~1  # or specify a commit
cd axis-ai
source .venv/bin/activate
pip install -e .
sudo systemctl restart axis-ai axis-ai-worker axis-ai-beat
```

---

## Files changed in this release

### Backend (`axis-ai/`)
| File | Change |
|------|--------|
| `app/api/v1/course_builder.py` | **NEW** — 4 course builder endpoints |
| `app/api/v1/tts.py` | **NEW** — TTS synthesize + voices endpoints |
| `app/api/v1/router.py` | Updated — both new routers registered |
| `app/services/ai/prompts/course_analysis.yaml` | **NEW** — LLM prompt for lesson plan |
| `docs/phase17_18_spec.md` | **NEW** — Full spec doc |

### Frontend (`axis-frontend/`)
| File | Change |
|------|--------|
| `components/layout/sidebar.tsx` | Updated — "Course Builder" nav item |
| `components/learn/voice-chat-panel.tsx` | **NEW** — VoiceChatPanel component |
| `app/(dashboard)/create/course/page.tsx` | **NEW** — 4-step course builder wizard |
| `app/(dashboard)/learn/.../page.tsx` | Updated — mic FAB + VoiceChatPanel |
| `app/api/course-builder/analyze/route.ts` | **NEW** |
| `app/api/course-builder/youtube/route.ts` | **NEW** |
| `app/api/course-builder/generate/route.ts` | **NEW** |
| `app/api/course-builder/progress/[spaceId]/route.ts` | **NEW** |
| `app/api/tts/route.ts` | **NEW** — returns raw audio/mpeg |
