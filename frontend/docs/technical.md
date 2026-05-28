# axis-frontend — Technical Specification
> Version 1.0 | Phase 1 | May 2026

---

## System Architecture

```
Browser
  │
  │  HTTPS
  ▼
axis.edzlms.com  (Next.js 14, PM2, Nginx port 3000)
  │
  │  Server-side only (AXIS_AI_KEY header, same VPS LAN)
  ▼
axisai.edzlms.com  (FastAPI, Uvicorn port 8000)
  │
  ├── PostgreSQL 15 (port 5432)
  ├── Redis 7 (port 6379)
  └── Qdrant (port 6333)
```

---

## FastAPI Backend Extensions

### New DB Tables (Alembic migration 008)

```sql
-- Application users (NOT Moodle users)
CREATE TABLE axis_users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email       VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,          -- bcrypt, cost=12
    full_name   VARCHAR(255),
    role        VARCHAR(20) NOT NULL,              -- admin | creator | learner
    is_active   BOOLEAN DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_axis_users_tenant ON axis_users(tenant_id);
CREATE INDEX idx_axis_users_email  ON axis_users(email);

-- Refresh tokens (one per user session)
CREATE TABLE refresh_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES axis_users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(64) NOT NULL UNIQUE,       -- SHA-256 of raw token
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Learning Spaces
CREATE TABLE learning_spaces (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    creator_id          UUID NOT NULL REFERENCES axis_users(id) ON DELETE CASCADE,
    title               VARCHAR(255) NOT NULL,
    slug                VARCHAR(255) NOT NULL UNIQUE,
    description         TEXT,
    cover_image_url     TEXT,
    is_published        BOOLEAN DEFAULT FALSE,
    is_guest_accessible BOOLEAN DEFAULT FALSE,
    tags                JSONB DEFAULT '[]',
    metadata            JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_spaces_tenant   ON learning_spaces(tenant_id);
CREATE INDEX idx_spaces_creator  ON learning_spaces(creator_id);
CREATE INDEX idx_spaces_slug     ON learning_spaces(slug);

-- Space Items (content within a space)
CREATE TABLE space_items (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    space_id         UUID NOT NULL REFERENCES learning_spaces(id) ON DELETE CASCADE,
    content_item_id  UUID NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
    position         INTEGER DEFAULT 0,
    title_override   VARCHAR(255),
    is_visible       BOOLEAN DEFAULT TRUE,
    -- Which AI outputs are visible to learners in this space context
    visible_outputs  JSONB DEFAULT '["summary","glossary","flashcards","quiz","infographic"]',
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(space_id, content_item_id)
);

-- Space Access (which learners can access a space)
CREATE TABLE space_access (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    space_id   UUID NOT NULL REFERENCES learning_spaces(id) ON DELETE CASCADE,
    user_id    UUID NOT NULL REFERENCES axis_users(id) ON DELETE CASCADE,
    granted_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(space_id, user_id)
);

-- Share Tokens (for guest/link-based access)
CREATE TABLE share_tokens (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    space_id     UUID NOT NULL REFERENCES learning_spaces(id) ON DELETE CASCADE,
    token        VARCHAR(64) NOT NULL UNIQUE,      -- random, URL-safe
    expires_at   TIMESTAMPTZ,                      -- NULL = never expires
    access_count INTEGER DEFAULT 0,
    max_access   INTEGER,                          -- NULL = unlimited
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
```

### New FastAPI Files

```
app/
├── models/
│   ├── user.py          # AxisUser, RefreshToken
│   └── space.py         # LearningSpace, SpaceItem, SpaceAccess, ShareToken
├── schemas/
│   ├── auth.py          # LoginRequest, TokenResponse, UserResponse
│   └── space.py         # SpaceCreate, SpaceResponse, SpaceItemCreate, etc.
├── api/v1/
│   ├── auth.py          # /auth/login, /auth/refresh, /auth/logout, /auth/me
│   └── spaces.py        # Full CRUD + publish + share
└── core/
    └── jwt.py           # JWT encode/decode, password hashing (bcrypt)
```

### JWT Design
- Access token: 15-minute expiry, signed HS256 with `settings.secret_key`
- Refresh token: 7-day expiry, SHA-256 hash stored in DB
- Payload: `{sub: user_id, email, role, tenant_id, exp, iat}`
- Dependency: `get_current_user(token)` → validates JWT, returns AxisUser

