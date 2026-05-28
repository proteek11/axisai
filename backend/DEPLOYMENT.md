# axis-ai + axis-frontend — Full Deployment Guide

Fresh-install guide for **Ubuntu 24.04 LTS**. Assumes nothing is deployed yet.
Covers the FastAPI backend (`axis-ai`) and the Next.js frontend (`axis-frontend`) on the same VPS.

---

## Table of Contents

1. [Server requirements](#1-server-requirements)
2. [Initial server setup](#2-initial-server-setup)
3. [Install system dependencies](#3-install-system-dependencies)
4. [PostgreSQL setup](#4-postgresql-setup)
5. [Redis setup](#5-redis-setup)
6. [Qdrant setup](#6-qdrant-setup)
7. [Clone the repository](#7-clone-the-repository)
8. [Python backend setup](#8-python-backend-setup)
9. [Configure environment variables](#9-configure-environment-variables)
10. [Run database migrations](#10-run-database-migrations)
11. [Seed default users](#11-seed-default-users)
12. [Create the Moodle tenant](#12-create-the-moodle-tenant)
13. [Systemd services — FastAPI](#13-systemd-services--fastapi)
14. [Node.js frontend setup](#14-nodejs-frontend-setup)
15. [Frontend environment variables](#15-frontend-environment-variables)
16. [Build and run the frontend](#16-build-and-run-the-frontend)
17. [Nginx configuration](#17-nginx-configuration)
18. [SSL with Let's Encrypt](#18-ssl-with-lets-encrypt)
19. [Verify everything is running](#19-verify-everything-is-running)
20. [Post-deploy checklist](#20-post-deploy-checklist)
21. [Useful operational commands](#21-useful-operational-commands)

---

## 1. Server requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| OS | Ubuntu 24.04 LTS | Ubuntu 24.04 LTS |
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Disk | 40 GB | 80 GB SSD |
| Ports open | 22, 80, 443 | 22, 80, 443 |

**Domain names needed** (both pointing to this server's IP before you start):
- `axisai.edzlms.com` — FastAPI backend
- `axis.edzlms.com` — Next.js frontend

---

## 2. Initial server setup

```bash
# Log in as root, create a non-root deploy user
adduser axisai
usermod -aG sudo axisai

# Switch to the deploy user for all remaining steps
su - axisai
```

---

## 3. Install system dependencies

```bash
sudo apt update && sudo apt upgrade -y

# Enable the universe repo (needed for some packages on 24.04)
sudo add-apt-repository universe -y
sudo apt update

# Core tools
sudo apt install -y \
  git curl wget unzip build-essential \
  python3 python3-pip python3-venv python3-dev \
  libpq-dev libssl-dev libffi-dev \
  ffmpeg poppler-utils \
  nginx certbot python3-certbot-nginx

# LibreOffice for PowerPoint to image conversion (snap only on 24.04)
sudo snap install libreoffice

# Confirm Python version (should be 3.12)
python3 --version
```

---

## 4. PostgreSQL setup

```bash
sudo apt install -y postgresql postgresql-contrib

# Start and enable
sudo systemctl enable --now postgresql
sudo systemctl status postgresql

# Create the database and user
sudo -u postgres psql << 'SQL'
CREATE USER axis WITH PASSWORD 'CHANGE_THIS_STRONG_PASSWORD';
CREATE DATABASE axis_ai OWNER axis;
GRANT ALL PRIVILEGES ON DATABASE axis_ai TO axis;
SQL
```

> Save the password — you will need it in `.env` in step 9.

---

## 5. Redis setup

```bash
sudo apt install -y redis-server

# Set a password in the Redis config
sudo sed -i 's/^# requirepass .*/requirepass CHANGE_THIS_REDIS_PASSWORD/' /etc/redis/redis.conf

# Ubuntu 24.04: the service is called redis-server (NOT redis)
sudo systemctl enable --now redis-server
sudo systemctl status redis-server

# Test the connection
redis-cli -a CHANGE_THIS_REDIS_PASSWORD ping
# Expected output: PONG
```

---

## 6. Qdrant setup

```bash
# Create directories
sudo mkdir -p /opt/qdrant/bin /opt/qdrant/storage /opt/qdrant/config
sudo chown -R axisai:axisai /opt/qdrant

# Download the Qdrant binary
cd /tmp
wget https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-unknown-linux-gnu.tar.gz
tar xzf qdrant-x86_64-unknown-linux-gnu.tar.gz
sudo mv qdrant /opt/qdrant/bin/qdrant
sudo chmod +x /opt/qdrant/bin/qdrant

# Create config with API key authentication
tee /opt/qdrant/config/config.yaml << 'YAML'
storage:
  storage_path: /opt/qdrant/storage

service:
  host: 127.0.0.1
  http_port: 6333
  grpc_port: 6334

security:
  api_key: CHANGE_THIS_QDRANT_API_KEY
YAML

# Create systemd service
sudo tee /etc/systemd/system/qdrant.service << 'UNIT'
[Unit]
Description=Qdrant Vector Database
After=network.target

[Service]
Type=simple
User=axisai
WorkingDirectory=/opt/qdrant
ExecStart=/opt/qdrant/bin/qdrant --config-path /opt/qdrant/config/config.yaml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now qdrant
sudo systemctl status qdrant

# Test (replace with the api_key you set above)
curl -H "api-key: CHANGE_THIS_QDRANT_API_KEY" http://localhost:6333/
```

---

## 7. Clone the repository

```bash
cd /home/axisai
git clone https://github.com/lmsofindia/axisai-backend axisai-backend
cd axisai-backend
git checkout dev-video
```

---

## 8. Python backend setup

```bash
cd /home/axisai/axisai-backend/axis-ai

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the package in editable mode
# IMPORTANT: use pip install -e . — there is NO requirements.txt
pip install -e .

# Verify the install
python -c "import app; print('Import OK')"
```

---

## 9. Configure environment variables

```bash
cd /home/axisai/axisai-backend/axis-ai

cp .env.example .env
chmod 600 .env
nano .env
```

Fill in these values (generate secrets with `python3 -c "import secrets; print(secrets.token_hex(32))"`):

```dotenv
# App
ENV=production
SECRET_KEY=<32-byte hex>
MASTER_API_KEY=<32-byte hex>

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=axis
POSTGRES_PASSWORD=<your postgres password>
POSTGRES_DB=axis_ai
DATABASE_URL=postgresql+asyncpg://axis:<password>@localhost:5432/axis_ai

# Redis
# IMPORTANT: the colon before the password is required
# Correct:   redis://:PASSWORD@localhost:6379/0
# Wrong:     redis://PASSWORD@localhost:6379/0
REDIS_PASSWORD=<your redis password>
REDIS_URL=redis://:<password>@localhost:6379/0
CELERY_BROKER_URL=redis://:<password>@localhost:6379/1
CELERY_RESULT_BACKEND=redis://:<password>@localhost:6379/2

# Qdrant — must match the api_key in /opt/qdrant/config/config.yaml exactly
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=<your qdrant api key>

# AI
OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...   (optional)

# JWT for axis.edzlms.com frontend users
JWT_SECRET_KEY=<32-byte hex>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
```

Save all passwords to `/home/axisai/CREDENTIALS.txt` and run `chmod 600 /home/axisai/CREDENTIALS.txt`.

---

## 10. Run database migrations

```bash
cd /home/axisai/axisai-backend/axis-ai
source .venv/bin/activate

# Apply all 11 migrations (001 through 011)
alembic upgrade head

# Confirm
alembic current
# Should print: 011 (head)
```

---

## 11. Seed default users

```bash
cd /home/axisai/axisai-backend/axis-ai
source .venv/bin/activate

python scripts/seed_users.py
```

Creates three accounts and writes generated passwords to `/home/axisai/AXIS_CREDENTIALS.txt`. Run once only.

```
admin@axis.edzlms.com   → role: admin
creator@axis.edzlms.com → role: creator
learner@axis.edzlms.com → role: learner
```

---

## 12. Create the Moodle tenant

The Moodle plugin authenticates with a tenant API key. You need to create the tenant before the plugin can connect.

```bash
# Start the API server temporarily
cd /home/axisai/axisai-backend/axis-ai
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
sleep 3

# Create tenant — replace YOUR_MASTER_KEY with MASTER_API_KEY from .env
curl -s -X POST http://127.0.0.1:8000/api/v1/admin/tenants \
  -H "X-Master-Key: YOUR_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "EDZLMS Production",
    "moodle_url": "https://your-moodle-site.com",
    "contact_email": "admin@edzlms.com"
  }' | python3 -m json.tool

# Save tenant_id and api_key from the response — the api_key is shown ONCE.

# Stop the temporary server
kill %1
```

---

## 13. Systemd services — FastAPI

```bash
# Get CPU core count for --workers / --concurrency
CORES=$(nproc)
echo "CPU cores: $CORES"

# API server
sudo tee /etc/systemd/system/axis-ai.service << UNIT
[Unit]
Description=axis-ai FastAPI server
After=network.target postgresql.service redis-server.service qdrant.service

[Service]
Type=simple
User=axisai
WorkingDirectory=/home/axisai/axisai-backend/axis-ai
EnvironmentFile=/home/axisai/axisai-backend/axis-ai/.env
ExecStart=/home/axisai/axisai-backend/axis-ai/.venv/bin/uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --workers $CORES \
  --loop uvloop \
  --access-log
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

# Celery worker
sudo tee /etc/systemd/system/axis-ai-worker.service << UNIT
[Unit]
Description=axis-ai Celery worker
After=network.target redis-server.service

[Service]
Type=simple
User=axisai
WorkingDirectory=/home/axisai/axisai-backend/axis-ai
EnvironmentFile=/home/axisai/axisai-backend/axis-ai/.env
ExecStart=/home/axisai/axisai-backend/axis-ai/.venv/bin/celery \
  -A app.tasks.celery_app worker \
  --loglevel=info \
  --concurrency=$CORES \
  -Q default,priority,video,beat
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

# Celery beat scheduler
sudo tee /etc/systemd/system/axis-ai-beat.service << UNIT
[Unit]
Description=axis-ai Celery beat scheduler
After=network.target redis-server.service

[Service]
Type=simple
User=axisai
WorkingDirectory=/home/axisai/axisai-backend/axis-ai
EnvironmentFile=/home/axisai/axisai-backend/axis-ai/.env
ExecStart=/home/axisai/axisai-backend/axis-ai/.venv/bin/celery \
  -A app.tasks.celery_app beat \
  --loglevel=info
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable axis-ai axis-ai-worker axis-ai-beat
sudo systemctl start axis-ai axis-ai-worker axis-ai-beat
sudo systemctl status axis-ai axis-ai-worker axis-ai-beat --no-pager

# Quick health check
curl http://127.0.0.1:8000/api/v1/health
```

---

## 14. Node.js frontend setup

```bash
# Install Node.js 20 LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

node --version   # v20.x.x
npm --version    # 10.x.x

# Install PM2 globally
sudo npm install -g pm2

# Install frontend dependencies
cd /home/axisai/axisai-backend/axis-frontend
npm install
```

---

## 15. Frontend environment variables

```bash
cd /home/axisai/axisai-backend/axis-frontend

tee .env.local << 'ENV'
# Internal URL of the FastAPI backend (never exposed to the browser)
AXIS_AI_URL=http://127.0.0.1:8000

# Tenant API key from step 12 (used for non-JWT admin calls)
AXIS_AI_KEY=axai_your_tenant_api_key_here

# Public URL of this frontend (used for CORS and og: meta tags)
NEXT_PUBLIC_APP_URL=https://axis.edzlms.com
ENV

chmod 600 .env.local
```

---

## 16. Build and run the frontend

```bash
cd /home/axisai/axisai-backend/axis-frontend

# Production build
npm run build

# Start with PM2
pm2 start npm --name "axis-frontend" -- start -- -p 3000

# Persist PM2 process list across reboots
pm2 save

# Configure PM2 to start on boot
pm2 startup
# Run the sudo command that PM2 prints

# Verify
pm2 status
curl http://127.0.0.1:3000
```

---

## 17. Nginx configuration

Write the HTTP-only config first. Certbot will add HTTPS automatically in the next step.

```bash
sudo tee /etc/nginx/sites-available/axisai << 'NGINX'
# FastAPI backend
server {
    listen 80;
    server_name axisai.edzlms.com;

    client_max_body_size 512M;

    location /api/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    # Swagger is disabled in ENV=production — deny everything else
    location / {
        return 404;
    }
}

# Next.js frontend
server {
    listen 80;
    server_name axis.edzlms.com;

    client_max_body_size 512M;

    location / {
        proxy_pass         http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade           $http_upgrade;
        proxy_set_header   Connection        "upgrade";
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/axisai /etc/nginx/sites-enabled/axisai
sudo rm -f /etc/nginx/sites-enabled/default

sudo nginx -t
sudo systemctl reload nginx
```

---

## 18. SSL with Let's Encrypt

Both domains must have DNS records pointing to this server before running Certbot.
Check with `dig axisai.edzlms.com` and `dig axis.edzlms.com`.

```bash
sudo certbot --nginx \
  -d axisai.edzlms.com \
  -d axis.edzlms.com \
  --non-interactive \
  --agree-tos \
  --email admin@edzlms.com

# Certbot automatically edits the Nginx config to add HTTPS and redirects.
# Test auto-renewal
sudo certbot renew --dry-run
```

Verify SSL is working:
```bash
curl -I https://axisai.edzlms.com/api/v1/health
curl -I https://axis.edzlms.com
```

---

## 19. Verify everything is running

```bash
# All 7 services must show "active"
for svc in postgresql redis-server qdrant nginx axis-ai axis-ai-worker axis-ai-beat; do
    printf "%-22s %s\n" "$svc:" "$(systemctl is-active $svc)"
done

# FastAPI health
curl -s https://axisai.edzlms.com/api/v1/health | python3 -m json.tool

# Frontend reachable
curl -sI https://axis.edzlms.com | head -5

# PM2 frontend process
pm2 status

# Celery workers registered
cd /home/axisai/axisai-backend/axis-ai && source .venv/bin/activate
celery -A app.tasks.celery_app inspect ping

# Qdrant collections (replace YOUR_KEY)
curl -s -H "api-key: YOUR_QDRANT_API_KEY" \
  http://localhost:6333/collections | python3 -m json.tool
```

---

## 20. Post-deploy checklist

- [ ] All 7 systemd services show `active (running)`
- [ ] `https://axisai.edzlms.com/api/v1/health` returns `{"status": "ok"}`
- [ ] `https://axis.edzlms.com` loads the login page
- [ ] Login works with credentials from `/home/axisai/AXIS_CREDENTIALS.txt`
- [ ] Admin dashboard displays stat cards
- [ ] Creator can upload a PDF and trigger an ingest job
- [ ] Learner can open a space and use the AI chat widget
- [ ] Token budgets are visible in the admin panel
- [ ] SSL certificate is valid (no browser warning)
- [ ] `.env` and `.env.local` are `chmod 600`
- [ ] `CREDENTIALS.txt` is `chmod 600`

---

## 21. Useful operational commands

### Update the backend

```bash
cd /home/axisai/axisai-backend
git stash && git pull origin dev-video

cd axis-ai
source .venv/bin/activate
pip install -e .
alembic upgrade head

sudo systemctl restart axis-ai axis-ai-worker axis-ai-beat
sudo systemctl status axis-ai --no-pager
```

### Update the frontend

```bash
cd /home/axisai/axisai-backend
git pull origin dev-video

cd axis-frontend
npm install
npm run build
pm2 restart axis-frontend
pm2 status
```

### View live logs

```bash
sudo journalctl -u axis-ai -f          # FastAPI
sudo journalctl -u axis-ai-worker -f   # Celery worker
sudo journalctl -u axis-ai-beat -f     # Celery beat
pm2 logs axis-frontend --lines 100     # Next.js
sudo tail -f /var/log/nginx/access.log # Nginx
```

### Restart everything

```bash
sudo systemctl restart axis-ai axis-ai-worker axis-ai-beat
pm2 restart axis-frontend
```

### Database backup

```bash
pg_dump -U axis axis_ai | gzip > /home/axisai/backup_$(date +%Y%m%d_%H%M).sql.gz
```

### Reset a user's password

```bash
cd /home/axisai/axisai-backend/axis-ai && source .venv/bin/activate
python3 - << 'PY'
import asyncio
from app.core.database import AsyncSessionFactory
from app.models.user import AxisUser
from passlib.context import CryptContext
from sqlalchemy import select

pwd_ctx = CryptContext(schemes=["bcrypt"])

async def reset():
    async with AsyncSessionFactory() as db:
        user = (await db.execute(
            select(AxisUser).where(AxisUser.email == "admin@axis.edzlms.com")
        )).scalar_one()
        user.hashed_password = pwd_ctx.hash("NewPassword123!")
        await db.commit()
        print(f"Password reset for {user.email}")

asyncio.run(reset())
PY
```

### Check disk usage

```bash
du -sh /opt/qdrant/storage/   # Vector DB storage
df -h /                        # Overall disk
```
