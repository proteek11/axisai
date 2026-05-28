# Phase 17 + 18 — Auto-Course Builder & Voice AI Tutor
> Spec doc — May 2026

---

## Phase 17 — Auto-Course Builder

### Functionality
Creator uploads a PDF → AI drafts a lesson plan (chapters, objectives, key topics).
Creator reviews + edits the plan, picks what to generate, optionally adds YouTube videos.
On submit, the system generates a fully populated Learning Space with summaries, quizzes, flashcards, and glossary for each chapter — in parallel — in under 5 minutes.

### API contract
| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/v1/course-builder/analyze` | POST | JWT | Upload PDF → returns lesson plan JSON + redis_token |
| `/api/v1/course-builder/youtube` | GET | JWT | `?query=...` → top 5 YouTube videos |
| `/api/v1/course-builder/generate` | POST | JWT | Create space + kick off all chapter jobs |
| `/api/v1/course-builder/progress/{space_id}` | GET | JWT | Poll job statuses for all items in a space |

### Data flow
1. POST analyze: pdfplumber extracts per-page text → stored in Redis (TTL 2h) under `course_build:{token}` → full text sent to LLM with course_analysis prompt → returns lesson plan JSON
2. GET youtube: YouTube Data API v3 search → top 5 videos
3. POST generate: reads pages from Redis → writes chapter text files to /tmp/course_builder/{token}/ → creates Space + ContentItems (type=text per chapter, type=youtube for videos) + ProcessingJobs → fires standard run_pipeline Celery tasks → returns {space_id, jobs[]}
4. GET progress: queries all processing jobs for the space → returns per-item status

### Lesson plan JSON schema
```json
{
  "course_title": "...",
  "description": "...",
  "estimated_duration": "3.5 hours",
  "objectives": ["..."],
  "chapters": [
    {
      "title": "Chapter 1: ...",
      "page_start": 1,
      "page_end": 8,
      "key_topics": ["...", "..."],
      "include": true,
      "youtube_search_query": "..."
    }
  ]
}
```

### Environment variables needed
- `YOUTUBE_API_KEY` — free YouTube Data API v3 key (10K queries/day)

---

## Phase 18 — Voice AI Tutor

### Functionality
Learner taps mic → speaks a question → browser SpeechRecognition converts to text → existing RAG chat answers → response text sent to TTS endpoint → EdgeTTS synthesizes MP3 → browser plays audio back. Full voice conversation loop. No new AI model needed — reuses existing RAG chat + EdgeTTS already in stack.

### API contract
| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/v1/tts/synthesize` | POST | JWT | `{text, voice?, language?}` → MP3 bytes (audio/mpeg) |
| `/api/v1/tts/voices` | GET | JWT | `?language=en` → list of available EdgeTTS voices |

### Frontend flow
1. VoiceChatPanel component added as a tab on the learner content page
2. Learner clicks mic → `SpeechRecognition.start()` → live transcript shown
3. On silence/stop → transcript sent to `/axis/chat/sessions/{id}/message` (existing)
4. AI response text → POST `/api/v1/tts/synthesize` → MP3 blob URL → `Audio.play()`
5. While audio plays: mic auto-disabled. After audio ends: mic re-activates.

### Performance
- Redis cache on TTS: SHA256(text+voice) → MP3 bytes, TTL 1h. Common responses cached instantly.
- Edge-tts: ~1-3 sec latency for typical response (~200 words). Acceptable for learning context.

---

## Testing
See testing.txt in this directory for curl test cases.
