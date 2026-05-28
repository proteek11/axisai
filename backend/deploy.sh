#!/bin/bash
# =============================================================================
# axis-ai — Automated Deployment Script
# Run this as the "axisai" user on a fresh Ubuntu 22.04 server.
# It will do everything: install software, set up databases, deploy the app,
# configure Nginx, and issue an SSL certificate.
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh
# =============================================================================

set -euo pipefail   # exit immediately if any command fails

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'  # No Colour

# ── Helpers ───────────────────────────────────────────────────────────────────
info()    { echo -e "${CYAN}▶  $1${NC}"; }
success() { echo -e "${GREEN}✔  $1${NC}"; }
warn()    { echo -e "${YELLOW}⚠  $1${NC}"; }
error()   { echo -e "${RED}✖  $1${NC}"; exit 1; }
section() { echo -e "\n${BOLD}${BLUE}━━━  $1  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"; }
ask()     { echo -e "${YELLOW}?  $1${NC}"; }

# ── Verify running as non-root with sudo ──────────────────────────────────────
if [ "$EUID" -eq 0 ]; then
    error "Do NOT run this script as root. Run it as the 'axisai' user.
  First: adduser axisai && usermod -aG sudo axisai
  Then:  su - axisai && ./deploy.sh"
fi

if ! sudo -n true 2>/dev/null; then
    warn "This script needs sudo access. You may be prompted for your password."
fi

# =============================================================================
# STEP 0 — COLLECT ALL INPUTS UPFRONT
# We ask every question here so the script can run unattended after this.
# =============================================================================

echo -e "\n${BOLD}${BLUE}"
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║          axis-ai  Deployment Setup               ║"
echo "  ║   Answer these questions, then sit back.         ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo -e "${NC}"

echo ""
echo -e "${BOLD}── GitHub Repository ─────────────────────────────────────────${NC}"
ask "GitHub HTTPS URL of your repo  (e.g. https://github.com/yourname/moodle-axis-ai.git)"
read -r GITHUB_URL

ask "Branch to deploy  (press Enter for 'main')"
read -r GITHUB_BRANCH
GITHUB_BRANCH="${GITHUB_BRANCH:-main}"

ask "Is this a PRIVATE GitHub repo? (y/n)"
read -r REPO_PRIVATE
if [[ "$REPO_PRIVATE" =~ ^[Yy] ]]; then
    warn "For private repos you need a GitHub Personal Access Token."
    warn "Get one at: github.com → Settings → Developer settings → Personal access tokens → Tokens (classic)"
    warn "Select scope: repo (read access is enough)"
    ask "Paste your GitHub Personal Access Token:"
    read -rs GITHUB_TOKEN
    echo ""
else
    GITHUB_TOKEN=""
fi

ask "Subfolder inside the repo where pyproject.toml lives  (press Enter if it's in the root)"
read -r APP_SUBFOLDER
APP_SUBFOLDER="${APP_SUBFOLDER:-}"

echo ""
echo -e "${BOLD}── Domain ────────────────────────────────────────────────────${NC}"
warn "Your DNS A record must already point to this server's IP before the SSL step."
warn "Example: api.yourdomain.com → $(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP')"
ask "API subdomain  (e.g. api.yourdomain.com)"
read -r DOMAIN

echo ""
echo -e "${BOLD}── Email ─────────────────────────────────────────────────────${NC}"
ask "Your email address  (used for the SSL certificate)"
read -r ADMIN_EMAIL

echo ""
echo -e "${BOLD}── Moodle ────────────────────────────────────────────────────${NC}"
ask "Your Moodle site URL  (e.g. https://moodle.yourdomain.com)"
read -r MOODLE_URL

# ── Detect existing .env and reuse passwords if found ─────────────────────────
EXISTING_ENV=""
for CANDIDATE in \
    "/home/axisai/axisai-backend/axis-ai/.env" \
    "/home/axisai/axis-ai/.env" \
    "$HOME/axisai-backend/axis-ai/.env" \
    "$HOME/axis-ai/.env"; do
    if [ -f "$CANDIDATE" ]; then
        EXISTING_ENV="$CANDIDATE"
        break
    fi
done

