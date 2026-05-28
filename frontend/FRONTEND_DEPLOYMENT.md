# Axis AI Frontend — Deployment Guide

**Stack:** Next.js 14 (App Router) · Node.js 20 LTS · PM2 · Nginx · Ubuntu 24.04

**Live URL:** `https://axis.edzlms.com`

---

## Overview

The frontend sits on the **same Ubuntu 24.04 VPS** as the backend (`axisai.edzlms.com`).
Nginx terminates SSL and reverse-proxies traffic:

```
Browser → Nginx (443/SSL) → PM2/Next.js (localhost:3000)
                          → Uvicorn/FastAPI (localhost:8000)  [for /api/* if needed]
```

---

## First-Time Setup (run once)

### 1. Install Node.js 20 LTS

```bash
# Install via NodeSource
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
node -v    # should print v20.x.x
npm -v     # should print 10.x.x
```

### 2. Install PM2

```bash
sudo npm install -g pm2
pm2 -v     # should print 5.x.x
```

### 3. Create log directory

```bash
sudo mkdir -p /var/log/axis-frontend
sudo chown axisai:axisai /var/log/axis-frontend
```

### 4. Clone / pull the repository

```bash
cd /home/axisai
git clone https://github.com/lmsofindia/axisai-backend.git
cd axisai-backend/axis-frontend
```

### 5. Create `.env.local`

```bash
cp .env.example .env.local    # if .env.example exists
# OR create manually:
nano .env.local
```

Contents of `.env.local`:

```env
# ── Backend connection (server-side only — never sent to browser) ──
AXIS_AI_URL=http://localhost:8000
AXIS_AI_KEY=axai_YOUR_TENANT_API_KEY_HERE

# ── JWT (must match axis-ai .env JWT_SECRET) ──
JWT_SECRET=your_jwt_secret_here

# ── Public (visible to browser) ──
NEXT_PUBLIC_APP_URL=https://axis.edzlms.com

# ── Node environment ──
NODE_ENV=production
```

> **Where to get AXIS_AI_KEY:**
> ```bash
> # On the backend, create a tenant and get the API key:
> curl -X POST https://axisai.edzlms.com/api/v1/admin/tenants \
>   -H "X-Master-Key: YOUR_MASTER_KEY" \
>   -H "Content-Type: application/json" \
>   -d '{"name":"EDZLMS","moodle_url":"https://your.moodle.site"}'
> # Response includes "api_key" — copy it here
> ```

### 6. Install dependencies

```bash
npm ci
```

### 7. Build

```bash
NODE_ENV=production npm run build
```

### 8. Start with PM2

```bash
pm2 start pm2.config.js --env production
pm2 save                          # persist across reboots
pm2 startup                       # follow the printed sudo command
```

Verify it's running:
```bash
pm2 status
curl http://localhost:3000        # should return 200
```

---

## Nginx Configuration

### Add a new server block (or update the existing one)

```bash
sudo nano /etc/nginx/sites-available/axis-frontend
```

Paste:

```nginx
server {
    listen 80;
    server_name axis.edzlms.com;
    # Certbot will upgrade this to HTTPS automatically
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name axis.edzlms.com;

    # SSL — populated by Certbot
    # ssl_certificate     /etc/letsencrypt/live/axis.edzlms.com/fullchain.pem;
    # ssl_certificate_key /etc/letsencrypt/live/axis.edzlms.com/privkey.pem;
    # include /etc/letsencrypt/options-ssl-nginx.conf;
    # ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # Security headers (Next.js also sets these — belt and braces)
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Proxy everything to Next.js
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
        proxy_read_timeout 90s;
    }

    # Next.js static assets — serve with long cache
    location /_next/static/ {
        proxy_pass http://localhost:3000;
        proxy_cache_valid 200 365d;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }

    # Public folder assets
    location /public/ {
        proxy_pass http://localhost:3000;
        proxy_cache_valid 200 1d;
    }
}
```

Enable and test:

