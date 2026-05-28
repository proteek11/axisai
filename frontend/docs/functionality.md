# axis.edzlms.com — Functionality Specification
> Version 1.0 | Phase 1 | May 2026

---

## Overview

axis.edzlms.com is a standalone Next.js 14 web application that provides a clean, enterprise-grade interface for AI-powered learning content — independent of Moodle. It talks directly to the FastAPI backend at axisai.edzlms.com.

### Core Concept: Learning Space
A **Learning Space** is the primary organisational unit — analogous to a Moodle course. Creators build Learning Spaces, add content to them, and share them with learners. A space can contain one or many content items (PDFs, videos, links). Learners access all content within a space through a single shared link.

---

## Phase 1 Scope

### Content Types Supported
- PDF / TXT file upload (up to 100 MB)
- YouTube video URL
- Vimeo video URL
- Locally uploaded video (MP4, MOV, AVI)

### AI Outputs (Phase 1)
- Summary
- Glossary
- Flashcards
- Quiz (MCQ)
- Infographic
- FAQ (bonus — already in backend)

### NOT in Phase 1
- Video creation pipeline (Ravi video renderers)
- SCORM / H5P ingest (Moodle-only for now)
- Mindmap, Objectives, Blooms (future)
- Real-time collaboration

---

## Roles & Access Model

| Role | Access | Description |
|------|--------|-------------|
| `admin` | Full platform control | Manages tenants, features, KB, views all content, seeds users |
| `creator` | Own spaces + content | Creates Learning Spaces, uploads content, curates AI outputs, publishes |
| `learner` | Assigned spaces only | Studies content in spaces shared with them |
| `guest` | Public spaces only | No login required; can access spaces marked `is_guest_accessible = true` |

Role is encoded in JWT. Route protection enforced in Next.js middleware. FastAPI also validates role on every request.

---

## User Stories

### Admin
- As admin, I can view a dashboard showing total content items, active jobs, AI outputs generated, and KB documents
- As admin, I can toggle which AI features (summary, glossary, flashcards, quiz, infographic, chatbot) are enabled for the platform
- As admin, I can manage the Knowledge Base (add via URL / text / file, toggle active, delete, reindex)
- As admin, I can view all users and their roles (Phase 1: read-only; user creation is seeded via script)
- As admin, I can view token usage per user and set per-user limits
- As admin, I can view the full audit log

### Creator
- As creator, I can create a Learning Space with a title, description, and cover image
- As creator, I can upload content to a space: PDF/TXT, YouTube URL, Vimeo URL, or local video
- As creator, I can select which AI outputs to generate when uploading content
- As creator, I can watch the job progress in real time (polling every 3 seconds)
- As creator, I can review and edit all AI outputs: summary (inline edit), glossary (table CRUD), flashcards (card CRUD), quiz (question CRUD), infographic (view only)
- As creator, I can regenerate any output type on demand
- As creator, I can toggle visibility per output type per content item
- As creator, I can publish a Learning Space and share it with specific learners or as a public link
- As creator, I can mark a space as guest-accessible (no login required for learners)

### Learner
- As learner, I can see all Learning Spaces shared with me on my dashboard
- As learner, I can study any content item in a space through tabs: Summary, Glossary, Flashcards, Quiz, Infographic
- As learner, I can flip flashcards interactively and rate my understanding
- As learner, I can take a quiz, see my score, and retry
- As learner, I can use the AI study chat on any content item (if enabled)
- As guest, I can access a public space via shared URL without logging in

---

## API Contract (axis-frontend → axisai.edzlms.com)

All calls from Next.js **server-side API routes** to FastAPI. The browser never touches axisai.edzlms.com directly. The FastAPI API key is stored only in Next.js server environment variables.

### New FastAPI Endpoints (added by migration 008)

#### Auth
```
POST /api/v1/auth/login          → {email, password} → {access_token, refresh_token, user}
POST /api/v1/auth/refresh        → {refresh_token} → {access_token}
POST /api/v1/auth/logout         → invalidate refresh token
GET  /api/v1/auth/me             → current user profile
```

#### Learning Spaces
```
POST   /api/v1/spaces                    → create space
GET    /api/v1/spaces                    → list spaces (creator: own; admin: all)
GET    /api/v1/spaces/{id}               → space detail
PUT    /api/v1/spaces/{id}               → update space
DELETE /api/v1/spaces/{id}               → delete space
POST   /api/v1/spaces/{id}/items         → add content_item to space
DELETE /api/v1/spaces/{id}/items/{cid}   → remove content item
PUT    /api/v1/spaces/{id}/items/{cid}   → update item (position, visibility)
POST   /api/v1/spaces/{id}/publish       → publish space
POST   /api/v1/spaces/{id}/share         → generate share token
GET    /api/v1/spaces/public/{token}     → guest access (no auth)
POST   /api/v1/spaces/{id}/access        → grant learner access
DELETE /api/v1/spaces/{id}/access/{uid}  → revoke learner access
```

#### Content Ingest (existing, reused)
```
POST /api/v1/ingest/file        → upload PDF/TXT/video file
POST /api/v1/ingest             → ingest URL (YouTube, Vimeo, HTML page)
GET  /api/v1/jobs/{job_id}      → poll job status
```

#### Content Outputs (existing, reused)
```
GET/PUT  /api/v1/content/{id}/summary
GET/PUT/DELETE /api/v1/content/{id}/glossary
GET/POST/PUT/DELETE /api/v1/content/{id}/flashcards
GET/POST/PUT/DELETE /api/v1/content/{id}/quiz-questions
GET      /api/v1/content/{id}/infographic/html
POST     /api/v1/content/{id}/generate         → trigger generation
POST     /api/v1/content/{id}/flashcards/regenerate
POST     /api/v1/content/{id}/quiz-questions/regenerate
```

---

## Security Model

1. **JWT access token** (15-min expiry) — stored in memory (Zustand), sent as Authorization header from Next.js server routes only
2. **JWT refresh token** (7-day expiry) — stored in HttpOnly, Secure, SameSite=Strict cookie
3. **FastAPI API key** — stored in Next.js `.env.local` as `AXIS_AI_KEY`, never exposed to browser
4. **All FastAPI calls** proxy through Next.js `/api/*` route handlers
5. **Role enforcement** — Next.js middleware checks JWT role claim before rendering any protected route
6. **Guest access** — share token appended to URL, validated by FastAPI on the public endpoint
7. **File uploads** — MIME type + magic bytes validated server-side; streamed to FastAPI
8. **Rate limiting** — Next.js API routes apply per-user Redis counter before forwarding to FastAPI
9. **CSRF** — SameSite=Strict cookie + custom header (`X-Requested-With`) on state-changing requests