if [ -n "$EXISTING_ENV" ]; then
    echo ""
    echo -e "${GREEN}✔  Found existing .env at: $EXISTING_ENV${NC}"
    echo -e "${YELLOW}   Reusing existing passwords — no need to enter them again.${NC}"
    DB_PASSWORD=$(grep    "^POSTGRES_PASSWORD=" "$EXISTING_ENV" | cut -d= -f2-)
    REDIS_PASSWORD=$(grep "^REDIS_PASSWORD="    "$EXISTING_ENV" | cut -d= -f2-)
    QDRANT_API_KEY=$(grep "^QDRANT_API_KEY="    "$EXISTING_ENV" | cut -d= -f2-)
    OPENAI_KEY=$(grep     "^OPENAI_API_KEY="    "$EXISTING_ENV" | cut -d= -f2-)
    ANTHROPIC_KEY=$(grep  "^ANTHROPIC_API_KEY=" "$EXISTING_ENV" | cut -d= -f2-)
    SECRET_KEY=$(grep     "^SECRET_KEY="        "$EXISTING_ENV" | cut -d= -f2-)
    MASTER_API_KEY=$(grep "^MASTER_API_KEY="    "$EXISTING_ENV" | cut -d= -f2-)
    echo -e "${GREEN}   Passwords loaded from existing .env ✔${NC}"
else
    echo ""
    echo -e "${BOLD}── Passwords — Press Enter to auto-generate strong passwords ─${NC}"

    ask "PostgreSQL password  (or press Enter to generate)"
    read -rs DB_PASSWORD_INPUT
    echo ""
    DB_PASSWORD="${DB_PASSWORD_INPUT:-$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)}"

    ask "Redis password  (or press Enter to generate)"
    read -rs REDIS_PASSWORD_INPUT
    echo ""
    REDIS_PASSWORD="${REDIS_PASSWORD_INPUT:-$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)}"

    ask "Qdrant API key  (or press Enter to generate)"
    read -rs QDRANT_KEY_INPUT
    echo ""
    QDRANT_API_KEY="${QDRANT_KEY_INPUT:-$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)}"

    echo ""
    echo -e "${BOLD}── AI API Keys ───────────────────────────────────────────────${NC}"
    ask "OpenAI API key  (from platform.openai.com — required)"
    read -rs OPENAI_KEY
    echo ""

    ask "Anthropic API key  (optional — press Enter to skip)"
    read -rs ANTHROPIC_KEY
    echo ""

    # Generate app secrets automatically
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
    MASTER_API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -base64 32 | tr -d '/+=')
fi

# ── Confirm before proceeding ──────────────────────────────────────────────
echo ""
echo -e "${BOLD}${BLUE}── Summary — Please Confirm ──────────────────────────────────${NC}"
echo -e "  GitHub URL     : ${CYAN}$GITHUB_URL${NC}"
echo -e "  Branch         : ${CYAN}$GITHUB_BRANCH${NC}"
echo -e "  App subfolder  : ${CYAN}${APP_SUBFOLDER:-'(repo root)'}${NC}"
echo -e "  Domain         : ${CYAN}$DOMAIN${NC}"
echo -e "  Email          : ${CYAN}$ADMIN_EMAIL${NC}"
echo -e "  Moodle URL     : ${CYAN}$MOODLE_URL${NC}"
echo -e "  DB password    : ${CYAN}(set)${NC}"
echo -e "  Redis password : ${CYAN}(set)${NC}"
echo -e "  Qdrant key     : ${CYAN}(set)${NC}"
echo -e "  OpenAI key     : ${CYAN}${OPENAI_KEY:0:8}...${NC}"
echo ""
ask "Everything look correct? Type 'yes' to start deployment:"
read -r CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
    error "Deployment cancelled. Run the script again to restart."
fi

# ── Derive paths ──────────────────────────────────────────────────────────────
REPO_NAME=$(basename "$GITHUB_URL" .git)
REPO_DIR="/home/axisai/$REPO_NAME"
if [ -n "$APP_SUBFOLDER" ]; then
    APP_DIR="$REPO_DIR/$APP_SUBFOLDER"
else
    APP_DIR="$REPO_DIR"
fi

echo ""
echo -e "${BOLD}${GREEN}Starting deployment...${NC}"
echo ""

# =============================================================================
# SECTION 3 — SYSTEM DEPENDENCIES
# =============================================================================
section "3/7  Installing System Packages"

info "Enabling Ubuntu universe repository (required for LibreOffice)..."
sudo add-apt-repository universe -y -q 2>/dev/null || true

info "Updating package lists..."
sudo apt-get update -qq

info "Installing core tools..."
sudo apt-get install -y -qq \
    curl wget git unzip build-essential \
    software-properties-common \
    ca-certificates gnupg lsb-release \
    nginx certbot python3-certbot-nginx \
    libpq-dev nano

info "Installing media tools (ffmpeg, fonts)..."
sudo apt-get install -y -qq \
    ffmpeg \
    fonts-liberation \
    fonts-noto \
    fonts-open-sans
success "ffmpeg and fonts installed"

info "Installing LibreOffice (needed only for PowerPoint-to-video feature)..."
if sudo apt-get install -y -qq libreoffice-headless 2>/dev/null; then
    success "LibreOffice installed"