```bash
sudo ln -s /etc/nginx/sites-available/axis-frontend \
           /etc/nginx/sites-enabled/axis-frontend
sudo nginx -t
sudo systemctl reload nginx
```

### Issue SSL certificate (after DNS is pointing to the server)

```bash
sudo certbot --nginx -d axis.edzlms.com
```

---

## Subsequent Deploys (day-to-day)

Just run the deploy script:

```bash
cd /home/axisai/axisai-backend/axis-frontend
./frontdeploy.sh
```

The script:
1. `git stash && git pull origin main` — pulls latest code
2. `npm ci` — installs/updates dependencies
3. `npm run build` — production Next.js build
4. `pm2 reload axis-frontend --update-env` — zero-downtime restart
5. Health check — confirms app is responding

To deploy from a specific branch:

```bash
GIT_BRANCH=dev-video ./frontdeploy.sh
```

---

## Operational Commands

```bash
# View running status
pm2 status

# Live logs
pm2 logs axis-frontend

# Live CPU/memory monitor
pm2 monit

# Manual restart (hard)
pm2 restart axis-frontend

# Zero-downtime reload (preferred)
pm2 reload axis-frontend --update-env

# Stop
pm2 stop axis-frontend

# View build output
ls -la .next/

# Check which Node version is active
node -v

# Check Nginx is passing to Next.js
curl -I https://axis.edzlms.com
```

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `AXIS_AI_URL` | ✓ | FastAPI backend URL (e.g. `http://localhost:8000`) |
| `AXIS_AI_KEY` | ✓ | Tenant API key (`axai_...`) — server-side only |
| `JWT_SECRET` | ✓ | Must match `JWT_SECRET` in axis-ai `.env` |
| `NEXT_PUBLIC_APP_URL` | ✓ | Full public URL (e.g. `https://axis.edzlms.com`) |
| `NODE_ENV` | ✓ | Set to `production` on the server |

---

## Troubleshooting

### App starts but shows blank white page
- Check `.env.local` exists and has `AXIS_AI_URL` set
- Check `pm2 logs axis-frontend` for build errors
- Run `npm run build` manually and watch for TypeScript errors

### 502 Bad Gateway from Nginx
- Next.js is not running: `pm2 status`
- Start it: `pm2 start pm2.config.js --env production`
- Check port: `curl http://localhost:3000`

### Login returns "Network error"
- `AXIS_AI_URL` is wrong or FastAPI is not running
- Test: `curl http://localhost:8000/api/v1/health`

### PM2 process keeps crashing
- Check logs: `pm2 logs axis-frontend --lines 50`
- Common cause: `.env.local` missing or `AXIS_AI_KEY` incorrect
- Check build: `npm run type-check`

### CSS / fonts not loading
- Clear browser cache
- Check `/_next/static/` is accessible through Nginx
- Verify `NEXT_PUBLIC_APP_URL` matches the actual domain

### "Module not found" after git pull
- New package added: `npm ci && npm run build`
- Or run: `./frontdeploy.sh` (handles this automatically)

---

## Services on This Server

| Service | Command | Purpose |
|---|---|---|
| `axis-frontend` (PM2) | `pm2 reload axis-frontend` | Next.js frontend |
| `axis-ai` (systemd) | `sudo systemctl restart axis-ai` | FastAPI backend |
| `axis-ai-worker` (systemd) | `sudo systemctl restart axis-ai-worker` | Celery worker |
| `nginx` (systemd) | `sudo systemctl reload nginx` | Reverse proxy + SSL |

---

## Quick Health Check

```bash
# All in one go
pm2 status
curl -o /dev/null -s -w "Frontend: %{http_code}\n" http://localhost:3000
curl -o /dev/null -s -w "Backend:  %{http_code}\n" http://localhost:8000/api/v1/health
curl -o /dev/null -s -w "Public:   %{http_code}\n" https://axis.edzlms.com
```

Expected output:
```
┌─ axis-frontend │ online │ ...
Frontend: 200
Backend:  200
Public:   200
```
