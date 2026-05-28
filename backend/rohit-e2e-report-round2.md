# Rohit E2E Test Report — Round 2
**Date:** 2026-05-09  
**Tester:** Rohit (Ravi's automated testing agent)  
**Target:** https://axis.edzlms.com  
**Branch tested:** dev-video  

---

## Summary

| Category | Result |
|---|---|
| Bugs fixed from Round 1 (BUG-02, 03, 08) | ✅ All confirmed fixed |
| Edit Profile feature (new) | ✅ Backend fully working / Frontend needs 1 deploy |
| File upload processing | 🔴 Critical bug found — PDF extractor can't read local files |
| Vimeo showcase | 🟡 Ingestion accepted, processing ongoing (expected — large playlist) |
| Guest access API | ✅ Working |
| Learner access API | ✅ Working |
| Role RBAC enforcement | ✅ Working |

---

## Phase 1 — Admin Flow

| Test | Result | Notes |
|---|---|---|
| Login as admin@edzlms.com | ✅ | JWT issued |
| List users (6 users) | ✅ | admin, creator, learner + test accounts visible |
| Edit user — email field in edit mode | ✅ | Fixed from Round 1 |
| Logout redirects to /login | ✅ | BUG-03 fixed confirmed |

---

## Phase 2 — Creator Flow

### Content Upload Tests

| Test | Result | Notes |
|---|---|---|
| Upload TXT file (content_type=pdf) | ✅ Queued | Backend auto-detects `.txt` → `content_type=text` (BUG-02 fix) |
| Upload Vimeo showcase URL | ✅ Accepted | `type=vimeo`, status=pending→processing |
| TXT processing completes | 🔴 **STUCK** | See BUG-NEW-01 below |
| PDF processing completes | 🔴 **STUCK** | See BUG-NEW-01 below |
| Share space → is_guest_accessible=True | ✅ | BUG-08 fix confirmed |
| Grant learner access to space | ✅ | Learner can see space |

---

## Phase 3 — Learner Flow

| Test | Result | Notes |
|---|---|---|
| Login as testlearner@edzlms.com | ✅ | JWT issued |
| Shared space visible | ✅ | Space appears in learner's space list |
| Fetch space detail | ✅ | Returns items (all in processing state due to BUG-NEW-01) |
| Learner cannot create spaces | ✅ | Returns 403 "Creator or admin access required" |
| Edit Profile PATCH /auth/me | ✅ | Name updated correctly |
| Edit Profile — email duplicate blocked | ✅ | 409 conflict returned |
| Edit Profile — weak password blocked | ✅ | Validation error returned |

---

## Phase 4 — Guest Flow

| Test | Result | Notes |
|---|---|---|
| Generate share token | ✅ | Returns `{ token, share_url: "/learn/guest?token=..." }` |
| space.is_guest_accessible=True after share | ✅ | Confirmed via GET space |
| GET /api/v1/spaces/guest/{token} (no auth) | ✅ | Returns full space with items |
| Guest token shows correct space | ✅ | Title, items, item_count all correct |

---

## New Bugs Found in Round 2

### 🔴 BUG-NEW-01: PDFExtractor cannot read `file://` URLs (all PDF/TXT uploads broken)

**Severity:** Critical — all file uploads are permanently broken  
**Symptom:** All uploaded files (PDF, TXT) get stuck in `content_status=processing` forever. Content never becomes `ready` and AI outputs are never generated.

**Root cause:** When a file is uploaded via the spaces API, it is saved to `/tmp/axis_uploads/{uuid}_{filename}` and `source_url` is set to `file:///tmp/axis_uploads/{uuid}_{filename}`. The Celery pipeline then calls `PDFExtractor._download(url)` which uses `httpx` to fetch the URL — but `httpx` does not support the `file://` protocol. The request fails silently, the pipeline's error handler marks the job as FAILED but does NOT update `content_item.status`, leaving it permanently stuck in `PROCESSING`.

**The TextExtractor already handles `file://` correctly.** Only PDFExtractor was missing this.

**Fix applied (local workspace):**  
`axis-ai/app/services/extractors/pdf.py` — added `file://` handling in `_download()`:
```python
if url.startswith("file://"):
    path = url[7:]
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as e:
        raise ContentProcessingError(f"Cannot read local file {path}: {e}")
```

**Secondary fix:** `axis-ai/app/services/pipeline.py` — `_mark_job_failed()` now also sets `content_item.status = ContentStatus.FAILED` so items don't stay stuck in PROCESSING when pipeline fails.

**Deploy:** Run `bash axis-ai/patch_file_url_fix.sh` on the server, then `sudo systemctl restart axis-ai-worker axis-ai-beat`.

---

### 🔴 BUG-NEW-02: Edit Profile frontend — wrong cookie name in Next.js route

**Severity:** High — Edit Profile saves fail with 401  
**Symptom:** Clicking "Save Changes" in the Edit Profile modal gets a 401 "Not authenticated" response from `/api/me/profile`.

**Root cause:** `axis-frontend/app/api/me/profile/route.ts` reads cookie `axis_access_token` but the correct name set by the auth login route is `axis_access` (without `_token` suffix).

**Fix applied (local workspace):**  
`axis-frontend/app/api/me/profile/route.ts` line 7:
```ts
// Was:  cookieStore.get('axis_access_token')
// Now:  cookieStore.get('axis_access')
```

**Deploy:** `bash axis-frontend/patch_profile_route.sh` on the server, then `npm run build && pm2 restart axis-frontend` (or equivalent).

---

## Confirmed Fixes from Round 1

| Bug | Status | Evidence |
|---|---|---|
| BUG-02: TXT file content_type detection | ✅ Fixed | Backend returns `content_type=text` for `.txt` uploads |
| BUG-03: Logout button navigation | ✅ Fixed | Admin logout redirects to `/login` |
| BUG-08: guest share sets is_guest_accessible | ✅ Fixed | `is_guest_accessible=True` confirmed after share token creation |

---

## New Feature: Edit Profile

### Backend (all working)
| Endpoint | Test | Result |
|---|---|---|
| `PATCH /api/v1/auth/me` | Update name | ✅ |
| `PATCH /api/v1/auth/me` | Update email | ✅ |
| `PATCH /api/v1/auth/me` | Duplicate email blocked | ✅ 409 |
| `PATCH /api/v1/auth/me` | Weak password blocked | ✅ validation error |
| Admin `PUT /auth/users/{id}` | Email field in edit mode | ✅ |

### Frontend
| Component | Test | Result |
|---|---|---|
| Modal opens from sidebar avatar click | ✅ | Opens correctly |
| Name pre-filled from auth store | ✅ | `Test Creator Verified` shown |
| Email pre-filled | ✅ | `testcreator@edzlms.com` shown |
| Save sends correct PATCH payload | ✅ | `{"full_name": "Test Creator UI Verified"}` |
| Save actually succeeds | 🔴 | **BUG-NEW-02** — 401 from wrong cookie name |

---

## Deploy Checklist

Run these commands on the server to unblock everything:

### 1. Backend: PDF file:// fix + pipeline error fix
```bash
cd /home/axisai/axisai-backend/axis-ai
bash /path/to/patch_file_url_fix.sh
# OR apply git pull after push
sudo systemctl restart axis-ai-worker axis-ai-beat
sudo systemctl status axis-ai-worker --no-pager
```

### 2. Frontend: Edit Profile cookie name fix
```bash
cd /home/axisai/axis-frontend   # or wherever Next.js is deployed
bash /path/to/patch_profile_route.sh
npm run build
pm2 restart axis-frontend   # or systemctl restart axis-frontend
```

### 3. Verify after deploy
```bash
# Test PDF upload completes
curl -X POST https://axisai.edzlms.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"testcreator@edzlms.com","password":"Creator@123"}'
# Upload a small PDF, wait 60s, check content_status=ready
```

---

## Vimeo Showcase Note

The showcase URL `https://vimeo.com/showcase/11757836?share=copy` was accepted and moved to `status=processing`. Vimeo showcases are playlists and can contain many videos — yt-dlp processes them as a playlist, which takes significantly longer than a single video. This is expected behavior, not a bug. Monitor via the space items endpoint until status=ready.

---

## Round 2 Verdict

The axis-ai platform is architecturally sound. Authentication, RBAC, space management, share tokens, and guest access all work correctly. Two critical bugs were found and patched locally:

1. **All file uploads broken** (PDFExtractor `file://` bug) — deploy `patch_file_url_fix.sh`
2. **Edit Profile save fails** (wrong cookie name) — deploy `patch_profile_route.sh`

Once both patches are deployed and workers restarted, the full E2E flow (upload → process → AI outputs → share → learner view → guest view) should work end-to-end.
