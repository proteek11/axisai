# axis.edzlms.com Administrator Guide

Complete reference for platform administrators.

---

## Initial Setup Checklist

After deployment, complete these steps in order:

1. **Seed initial users** — run `python scripts/seed_users.py` on the server
2. **Get credentials** — read `/home/axisai/AXIS_CREDENTIALS.txt`
3. **Log in as admin** — go to https://axis.edzlms.com/login
4. **Enable AI features** — Admin → Feature Control → toggle on the outputs you want
5. **Add KB documents** — Admin → Knowledge Base → Add Document (optional)
6. **Create a creator account** — Users page shows all accounts; creators are seeded automatically
7. **Share creator credentials** — give the creator their login from the credentials file

---

## User Roles

| Role    | Can Do |
|---------|--------|
| Admin   | Full platform access, feature toggles, KB management, usage reports, audit log, user list |
| Creator | Create Learning Spaces, upload content, manage AI outputs, share spaces with learners |
| Learner | Access assigned Learning Spaces, study AI outputs, use AI chat |

Users are created via the seed script. To add more users, extend `scripts/seed_users.py` or use the API directly:

```bash
curl -X POST https://axisai.edzlms.com/api/v1/auth/register \
  -H "Authorization: Bearer <admin_jwt>" \
  -H "Content-Type: application/json" \
  -d '{"email": "new@domain.com", "full_name": "New User", "role": "learner", "password": "SecurePass123"}'
```

---

## Feature Control

Navigate to **Admin → Feature Control** to enable/disable AI output types.

Available outputs:
- **Summary** — concise text summary of any content
- **Quiz** — multiple-choice questions with Bloom's taxonomy levels
- **Flashcards** — front/back study cards
- **Glossary** — key term definitions
- **FAQ** — frequently asked questions
- **Infographic** — visual HTML infographic
- **Mind Map** — hierarchical concept map
- **Objectives** — extracted learning objectives
- **Bloom's** — Bloom's taxonomy analysis

Disabling a feature prevents new outputs being generated but does not delete existing ones.

---

## Knowledge Base Management

The Knowledge Base powers the **Support Chat** — a separate RAG system for answering platform or subject-matter support questions.

To add a KB document:
1. Admin → Knowledge Base → Add Document
2. Choose **Plain Text** (paste content) or **URL** (fetch from a webpage)
3. Enter a title
4. Click Add Document — content is automatically chunked and embedded

KB documents are searched via Qdrant's `axis_kb_chunks` collection. Deletions also remove the vectors.

---

## Usage & Costs

Admin → Usage & Limits shows:
- **Total tokens** consumed (prompt + completion split)
- **Cost in USD** (based on OpenAI pricing)
- **API requests** count
- **Active users** (who made at least one request)
- **Daily usage chart**
- **Token breakdown by output type**
- **Top users by consumption**

Select period: 7 days / 30 days / 90 days.

Token usage is tracked in the `audit_logs` table. Cost estimates use hardcoded OpenAI pricing — update in `app/services/ai/client.py` if pricing changes.

---

## Audit Log

Admin → Audit Log shows every API call:
- Timestamp
- User email (or anonymous for guest)
- HTTP method + path (action)
- Resource type and ID
- Response status code (colored: green=2xx, orange=4xx, red=5xx)
- Click any row to expand and see full request details (JSON)

The audit log is paginated (50 per page). Older entries are never deleted automatically — add a cron job or DB-level partition if you need retention limits.

---

## Backup & Restore

### Database backup
```bash
sudo -u postgres pg_dump axis_ai > /home/axisai/backups/axis_ai_$(date +%Y%m%d).sql
```

### Qdrant backup
Qdrant does not have built-in snapshot tooling via the CLI. Use the REST API:
```bash
curl -X POST http://localhost:6333/collections/axis_content_chunks/snapshots
# Returns a snapshot file in /opt/qdrant/storage/snapshots/
```

### Redis backup
Redis RDB snapshots are at `/var/lib/redis/dump.rdb`. Copy this file.

---

## Changing Credentials

### Admin password
Log in as admin → the profile page will have a password change form.

Or via API:
```bash
curl -X PUT https://axis.edzlms.com/api/auth/me \
  -H "Authorization: Bearer <admin_jwt>" \
  -H "Content-Type: application/json" \
  -d '{"current_password": "old", "new_password": "new_secure_password"}'
```

### Rotating JWT secret
1. Generate new secret: `python -c "import secrets; print(secrets.token_hex(32))"`
2. Update `JWT_SECRET` in `/home/axisai/axisai-backend/axis-ai/.env`
3. Update `JWT_SECRET` in `/home/axisai/axis-frontend/.env.local`
4. Restart both services:
   ```bash
   sudo systemctl restart axis-ai
   pm2 reload axis-frontend
   ```
5. **All existing sessions will be invalidated** — users must log in again.

---

## Monitoring

### Service health
```bash
# Quick health check
curl https://axis.edzlms.com/api/auth/me   # should return 401 (not 502)
curl https://axisai.edzlms.com/api/v1/health

# PM2 status
pm2 status
pm2 logs axis-frontend --lines 20

# Systemd services
systemctl status axis-ai axis-ai-worker axis-ai-beat --no-pager
```

### Log locations
| Service | Log Location |
|---------|-------------|
| axis-frontend (PM2) | `/home/axisai/logs/axis-frontend.log` |
| axis-frontend errors | `/home/axisai/logs/axis-frontend-error.log` |
| axis-ai FastAPI | `journalctl -u axis-ai -n 100` |
| axis-ai Celery worker | `journalctl -u axis-ai-worker -n 100` |
| Nginx access | `/var/log/nginx/access.log` |
| Nginx error | `/var/log/nginx/error.log` |

---

## Security Hardening Notes

1. `.env.local` and the backend `.env` are chmod 600 — never commit them to git
2. `AXIS_CREDENTIALS.txt` is chmod 600 — only the `axisai` user can read it
3. The AXIS_AI_KEY (master API key) never reaches the browser — it lives in server-only Next.js config
4. All cookies use `HttpOnly` + `SameSite=Strict` + `Secure` in production
5. JWT access tokens expire in 15 minutes; refresh tokens expire in 7 days
6. Rate limiting: 30 req/min per IP via Nginx (configured in the vhost)

---

## Emergency: Reset all user sessions

To force all users to log out immediately (e.g., after a security incident):

```bash
cd /home/axisai/axisai-backend/axis-ai
source .venv/bin/activate
python -c "
import asyncio
from app.core.database import engine, AsyncSessionLocal
from app.models.user import RefreshToken
from sqlalchemy import delete
async def nuke():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(RefreshToken))
        await db.commit()
        print('All refresh tokens deleted — all users logged out')
asyncio.run(nuke())
"
```