else
    warn "LibreOffice not found via apt — trying snap..."
    if sudo snap install libreoffice 2>/dev/null; then
        success "LibreOffice installed via snap"
    else
        warn "LibreOffice skipped — install it later with: sudo snap install libreoffice"
        warn "Only affects PowerPoint-to-video conversion. Everything else works fine."
    fi
fi

info "Detecting Python version..."
if command -v python3.12 &>/dev/null; then
    PYTHON_BIN=python3.12
    info "Found Python 3.12 (Ubuntu 24.04) — using it"
elif command -v python3.11 &>/dev/null; then
    PYTHON_BIN=python3.11
    info "Found Python 3.11 — using it"
else
    info "Python 3.11/3.12 not found — installing via deadsnakes PPA..."
    sudo add-apt-repository ppa:deadsnakes/ppa -y -q 2>/dev/null || true
    sudo apt-get update -qq
    if sudo apt-get install -y -qq python3.11 2>/dev/null; then
        PYTHON_BIN=python3.11
    else
        sudo apt-get install -y -qq python3.12
        PYTHON_BIN=python3.12
    fi
fi

# Ensure venv + dev headers are installed for whichever Python we're using
sudo apt-get install -y -qq "${PYTHON_BIN}-venv" "${PYTHON_BIN}-dev" 2>/dev/null || true

PYTHON_VER=$(${PYTHON_BIN} --version)
success "Python ready: $PYTHON_VER"

info "Ensuring pip is available..."
sudo apt-get install -y -qq python3-pip 2>/dev/null || true
success "pip ready (venv will manage its own pip)"

# PostgreSQL 15
info "Installing PostgreSQL 15..."
if ! command -v psql &>/dev/null; then
    sudo sh -c "echo \"deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main\" > /etc/apt/sources.list.d/pgdg.list"
    wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add - 2>/dev/null
    sudo apt-get update -qq
    sudo apt-get install -y -qq postgresql-15 postgresql-client-15
else
    warn "PostgreSQL already installed — skipping"
fi
sudo systemctl start postgresql
sudo systemctl enable postgresql
success "PostgreSQL 15 ready"

# Redis 7
info "Installing Redis 7..."
if ! command -v redis-cli &>/dev/null; then
    curl -fsSL https://packages.redis.io/gpg \
        | sudo gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg 2>/dev/null
    echo "deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] \
        https://packages.redis.io/deb $(lsb_release -cs) main" \
        | sudo tee /etc/apt/sources.list.d/redis.list > /dev/null
    sudo apt-get update -qq
    sudo apt-get install -y -qq redis
else
    warn "Redis already installed — skipping"
fi

# Detect Redis service name (redis-server on Ubuntu 24.04, redis on 22.04)
# Check for the actual unit file — not the alias — to avoid "linked unit" errors
if [ -f /lib/systemd/system/redis-server.service ] || [ -f /usr/lib/systemd/system/redis-server.service ]; then
    REDIS_SVC=redis-server
else
    REDIS_SVC=redis
fi
info "Redis service name: $REDIS_SVC"

# Configure Redis password
info "Configuring Redis password..."
sudo sed -i "s/^# requirepass foobared/requirepass $REDIS_PASSWORD/" /etc/redis/redis.conf
sudo sed -i "s/^requirepass .*/requirepass $REDIS_PASSWORD/" /etc/redis/redis.conf
# Ensure Redis is bound to localhost
sudo sed -i "s/^# bind 127.0.0.1/bind 127.0.0.1/" /etc/redis/redis.conf
sudo systemctl restart "$REDIS_SVC"
sudo systemctl enable "$REDIS_SVC"

# Verify Redis
if redis-cli -a "$REDIS_PASSWORD" ping 2>/dev/null | grep -q PONG; then
    success "Redis ready with password"
else
    error "Redis failed to start. Check: sudo journalctl -u $REDIS_SVC -n 20"
fi

# Qdrant
info "Installing Qdrant..."
sudo mkdir -p /opt/qdrant/{bin,storage,config}
sudo chown -R axisai:axisai /opt/qdrant

if [ ! -f /opt/qdrant/bin/qdrant ]; then
    info "Downloading Qdrant binary..."
    wget -q -O /tmp/qdrant.tar.gz \
        https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-unknown-linux-musl.tar.gz
    tar -xzf /tmp/qdrant.tar.gz -C /tmp
    sudo mv /tmp/qdrant /opt/qdrant/bin/qdrant
    sudo chmod +x /opt/qdrant/bin/qdrant
    rm -f /tmp/qdrant.tar.gz
else
    warn "Qdrant binary already present — skipping download"
fi

# Qdrant config
cat > /opt/qdrant/config/config.yaml << QDRANT_EOF
storage:
  storage_path: /opt/qdrant/storage

service:
  host: 127.0.0.1
  http_port: 6333
  grpc_port: 6334
  enable_cors: false

security:
  api_key: ${QDRANT_API_KEY}