### Seed Script
```
scripts/seed_users.py  — creates 3 default users + master tenant API key
```
Credentials written to `/home/axisai/AXIS_CREDENTIALS.txt` (chmod 600).

---

## Next.js Frontend Architecture

### Tech Stack
| Layer | Choice | Reason |
|-------|--------|--------|
| Framework | Next.js 14 (App Router) | SSR, API routes, file-based routing |
| Styling | Tailwind CSS + shadcn/ui | Brand tokens, consistent components |
| State | Zustand | Lightweight, no boilerplate |
| Server state | TanStack Query (React Query) | Caching, background refresh, polling |
| Auth | HttpOnly cookie (refresh) + memory (access) | Secure, XSS-resistant |
| Forms | React Hook Form + Zod | Type-safe validation |
| Icons | lucide-react | Consistent with brand reference |
| Fonts | Instrument Sans + Geist (next/font/google) | Brand spec |
| HTTP client | ky (tiny fetch wrapper) | Server-side API routes |
| File upload | Native fetch + FormData | Streams to FastAPI |
| Animations | Framer Motion | Flashcard 3D flip, transitions |

### Project Structure
```
axis-frontend/
├── app/
│   ├── layout.tsx                    # Root layout: fonts, providers, theme
│   ├── globals.css                   # Brand CSS variables + Tailwind base
│   ├── (auth)/
│   │   ├── login/page.tsx            # Login page
│   │   └── layout.tsx                # Auth layout (centered card)
│   ├── (dashboard)/
│   │   ├── layout.tsx                # Sidebar + header shell
│   │   ├── dashboard/page.tsx        # Role-aware home dashboard
│   │   ├── spaces/
│   │   │   ├── page.tsx              # Spaces list (creator/admin)
│   │   │   ├── new/page.tsx          # Create space
│   │   │   └── [id]/
│   │   │       ├── page.tsx          # Space detail (creator view)
│   │   │       ├── edit/page.tsx     # Edit space metadata
│   │   │       └── content/
│   │   │           └── [contentId]/
│   │   │               └── page.tsx  # Content workspace (5 tabs)
│   │   ├── admin/
│   │   │   ├── layout.tsx            # Admin guard (role check)
│   │   │   ├── page.tsx              # Admin dashboard
│   │   │   ├── features/page.tsx     # Feature toggles
│   │   │   ├── kb/page.tsx           # Knowledge Base manager
│   │   │   ├── users/page.tsx        # User seeds view
│   │   │   ├── usage/page.tsx        # Token usage charts
│   │   │   └── audit/page.tsx        # Audit log
│   │   └── settings/page.tsx         # Profile + API key
│   ├── learn/
│   │   ├── [spaceId]/
│   │   │   ├── page.tsx              # Learner space overview
│   │   │   └── [contentId]/page.tsx  # Content study view (tabs)
│   │   └── guest/
│   │       └── [token]/
│   │           ├── page.tsx          # Public space (no auth)
│   │           └── [contentId]/page.tsx
│   └── api/
│       ├── auth/
│       │   ├── login/route.ts        # POST: proxy to FastAPI auth
│       │   ├── refresh/route.ts      # POST: refresh JWT
│       │   ├── logout/route.ts       # POST: clear cookie
│       │   └── me/route.ts           # GET: current user
│       ├── spaces/
│       │   ├── route.ts              # GET list, POST create
│       │   └── [id]/
│       │       ├── route.ts          # GET, PUT, DELETE
│       │       ├── items/route.ts    # POST add item
│       │       ├── publish/route.ts  # POST publish
│       │       └── share/route.ts    # POST generate share token
│       ├── content/
│       │   ├── ingest/route.ts       # POST: file or URL ingest
│       │   ├── jobs/[jobId]/route.ts # GET: poll job
│       │   └── [id]/
│       │       ├── summary/route.ts
│       │       ├── glossary/route.ts
│       │       ├── flashcards/route.ts
│       │       ├── quiz/route.ts
│       │       └── infographic/route.ts
│       └── admin/
│           ├── features/route.ts
│           ├── kb/route.ts
│           ├── users/route.ts
│           └── usage/route.ts
├── components/
│   ├── ui/                           # shadcn/ui (auto-generated)
│   ├── layout/
│   │   ├── sidebar.tsx               # Enterprise sidebar, role-aware nav
│   │   ├── header.tsx                # Top bar: user avatar, notifications
│   │   ├── page-header.tsx           # Page title + date + CTA
│   │   └── stat-card.tsx             # Reusable stat card component
│   ├── spaces/
│   │   ├── space-card.tsx            # Space list card
│   │   ├── space-form.tsx            # Create/edit space form
│   │   ├── content-upload-modal.tsx  # Multi-type upload dialog
│   │   ├── job-progress.tsx          # Live job status ring/bar
│   │   └── publish-panel.tsx         # Publish + share link generator
│   ├── workspace/
│   │   ├── workspace-tabs.tsx        # 5-tab container
│   │   ├── summary-tab.tsx           # Read + inline edit
│   │   ├── glossary-tab.tsx          # Table CRUD + drag reorder
│   │   ├── flashcards-tab.tsx        # Card grid + edit
│   │   ├── quiz-tab.tsx              # Question table + editor
│   │   └── infographic-tab.tsx       # srcdoc iframe renderer
│   ├── study/
│   │   ├── study-tabs.tsx            # Learner tab container
│   │   ├── summary-reader.tsx        # Reader view + font controls
│   │   ├── glossary-browser.tsx      # Searchable alpha index
│   │   ├── flashcard-game.tsx        # 3D flip + self-assessment
│   │   ├── quiz-engine.tsx           # Step MCQ + results
│   │   └── chat-panel.tsx            # Floating RAG study chat
│   └── admin/
│       ├── feature-toggles.tsx       # Feature toggle switches
│       ├── kb-manager.tsx            # KB CRUD table
│       └── usage-chart.tsx           # Token usage bar chart
├── lib/
│   ├── api/
│   │   ├── client.ts                 # Typed fetch wrapper (server-side)
│   │   ├── auth.ts                   # Auth API calls
│   │   ├── spaces.ts                 # Spaces API calls
│   │   ├── content.ts                # Content/output API calls
│   │   └── admin.ts                  # Admin API calls
│   ├── auth/
│   │   ├── tokens.ts                 # JWT decode (client-side, no verify)
│   │   └── session.ts                # Cookie management
│   ├── hooks/
│   │   ├── use-user.ts               # Current user from Zustand
│   │   ├── use-job-poll.ts           # TanStack Query job poller
│   │   └── use-spaces.ts             # Spaces queries
│   └── stores/
│       ├── auth-store.ts             # Zustand: user, access token
│       └── ui-store.ts               # Zustand: sidebar collapsed, theme
├── middleware.ts                     # Route protection by role
├── next.config.js
├── tailwind.config.ts
├── components.json                   # shadcn/ui config
├── .env.local                        # AXIS_AI_URL, AXIS_AI_KEY, JWT_SECRET
├── package.json
├── ecosystem.config.js               # PM2 config
└── tsconfig.json
```

