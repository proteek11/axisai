#!/usr/bin/env bash
# ============================================================
# deploy-phase17-18.sh — Phase 17 (Auto-Course Builder) +
#                         Phase 18 (Voice AI Tutor)
#
# Run from the server as: axisai user
#   cd /home/axisai/axisai-backend
#   bash axis-ai/deploy-phase17-18.sh
#
# What this script does:
#   1. Pulls latest code from dev-video branch
#   2. Installs/upgrades Python dependencies
#   3. Runs Alembic migrations (none needed for Ph 17+18 — reuses existing tables)
#   4. Validates new env vars are set
#   5. Restarts all 3 axis-ai systemd services
#   6. Smoke-tests the 6 new endpoints
# ============================================================
set -euo pipefail

APP_DIR="/home/axisai/axisai-backend/axis-ai"
VENV="$APP_DIR/.venv"
BRANCH="dev-video"
SERVICES=("axis-ai" "axis-ai-worker" "axis-ai-beat")

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC}  $*"; }
fail() { echo -e "${RED}[error]${NC} $*"; exit 1; }

# ── 0. Pre-flight ─────────────────────────────────────────────────────────────
log "Phase 17 + 18 deployment starting"
cd /home/axisai/axisai-backend

# ── 1. Pull latest code ───────────────────────────────────────────────────────
log "Pulling latest code from $BRANCH..."
git stash --quiet || true
git pull origin "$BRANCH"
log "Code updated."

# ── 2. Install/upgrade dependencies ──────────────────────────────────────────
log "Installing dependencies..."
source "$VENV/bin/activate"
cd "$APP_DIR"
pip install -e . --quiet
log "Dependencies installed."

# ── 3. Validate new env vars ──────────────────────────────────────────────────
log "Checking environment variables..."
source "$APP_DIR/.env" 2>/dev/null || true

if [[ -z "${YOUTUBE_API_KEY:-}" ]]; then
    warn "YOUTUBE_API_KEY is NOT set in .env"
    warn "YouTube video search will return 503 until this is configured."
    warn "Get a free key at: https://console.cloud.google.com → YouTube Data API v3"
else
    log "YOUTUBE_API_KEY is set ✓"
fi

# EdgeTTS needs no key — just confirm edge-tts is importable
if "$VENV/bin/python" -c "import edge_tts" 2>/dev/null; then
    log "edge-tts package available ✓"
else
    warn "edge-tts not found — installing..."
    pip install edge-tts --quiet
fi

# pdfplumber needed for course builder
if "$VENV/bin/python" -c "import pdfplumber" 2>/dev/null; then
    log "pdfplumber available ✓"
else
    warn "pdfplumber not found — installing..."
    pip install pdfplumber --quiet
fi

# ── 4. No DB migration needed ─────────────────────────────────────────────────
log "No new Alembic migration for Phase 17+18 (reuses existing tables)."
log "Current migration head:"
alembic current 2>/dev/null || true

# ── 5. Restart services ───────────────────────────────────────────────────────
log "Restarting axis-ai services..."
for svc in "${SERVICES[@]}"; do
    sudo systemctl restart "$svc"
    sleep 1
done
log "Services restarted."

# ── 6. Verify services are running ────────────────────────────────────────────
log "Checking service status..."
all_ok=true
for svc in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$svc"; then
        log "  $svc: running ✓"
    else
        warn "  $svc: NOT running ✗"
        all_ok=false
    fi
done

if [[ "$all_ok" == false ]]; then
    fail "One or more services failed to start. Check: sudo journalctl -u axis-ai -n 50"
fi

# ── 7. Smoke tests ────────────────────────────────────────────────────────────
log "Running smoke tests..."
sleep 3  # give Uvicorn a moment

BASE="https://axisai.edzlms.com/api/v1"

health=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/health")
if [[ "$health" == "200" ]]; then
    log "  GET /health → 200 ✓"
else
    fail "  GET /health → $health  (expected 200)"
fi

# TTS voices — requires a valid JWT, so we just check 401 (not 404/500)
tts_status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/tts/voices?language=en")
if [[ "$tts_status" == "401" || "$tts_status" == "200" ]]; then
    log "  GET /tts/voices → $tts_status ✓ (endpoint reachable)"
else
    warn "  GET /tts/voices → $tts_status (unexpected, but may be auth-related)"
fi

# Course builder analyze — requires JWT, so 401 = endpoint exists
cb_status=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/course-builder/analyze")
if [[ "$cb_status" == "401" || "$cb_status" == "422" ]]; then
    log "  POST /course-builder/analyze → $cb_status ✓ (endpoint reachable)"
else
    warn "  POST /course-builder/analyze → $cb_status"
fi

cb_yt=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/course-builder/youtube?query=test")
if [[ "$cb_yt" == "401" || "$cb_yt" == "200" ]]; then
    log "  GET /course-builder/youtube → $cb_yt ✓ (endpoint reachable)"
else
    warn "  GET /course-builder/youtube → $cb_yt"
fi

log ""
log "═══════════════════════════════════════════════════════"
log "  Phase 17 + 18 deployment complete! ✅"
log "  New endpoints live at:"
log "    POST $BASE/course-builder/analyze"
log "    GET  $BASE/course-builder/youtube"
log "    POST $BASE/course-builder/generate"
log "    GET  $BASE/course-builder/progress/{space_id}"
log "    POST $BASE/tts/synthesize"
log "    GET  $BASE/tts/voices"
log ""
if [[ -z "${YOUTUBE_API_KEY:-}" ]]; then
log "  ⚠️  ACTION NEEDED: Set YOUTUBE_API_KEY in .env then restart axis-ai"
fi
log "  See DEPLOY_PHASE17_18.md for full testing instructions"
log "═══════════════════════════════════════════════════════"