log_level: INFO
QDRANT_EOF

# Qdrant systemd service
sudo tee /etc/systemd/system/qdrant.service > /dev/null << 'SYSTEMD_EOF'
[Unit]
Description=Qdrant Vector Database
After=network.target

[Service]
Type=simple
User=axisai
ExecStart=/opt/qdrant/bin/qdrant --config-path /opt/qdrant/config/config.yaml
Restart=on-failure
RestartSec=5
WorkingDirectory=/opt/qdrant

[Install]
WantedBy=multi-user.target
SYSTEMD_EOF

sudo systemctl daemon-reload
sudo systemctl enable qdrant
sudo systemctl restart qdrant
sleep 3

if curl -sf -H "api-key: $QDRANT_API_KEY" http://127.0.0.1:6333/healthz > /dev/null; then
    success "Qdrant running"
else
    error "Qdrant failed to start. Check: sudo journalctl -u qdrant -n 20"
fi

# =============================================================================
# SECTION 4 — DATABASE
# =============================================================================
section "4/7  Setting Up Database"

info "Creating PostgreSQL user and database..."
# Use || true so it doesn't fail if they already exist
sudo -u postgres psql -c "CREATE USER axis WITH PASSWORD '$DB_PASSWORD';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE axis_ai OWNER axis;" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE axis_ai TO axis;" 2>/dev/null || true

# Verify connection
if PGPASSWORD="$DB_PASSWORD" psql -U axis -h localhost -d axis_ai -c "SELECT 1;" > /dev/null 2>&1; then
    success "PostgreSQL database 'axis_ai' ready"
else
    error "Cannot connect to database. Check password and try again."
fi

# Create upload directories
info "Creating application directories..."
sudo mkdir -p /tmp/axis_uploads
sudo mkdir -p /data/video_outputs
sudo chown -R axisai:axisai /tmp/axis_uploads /data/video_outputs
success "Directories created"

# =============================================================================
# SECTION 5 — APPLICATION CODE
# =============================================================================
section "5/7  Deploying Application Code"

# Clone repo
info "Cloning repository from GitHub..."
if [ -d "$REPO_DIR" ]; then
    warn "Directory $REPO_DIR already exists — pulling latest code instead"
    cd "$REPO_DIR"
    git pull origin "$GITHUB_BRANCH"
else
    if [ -n "$GITHUB_TOKEN" ]; then
        # Embed token in URL for private repos
        CLONE_URL=$(echo "$GITHUB_URL" | sed "s|https://|https://${GITHUB_TOKEN}@|")
    else
        CLONE_URL="$GITHUB_URL"
    fi
    git clone --branch "$GITHUB_BRANCH" "$CLONE_URL" "$REPO_DIR"
fi
success "Repository cloned to $REPO_DIR"

# Navigate to app directory and verify
if [ -n "$APP_SUBFOLDER" ]; then
    info "Navigating to app subfolder: $APP_SUBFOLDER"
fi

if [ ! -f "$APP_DIR/pyproject.toml" ]; then
    # Try to auto-detect
    FOUND=$(find "$REPO_DIR" -name "pyproject.toml" -not -path "*/.*" 2>/dev/null | head -1)
    if [ -n "$FOUND" ]; then
        APP_DIR=$(dirname "$FOUND")
        warn "pyproject.toml found at: $APP_DIR"
    else
        error "Cannot find pyproject.toml in $APP_DIR. Check the APP_SUBFOLDER value."
    fi
fi

cd "$APP_DIR"
success "App directory: $APP_DIR"

# Create virtual environment
info "Creating Python virtual environment..."
if [ ! -d ".venv" ]; then
    ${PYTHON_BIN} -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip -q
success "Virtual environment ready"

# Install dependencies
info "Installing Python packages (this takes 3-5 minutes)..."
pip install -e . -q
success "Python packages installed"

# Optional: Whisper
info "Installing Whisper for audio transcription..."
pip install -e ".[whisper]" -q 2>/dev/null && success "Whisper installed" || warn "Whisper install skipped (optional)"

# Create .env file
info "Creating .env configuration file..."
cat > "$APP_DIR/.env" << ENV_EOF
# ── App ──────────────────────────────────────────────────────────────────────
ENV=production
APP_NAME=axis-ai
APP_VERSION=0.1.0
DEBUG=false
SECRET_KEY=${SECRET_KEY}
MASTER_API_KEY=${MASTER_API_KEY}

# ── PostgreSQL ────────────────────────────────────────────────────────────────
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=axis
POSTGRES_PASSWORD=${DB_PASSWORD}
POSTGRES_DB=axis_ai
DATABASE_URL=postgresql+asyncpg://axis:${DB_PASSWORD}@localhost:5432/axis_ai

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=${REDIS_PASSWORD}
REDIS_DB=0
REDIS_URL=redis://:${REDIS_PASSWORD}@localhost:6379/0

