# axis-frontend

**Next.js 14 frontend for axis.edzlms.com** — the standalone web interface for the axis-ai learning intelligence platform. Talks to the FastAPI backend at `axisai.edzlms.com`.

---

## What this is

axis-frontend provides a complete, role-based web interface that sits on top of the axis-ai FastAPI service. It introduces the concept of **Learning Spaces** — structured containers of content (PDFs, YouTube videos, Vimeo videos, uploaded videos) that creators build and share with learners. Each piece of content is processed by the AI pipeline to generate summaries, glossaries, flashcards, quizzes, and infographics.

### Roles

| Role    | Access |
|---------|--------|
| Admin   | Platform administration — feature toggles, KB management, usage analytics, audit log, user list |
| Creator | Build Learning Spaces, upload & process content, review AI outputs, share with learners |
| Learner | Study assigned spaces — read summaries, search glossary, flip flashcards, take quizzes, use AI chat |
| Guest   | Preview publicly-shared spaces via share token (no login required) |

---

## Tech stack

- **Next.js 14** (App Router, TypeScript)
- **Tailwind CSS** + **shadcn/ui** components
- **TanStack Query v5** — server state, job polling, background refresh
- **Zustand** — auth store (access token in-memory), UI store (sidebar collapse)
- **React Hook Form** + **Zod** — form validation
- **jose** — server-side JWT decode in middleware
- **Framer Motion** — flashcard 3D flip animation
- **Sonner** — toast notifications
- **date-fns** — date formatting

---

## Project structure

```
axis-frontend/
├── app/
│   ├── (auth)/login/          # Login page (split panel)
│   ├── (dashboard)/           # Protected dashboard layout (sidebar + header)
│   │   ├── dashboard/         # Role-aware dashboard (admin/creator/learner)
│   │   ├── admin/             # Admin screens (features, kb, users, usage, audit)
│   │   ├── spaces/            # Creator: Learning Space CRUD
│   │   ├── content/[id]/      # Creator: AI output workspace (5 tabs)
│   │   └── learn/             # Learner: study views + AI chat
│   ├── learn/guest/           # Public guest view (no auth, share token)
│   └── api/                   # Next.js API routes (proxy to FastAPI)
│       ├── auth/              # login, logout, refresh, me
│       ├── admin/             # status, features, kb, users, usage, audit
│       ├── spaces/            # CRUD, publish, share, items
│       ├── content/           # ingest, jobs, outputs
│       └── chat/              # RAG chat proxy
├── components/
│   ├── layout/                # Sidebar, Header, StatCard
│   ├── admin/                 # Admin-specific components
│   ├── spaces/                # Creator: UploadModal, JobProgress
│   ├── content/               # Creator workspace tabs (summary, glossary, etc.)
│   └── study/                 # Learner study tabs (read-only + interactive)
├── lib/
│   ├── api/client.ts          # Server-only FastAPI proxy (adds API key)
│   ├── stores/                # Zustand stores (auth, ui)
│   └── hooks/                 # useUser, useRole, useJobPoll
├── middleware.ts               # Route protection + JWT auto-refresh
├── tailwind.config.ts
├── next.config.js
└── ecosystem.config.js        # PM2 cluster mode config
```

---

## Security model

**The FastAPI API key never reaches the browser.** All calls to `axisai.edzlms.com` go through Next.js API routes (`/app/api/*`) which read the `AXIS_AI_KEY` from server-only environment variables and inject it as a header. Browser code only ever talks to the Next.js server.

Cookie strategy:
- `axis_refresh` — HttpOnly, Secure, SameSite=Strict. Stores the 7-day refresh token. JavaScript cannot read it.
- `axis_access` — readable, Secure, SameSite=Strict. Stores the 15-minute JWT access token. Used by middleware and client-side API calls.

---

## Quick start (development)

```bash
cd axis-frontend
npm install

# Create .env.local (fill in your values)
cp .env.local.example .env.local
# Edit: AXIS_AI_URL, AXIS_AI_KEY, JWT_SECRET, NEXT_PUBLIC_APP_URL

npm run dev
# Open http://localhost:3000
```

Required environment variables:

```env
AXIS_AI_URL=https://axisai.edzlms.com
AXIS_AI_KEY=your_master_api_key_here
JWT_SECRET=your_jwt_secret_here_must_match_backend
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

`JWT_SECRET` must be identical to the `JWT_SECRET` in the FastAPI backend `.env`.

---

## Deployment

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the full step-by-step production deployment guide including:
- Node.js 20 installation
- PM2 cluster mode setup
- Nginx vhost config (`docs/nginx-axis-frontend.conf`)
- SSL via Certbot
- Alembic migration 008
- User seeding

---

## Admin guide

See [`docs/ADMIN_GUIDE.md`](docs/ADMIN_GUIDE.md) for platform administration including feature control, KB management, usage monitoring, backup/restore, and security hardening.

---

## Testing

See [`docs/testing.txt`](docs/testing.txt) for the full manual test plan covering 40+ test cases across auth, admin, creator, learner, guest access, and security.

---

## Key routes

| Route | Who | What |
|-------|-----|------|
| `/login` | All | Login page |
| `/dashboard` | All | Role-aware dashboard |
| `/admin/features` | Admin | Toggle AI output types |
| `/admin/kb` | Admin | Knowledge base manager |
| `/admin/users` | Admin | User list |
| `/admin/usage` | Admin | Token & cost analytics |
| `/admin/audit` | Admin | API audit trail |
| `/spaces` | Creator | All learning spaces |
| `/spaces/new` | Creator | Create learning space |
| `/spaces/:id` | Creator | Space detail + content upload |
| `/content/:id` | Creator | AI output workspace (5 tabs) |
| `/learn/:spaceId` | Learner | Space study overview |
| `/learn/:spaceId/content/:id` | Learner | Study content + AI chat |
| `/learn/guest?token=...` | Anyone | Public guest preview |

---

## Changelog

### v1.0.0 (Phase 1)
- Learning Space concept with full CRUD
- Content types: PDF/TXT upload, YouTube URL, Vimeo URL, local video upload
- AI outputs: Summary, Glossary, Flashcards, Quiz (Bloom's taxonomy), Infographic
- Role-based auth: Admin, Creator, Learner
- Guest access via share tokens (time-limited, access-count-limited)
- Creator workspace: 5-tab review/edit UI with inline editing
- Learner study mode: interactive flashcard flip, step-through quiz with results
- Floating RAG chat panel on all study pages
- Admin: feature toggles, KB manager, usage charts, audit log, user list
- JWT auth with 15-min access tokens + 7-day HttpOnly refresh tokens
- PM2 cluster mode deployment + Nginx reverse proxy
