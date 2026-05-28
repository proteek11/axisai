# axis-frontend Deployment Guide

Full step-by-step guide to deploying the Next.js 14 frontend to `axis.edzlms.com` on your Ubuntu 24.04 VPS alongside the existing axis-ai FastAPI backend.

---

## Prerequisites

- Ubuntu 24.04 VPS (same server as `axisai.edzlms.com`)
- Existing axis-ai FastAPI service running and healthy
- `axisai` user with sudo access
- DNS A record for `axis.edzlms.com` pointing to the VPS IP
- Node.js 20+ and npm installed

---

## Step 0 — Verify DNS and existing services

```bash
# Check DNS has propagated
dig axis.edzlms.com +short

# Confirm axis-ai backend is running
curl https://axisai.edzlms.com/api/v1/health
# Expected: {"status": "healthy", ...}

# Check running systemd services
for svc in postgresql redis-server qdrant nginx axis-ai axis-ai-worker axis-ai-beat; do
  systemctl is-active "$svc"
done
# All should print "active"
```

---

## Step 1 — Install Node.js 20 (if not installed)

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
node --version   # should print v20.x
npm --version
```

---

## Step 2 — Install PM2 globally

```bash
sudo npm install -g pm2
pm2 --version
```

---

## Step 3 — Create initial users (seed script)

Run this once against the FastAPI backend to create admin, creator, and learner accounts:

```bash
cd /home/axisai/axisai-backend/axis-ai
source .venv/bin/activate
python scripts/seed_users.py

# Credentials written to:
cat /home/axisai/AXIS_CREDENTIALS.txt
# KEEP THIS FILE PRIVATE: chmod 600 /home/axisai/AXIS_CREDENTIALS.txt
```

---

## Step 4 — Install backend Python dependencies

The following packages were added to `pyproject.toml`. Run the install:

```bash
cd /home/axisai/axisai-backend/axis-ai
source .venv/bin/activate
pip install -e .
```

New dependencies added:
- `passlib[bcrypt]>=1.7.4` — password hashing
- `python-jose[cryptography]>=3.3.0` — JWT tokens
- `python-slugify>=8.0.0` — Learning Space slug generation

---

## Step 5 — Run Alembic migration 008

Migration 008 creates the 6 new tables needed by the frontend (axis_users, refresh_tokens, learning_spaces, space_items, space_access, share_tokens).

```bash
cd /home/axisai/axisai-backend/axis-ai
source .venv/bin/activate
alembic upgrade head