# ── Celery ───────────────────────────────────────────────────────────────────
CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@localhost:6379/1
CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@localhost:6379/2

# ── Qdrant ───────────────────────────────────────────────────────────────────
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=${QDRANT_API_KEY}
QDRANT_GRPC_PORT=6334
QDRANT_USE_GRPC=false
QDRANT_COLLECTION_CONTENT_CHUNKS=axis_content_chunks
QDRANT_COLLECTION_KB_CHUNKS=axis_kb_chunks
QDRANT_COLLECTION_CONTENT_INTELLIGENCE=axis_content_intelligence
QDRANT_COLLECTION_QUESTION_INTELLIGENCE=axis_question_intelligence
QDRANT_VECTOR_SIZE=1536

# ── AI Providers ─────────────────────────────────────────────────────────────
OPENAI_API_KEY=${OPENAI_KEY}
ANTHROPIC_API_KEY=${ANTHROPIC_KEY}
DEFAULT_AI_PROVIDER=openai
DEFAULT_EMBEDDING_MODEL=text-embedding-3-small
DEFAULT_CHAT_MODEL=gpt-4o-mini
MODEL_SUMMARY=gpt-4o-mini
MODEL_QUIZ=gpt-4o
MODEL_FLASHCARDS=gpt-4o-mini
MODEL_GLOSSARY=gpt-4o-mini
MODEL_MINDMAP=gpt-4o-mini
MODEL_OBJECTIVES=gpt-4o-mini
MODEL_BLOOMS=gpt-4o-mini
MODEL_TRANSLATION=gpt-4o-mini

# ── Chunking ─────────────────────────────────────────────────────────────────
DEFAULT_CHUNK_SIZE=1000
DEFAULT_CHUNK_OVERLAP=200
DEFAULT_CHUNKING_STRATEGY=recursive

# ── Rate limiting ─────────────────────────────────────────────────────────────
RATE_LIMIT_GLOBAL_TOKENS_HOUR=500000
RATE_LIMIT_GLOBAL_TOKENS_DAY=5000000
RATE_LIMIT_GLOBAL_TOKENS_MONTH=50000000
RATE_LIMIT_PER_COURSE_TOKENS_DAY=50000
RATE_LIMIT_PER_USER_TOKENS_DAY=10000

# ── File handling ─────────────────────────────────────────────────────────────
UPLOAD_DIR=/tmp/axis_uploads
MAX_FILE_SIZE_MB=100

# ── Video ─────────────────────────────────────────────────────────────────────
VIMEO_ACCESS_TOKEN=
YOUTUBE_API_KEY=
PEERTUBE_DEFAULT_INSTANCE=
WHISPER_MODEL=base
WHISPER_FALLBACK_ENABLED=true

# ── Observability ─────────────────────────────────────────────────────────────
LOG_LEVEL=INFO
LOG_FORMAT=json
PROMETHEUS_ENABLED=true

# ── CORS ──────────────────────────────────────────────────────────────────────
CORS_ORIGINS=${MOODLE_URL},https://${DOMAIN}
ENV_EOF

chmod 600 "$APP_DIR/.env"
success ".env file created and secured (chmod 600)"

# Run DB migrations
info "Running database migrations..."
cd "$APP_DIR"
source .venv/bin/activate
alembic upgrade head
success "All migrations applied"

# =============================================================================
# SECTION 6 — SYSTEMD SERVICES
# =============================================================================
section "6/7  Creating System Services"

NUM_CPUS=$(nproc)
API_WORKERS=$NUM_CPUS
CELERY_CONCURRENCY=$NUM_CPUS

info "Detected $NUM_CPUS CPU cores → API workers: $API_WORKERS, Celery concurrency: $CELERY_CONCURRENCY"

# ── axis-ai API service ──────────────────────────────────────────────────────
sudo tee /etc/systemd/system/axis-ai.service > /dev/null << SVCEOF
[Unit]
Description=axis-ai FastAPI API Server
After=network.target postgresql.service ${REDIS_SVC}.service qdrant.service
Requires=postgresql.service ${REDIS_SVC}.service

[Service]
Type=simple
User=axisai
Group=axisai
WorkingDirectory=${APP_DIR}
Environment="PATH=${APP_DIR}/.venv/bin"
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/uvicorn app.main:app \\
    --host 0.0.0.0 \\
    --port 8000 \\
    --workers ${API_WORKERS} \\
    --loop uvloop \\
    --log-level warning \\
    --no-access-log
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=axis-ai
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
SVCEOF
success "axis-ai.service created"

# ── Celery worker service ─────────────────────────────────────────────────────
sudo tee /etc/systemd/system/axis-ai-worker.service > /dev/null << SVCEOF
[Unit]
Description=axis-ai Celery Worker (background tasks)
After=network.target postgresql.service ${REDIS_SVC}.service qdrant.service
Requires=postgresql.service ${REDIS_SVC}.service