### Middleware Route Protection
```
/admin/*          → requires role: admin
/(dashboard)/*    → requires any authenticated role
/spaces/*         → requires role: admin | creator
/learn/*          → requires role: learner | admin | creator (or guest token)
/learn/guest/*    → no auth required (validates share token server-side)
/api/admin/*      → requires role: admin in JWT
/api/spaces/*     → requires role: admin | creator in JWT
```

### Environment Variables (.env.local)
```bash
AXIS_AI_URL=http://localhost:8000        # Internal (same server — no SSL needed)
AXIS_AI_KEY=axisai_<tenant_api_key>      # FastAPI tenant API key
JWT_SECRET=<same as FastAPI secret_key>  # Must match FastAPI settings
NEXTAUTH_URL=https://axis.edzlms.com
NODE_ENV=production
```

---

## Nginx Configuration (axis.edzlms.com)

New server block alongside existing axisai.edzlms.com:

```nginx
server {
    listen 80;
    server_name axis.edzlms.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name axis.edzlms.com;

    # SSL (added by Certbot)
    ssl_certificate /etc/letsencrypt/live/axis.edzlms.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/axis.edzlms.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";
    add_header X-XSS-Protection "1; mode=block";
    add_header Referrer-Policy "strict-origin-when-cross-origin";

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
```

---

## PM2 Process Manager

```js
// ecosystem.config.js
module.exports = {
  apps: [{
    name: 'axis-frontend',
    script: 'node_modules/.bin/next',
    args: 'start',
    cwd: '/home/axisai/axis-frontend',
    instances: 'max',
    exec_mode: 'cluster',
    env_production: {
      NODE_ENV: 'production',
      PORT: 3000,
    },
  }]
}
```