# Verify:
python -c "
import asyncio
from app.core.database import engine
from sqlalchemy import text, inspect
async def check():
    async with engine.connect() as conn:
        result = await conn.execute(text(\"SELECT tablename FROM pg_tables WHERE schemaname='public'\"))
        print([r[0] for r in result])
asyncio.run(check())
"
# Should include: axis_users, refresh_tokens, learning_spaces, space_items, space_access, share_tokens
```

---

## Step 6 — Add JWT_SECRET to axis-ai .env

The frontend auth uses a shared JWT secret. Add it to the backend `.env`:

```bash
cd /home/axisai/axisai-backend/axis-ai

# Generate a strong secret
JWT_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
echo "JWT_SECRET=$JWT_SECRET" >> .env

# Also save to credentials file
echo "JWT_SECRET=$JWT_SECRET" >> /home/axisai/AXIS_CREDENTIALS.txt

cat .env | grep JWT_SECRET
```

---

## Step 7 — Clone / copy the frontend codebase

```bash
# If deploying from your development machine:
# rsync -avz --exclude=node_modules --exclude=.next ./axis-frontend/ axisai@YOUR_VPS_IP:/home/axisai/axis-frontend/

# Or if it's part of the same monorepo:
cp -r /home/axisai/axisai-backend/axis-frontend /home/axisai/axis-frontend
cd /home/axisai/axis-frontend
```

---

## Step 8 — Create .env.local for the frontend

```bash
cd /home/axisai/axis-frontend

# Read credentials from the backend
AXIS_AI_KEY=$(grep MASTER_API_KEY /home/axisai/axisai-backend/axis-ai/.env | cut -d= -f2)
JWT_SECRET=$(grep JWT_SECRET /home/axisai/axisai-backend/axis-ai/.env | cut -d= -f2)

cat > .env.local << EOF
# axis-ai backend
AXIS_AI_URL=https://axisai.edzlms.com
AXIS_AI_KEY=${AXIS_AI_KEY}

# JWT — MUST match the JWT_SECRET in the FastAPI backend .env
JWT_SECRET=${JWT_SECRET}

# Public URL of this Next.js app
NEXT_PUBLIC_APP_URL=https://axis.edzlms.com

# Node environment
NODE_ENV=production
EOF

chmod 600 .env.local
echo "✓ .env.local created"
cat .env.local | grep -v KEY | grep -v SECRET   # show non-secret lines
```

---

## Step 9 — Install dependencies and build

```bash
cd /home/axisai/axis-frontend
npm install
npm run build

# Verify build succeeded
ls -la .next/
```

The build output will be in `.next/`. This is what PM2 will serve.

---

## Step 10 — Create log directory and start with PM2

```bash
mkdir -p /home/axisai/logs

cd /home/axisai/axis-frontend
pm2 start ecosystem.config.js --env production

# Verify it started
pm2 status
pm2 logs axis-frontend --lines 20

# Check the app is responding
curl http://localhost:3000
```

---

## Step 11 — Configure PM2 to start on boot

```bash
pm2 save
pm2 startup
# PM2 will print a command like:
# sudo env PATH=$PATH:/usr/bin /usr/lib/node_modules/pm2/bin/pm2 startup systemd -u axisai --hp /home/axisai
# Run that command exactly as printed.
```

---

## Step 12 — Configure Nginx

```bash
# Copy the nginx config
sudo cp /home/axisai/axis-frontend/docs/nginx-axis-frontend.conf \
        /etc/nginx/sites-available/axis-frontend

# Enable the site
sudo ln -sf /etc/nginx/sites-available/axis-frontend \
            /etc/nginx/sites-enabled/axis-frontend

# Test config
sudo nginx -t
# Expected: nginx: configuration file /etc/nginx/nginx.conf test is successful

# Reload
sudo systemctl reload nginx
```

---

## Step 13 — Get SSL certificate

**Wait for DNS propagation before running Certbot.**

```bash
# Verify DNS first:
dig axis.edzlms.com +short   # must return your VPS IP

# Get certificate:
sudo certbot --nginx -d axis.edzlms.com

# Certbot will automatically modify the nginx config to add HTTPS.
# Test renewal:
sudo certbot renew --dry-run
```

---

## Step 14 — Smoke test

```bash
# Health checks
curl https://axis.edzlms.com                   # should return Next.js HTML
curl https://axis.edzlms.com/api/auth/me       # should return 401 (not logged in)
curl https://axisai.edzlms.com/api/v1/health   # FastAPI still healthy

# Check PM2
pm2 status
pm2 logs axis-frontend --lines 10

# Check all systemd services still running
for svc in nginx postgresql redis-server qdrant axis-ai axis-ai-worker axis-ai-beat; do
  echo "$svc: $(systemctl is-active $svc)"
done
```

---

## Updating the frontend after code changes

```bash
cd /home/axisai/axis-frontend
# Pull latest code (or rsync from dev machine)
npm install
npm run build
pm2 reload axis-frontend
pm2 logs axis-frontend --lines 20
```

---

## Troubleshooting

### PM2 app not starting
```bash
pm2 logs axis-frontend --err --lines 50
# Check .env.local exists and has all required vars
cat /home/axisai/axis-frontend/.env.local
```

### 502 Bad Gateway from Nginx
```bash
pm2 status   # is axis-frontend running?
curl http://localhost:3000   # can nginx reach the app?
sudo nginx -t   # any config errors?
```

### Auth not working (login fails)
```bash
# Check JWT_SECRET matches between frontend and backend
grep JWT_SECRET /home/axisai/axis-frontend/.env.local
grep JWT_SECRET /home/axisai/axisai-backend/axis-ai/.env
# They MUST be identical
```

### Database migration failed
```bash
cd /home/axisai/axisai-backend/axis-ai
source .venv/bin/activate
alembic current    # see current revision
alembic history    # see all migrations
alembic upgrade head --sql | head -50   # preview SQL without running
```

### Users not found after seeding
```bash
cd /home/axisai/axisai-backend/axis-ai
source .venv/bin/activate
python scripts/seed_users.py   # idempotent — safe to run again
cat /home/axisai/AXIS_CREDENTIALS.txt
```

---

## Port summary

| Service            | Port  | Bound to  |
|--------------------|-------|-----------|
| axis-ai FastAPI    | 8000  | localhost |
| axis-frontend Next | 3000  | localhost |
| Nginx              | 80/443| 0.0.0.0   |
| PostgreSQL         | 5432  | localhost |
| Redis              | 6379  | localhost |
| Qdrant             | 6333  | localhost |

No application ports are exposed to the internet — everything goes through Nginx.