[Service]
Type=simple
User=axisai
Group=axisai
WorkingDirectory=${APP_DIR}
Environment="PATH=${APP_DIR}/.venv/bin"
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/celery \\
    -A app.tasks.celery_app worker \\
    --loglevel=info \\
    --concurrency=${CELERY_CONCURRENCY} \\
    -Q default,priority,video,beat
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=axis-ai-worker

[Install]
WantedBy=multi-user.target
SVCEOF
success "axis-ai-worker.service created"

# ── Celery beat service ───────────────────────────────────────────────────────
sudo tee /etc/systemd/system/axis-ai-beat.service > /dev/null << SVCEOF
[Unit]
Description=axis-ai Celery Beat Scheduler
After=network.target ${REDIS_SVC}.service axis-ai-worker.service
Requires=${REDIS_SVC}.service

[Service]
Type=simple
User=axisai
Group=axisai
WorkingDirectory=${APP_DIR}
Environment="PATH=${APP_DIR}/.venv/bin"
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/celery \\
    -A app.tasks.celery_app beat \\
    --loglevel=info
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=axis-ai-beat

[Install]
WantedBy=multi-user.target
SVCEOF
success "axis-ai-beat.service created"

# Reload and start all services
info "Starting all services..."
sudo systemctl daemon-reload
sudo systemctl enable axis-ai axis-ai-worker axis-ai-beat
sudo systemctl start axis-ai axis-ai-worker axis-ai-beat
sleep 5  # give them time to come up

# Verify
ALL_SERVICES_OK=true
for SVC in axis-ai axis-ai-worker axis-ai-beat; do
    STATUS=$(systemctl is-active "$SVC" 2>/dev/null)
    if [ "$STATUS" = "active" ]; then
        success "$SVC: active"
    else
        warn "$SVC: $STATUS"
        ALL_SERVICES_OK=false
    fi
done

if [ "$ALL_SERVICES_OK" = false ]; then
    warn "One or more services didn't start. Check logs:"
    warn "  sudo journalctl -u axis-ai -n 30 --no-pager"
    warn "  sudo journalctl -u axis-ai-worker -n 30 --no-pager"
fi

# Local health check
sleep 3
if curl -sf http://localhost:8000/api/v1/health > /dev/null; then
    success "API responding on localhost:8000"
else
    warn "API not yet responding — may still be starting. Check: sudo journalctl -u axis-ai -n 20"
fi

# =============================================================================
# SECTION 7 — NGINX VHOST + SSL
# =============================================================================
section "7/7  Nginx Virtual Host + SSL Certificate"

# ── Create Nginx vhost ────────────────────────────────────────────────────────
info "Creating Nginx virtual host for $DOMAIN..."

# Write HTTP-only config first — Certbot will add the SSL block itself
sudo tee /etc/nginx/sites-available/axis-ai > /dev/null << NGINXEOF
# Rate limit: 30 requests/minute per IP with burst of 20
limit_req_zone \$binary_remote_addr zone=axis_api:10m rate=30r/m;

server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    # Let's Encrypt certificate renewal challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Allow large uploads (PDFs, SCORM packages, videos)
    client_max_body_size 200M;

    # Generous timeouts for AI calls
    proxy_connect_timeout  60s;
    proxy_send_timeout    300s;
    proxy_read_timeout    300s;

    # ── API routes ─────────────────────────────────────────────────────────────
    location /api/ {
        limit_req zone=axis_api burst=20 nodelay;

        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade           \$http_upgrade;
        proxy_set_header   Connection        "upgrade";
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
    }

    # ── Health check (no rate limit) ───────────────────────────────────────────
    location = /api/v1/health {
        proxy_pass       http://127.0.0.1:8000;
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # ── Block everything else ──────────────────────────────────────────────────
    location / {
        return 404;
    }
}
NGINXEOF

success "Nginx vhost created for $DOMAIN"

# Enable site, disable default
sudo ln -sf /etc/nginx/sites-available/axis-ai /etc/nginx/sites-enabled/axis-ai
sudo rm -f /etc/nginx/sites-enabled/default

# Test Nginx config
if sudo nginx -t 2>/dev/null; then
    success "Nginx configuration is valid"
else
    error "Nginx config has errors. Run: sudo nginx -t"
fi

# Create certbot webroot directory
sudo mkdir -p /var/www/certbot

# Start Nginx (HTTP only for now — needed for SSL challenge)
sudo systemctl enable nginx
sudo systemctl restart nginx
success "Nginx started"

# ── Issue SSL Certificate ─────────────────────────────────────────────────────
info "Checking DNS before requesting SSL certificate..."

# Check if DNS is pointing to this server
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
DNS_IP=$(dig +short "$DOMAIN" 2>/dev/null | tail -1 || host "$DOMAIN" 2>/dev/null | grep -oP '\d+\.\d+\.\d+\.\d+' | head -1)

if [ -z "$DNS_IP" ]; then
    warn "Could not resolve $DOMAIN. DNS may not have propagated yet."
    warn "Your server IP is: $SERVER_IP"
    warn "Make sure your A record points $DOMAIN → $SERVER_IP"
    echo ""
    ask "Has the DNS A record been set? Press Enter to attempt SSL anyway, or Ctrl+C to exit and fix DNS first."
    read -r
elif [ "$DNS_IP" != "$SERVER_IP" ]; then
    warn "DNS mismatch: $DOMAIN resolves to $DNS_IP but this server is $SERVER_IP"
    warn "SSL certificate will fail until DNS propagates."
    ask "Press Enter to attempt SSL anyway (it will fail gracefully), or Ctrl+C to wait for DNS."
    read -r
else
    success "DNS verified: $DOMAIN → $SERVER_IP ✔"
fi

info "Requesting SSL certificate from Let's Encrypt..."
if sudo certbot --nginx \
    -d "$DOMAIN" \
    --non-interactive \
    --agree-tos \
    --email "$ADMIN_EMAIL" \
    --redirect 2>&1; then
    success "SSL certificate issued for $DOMAIN"
else
    warn "SSL certificate failed. Common reasons:"
    warn "  1. DNS not yet propagated (wait 5-15 min, then run: sudo certbot --nginx -d $DOMAIN --email $ADMIN_EMAIL --redirect)"
    warn "  2. Port 80 is blocked (check: sudo ufw status)"
    warn "  3. Nginx is not running (check: sudo systemctl status nginx)"
    warn ""
    warn "The app is still running — just without HTTPS for now."
    warn "After fixing DNS, run this to get SSL:"
    warn "  sudo certbot --nginx -d $DOMAIN --email $ADMIN_EMAIL --redirect"
fi

# Final Nginx restart
sudo systemctl restart nginx

# =============================================================================
# FINAL CHECKS
# =============================================================================
section "✔  Final Verification"

info "Checking all services..."
echo ""
ALL_OK=true
for SVC in postgresql "$REDIS_SVC" qdrant nginx axis-ai axis-ai-worker axis-ai-beat; do
    STATUS=$(systemctl is-active "$SVC" 2>/dev/null)
    if [ "$STATUS" = "active" ]; then
        echo -e "  ${GREEN}✔${NC}  $SVC"
    else
        echo -e "  ${RED}✖${NC}  $SVC  (status: $STATUS)"
        ALL_OK=false
    fi
done

echo ""
info "Testing API health endpoint..."
sleep 2
HEALTH_RESPONSE=$(curl -sf "https://$DOMAIN/api/v1/health" 2>/dev/null \
    || curl -sf "http://localhost:8000/api/v1/health" 2>/dev/null \
    || echo "not responding yet")
echo -e "  Health response: ${CYAN}$HEALTH_RESPONSE${NC}"

# =============================================================================
# BACKUP SETUP
# =============================================================================
section "Setting Up Automatic Backups"

mkdir -p /home/axisai/backups

cat > /home/axisai/backup.sh << BACKUPEOF
#!/bin/bash
DATE=\$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/home/axisai/backups
echo "Starting backup: \$DATE"
PGPASSWORD="${DB_PASSWORD}" pg_dump -U axis -h localhost axis_ai | gzip > \$BACKUP_DIR/postgres_\$DATE.sql.gz
sudo systemctl stop qdrant
tar -czf \$BACKUP_DIR/qdrant_\$DATE.tar.gz /opt/qdrant/storage
sudo systemctl start qdrant
cp ${APP_DIR}/.env \$BACKUP_DIR/env_\$DATE.bak
find \$BACKUP_DIR -name "*.gz" -mtime +7 -delete
find \$BACKUP_DIR -name "*.bak" -mtime +7 -delete
echo "Backup complete: \$DATE"
ls -lh \$BACKUP_DIR/
BACKUPEOF

chmod +x /home/axisai/backup.sh

# Add cron job (2 AM daily)
(crontab -l 2>/dev/null | grep -v backup.sh; echo "0 2 * * * /home/axisai/backup.sh >> /home/axisai/backups/backup.log 2>&1") | crontab -
success "Daily backup scheduled for 2 AM"

# =============================================================================
# PRINT SUMMARY
# =============================================================================

echo ""
echo -e "${BOLD}${GREEN}"
echo "  ╔══════════════════════════════════════════════════════════════════╗"
echo "  ║                   DEPLOYMENT COMPLETE!                          ║"
echo "  ╚══════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "${BOLD}── Your Credentials (SAVE THESE NOW) ────────────────────────────────${NC}"
echo ""
echo -e "  API URL           : ${CYAN}https://$DOMAIN${NC}"
echo -e "  Health check      : ${CYAN}https://$DOMAIN/api/v1/health${NC}"
echo ""
echo -e "  App directory     : ${CYAN}$APP_DIR${NC}"
echo ""
echo -e "  PostgreSQL DB     : ${CYAN}axis_ai${NC}"
echo -e "  PostgreSQL user   : ${CYAN}axis${NC}"
echo -e "  PostgreSQL pass   : ${CYAN}$DB_PASSWORD${NC}"
echo ""
echo -e "  Redis password    : ${CYAN}$REDIS_PASSWORD${NC}"
echo ""
echo -e "  Qdrant API key    : ${CYAN}$QDRANT_API_KEY${NC}"
echo ""
echo -e "  MASTER_API_KEY    : ${CYAN}$MASTER_API_KEY${NC}"
echo -e "  ${YELLOW}(use this to create tenants — keep it secret)${NC}"
echo ""
echo -e "  SECRET_KEY        : ${CYAN}$SECRET_KEY${NC}"
echo ""

echo -e "${BOLD}── Next Step: Create Your Tenant & API Key ──────────────────────────${NC}"
echo ""
echo -e "  ${YELLOW}Run this to create your school tenant:${NC}"
echo ""
echo -e "  ${CYAN}curl -s -X POST https://$DOMAIN/api/v1/tenants \\"
echo -e "    -H \"Content-Type: application/json\" \\"
echo -e "    -H \"X-Master-Key: $MASTER_API_KEY\" \\"
echo -e "    -d '{\"name\": \"My School\", \"slug\": \"my-school\"}' | python3 -m json.tool${NC}"
echo ""
echo -e "  ${YELLOW}Copy the 'id' from the response, then run:${NC}"
echo ""
echo -e "  ${CYAN}curl -s -X POST https://$DOMAIN/api/v1/tenants/PASTE_ID_HERE/keys \\"
echo -e "    -H \"Content-Type: application/json\" \\"
echo -e "    -H \"X-Master-Key: $MASTER_API_KEY\" \\"
echo -e "    -d '{\"name\": \"Moodle Key\"}' | python3 -m json.tool${NC}"
echo ""
echo -e "  ${YELLOW}Copy the 'key' (axai_...) into your Moodle plugin settings.${NC}"
echo ""

echo -e "${BOLD}── Useful Commands ──────────────────────────────────────────────────${NC}"
echo ""
echo -e "  View API logs   :  ${CYAN}sudo journalctl -u axis-ai -f${NC}"
echo -e "  View worker logs:  ${CYAN}sudo journalctl -u axis-ai-worker -f${NC}"
echo -e "  Restart all     :  ${CYAN}sudo systemctl restart axis-ai axis-ai-worker axis-ai-beat${NC}"
echo -e "  Check health    :  ${CYAN}curl https://$DOMAIN/api/v1/health${NC}"
echo -e "  Run backup      :  ${CYAN}/home/axisai/backup.sh${NC}"
echo ""
echo -e "  ${BOLD}Update the app (after pushing new code to GitHub):${NC}"
echo -e "  ${CYAN}cd $APP_DIR && source .venv/bin/activate && git pull && pip install -e . && alembic upgrade head && sudo systemctl restart axis-ai axis-ai-worker axis-ai-beat${NC}"
echo ""

if [ "$ALL_OK" = true ]; then
    echo -e "${BOLD}${GREEN}  All 7 services are running. Your API is live! ✔${NC}"
else
    echo -e "${BOLD}${YELLOW}  Some services need attention — check the warnings above.${NC}"
fi

echo ""

# Save credentials to a file for reference
CREDS_FILE="/home/axisai/CREDENTIALS.txt"
cat > "$CREDS_FILE" << CREDSEOF
axis-ai Deployment Credentials
Generated: $(date)
=====================================
API URL          : https://$DOMAIN
App directory    : $APP_DIR

PostgreSQL DB    : axis_ai
PostgreSQL user  : axis
PostgreSQL pass  : $DB_PASSWORD

Redis password   : $REDIS_PASSWORD
Qdrant API key   : $QDRANT_API_KEY

MASTER_API_KEY   : $MASTER_API_KEY
SECRET_KEY       : $SECRET_KEY

Moodle URL       : $MOODLE_URL

To update: cd $APP_DIR && source .venv/bin/activate && git pull && pip install -e . && alembic upgrade head && sudo systemctl restart axis-ai axis-ai-worker axis-ai-beat
CREDSEOF
chmod 600 "$CREDS_FILE"

echo -e "  ${YELLOW}Credentials also saved to: $CREDS_FILE (readable only by you)${NC}"
echo ""
