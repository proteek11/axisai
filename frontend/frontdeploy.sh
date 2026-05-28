#!/usr/bin/env bash
# ============================================================
# frontdeploy.sh — Axis AI Frontend Deploy Script
# Deploy path: /home/axisai/axis-frontend
# ============================================================
set -euo pipefail

# ── CONFIG ──────────────────────────────────────────────────
# APP_DIR  = where the Next.js code lives (axis-frontend folder)
# REPO_DIR = root of the git repo (one level up from axis-frontend)
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$APP_DIR/.." && pwd)"
PM2_APP_NAME="axis-frontend"
GIT_BRANCH="${GIT_BRANCH:-main}"
NODE_PORT="${NODE_PORT:-3000}"
MAX_HEALTH_RETRIES=12

# ── COLORS ──────────────────────────────────────────────────
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; BOLD='\033[1m'; RESET='\033[0m'
log()  { echo -e "${CYAN}[deploy]${RESET} $*"; }
ok()   { echo -e "${GREEN}[  OK  ]${RESET} $*"; }
warn() { echo -e "${YELLOW}[ WARN ]${RESET} $*"; }
fail() { echo -e "${RED}[ FAIL ]${RESET} $*"; exit 1; }
sep()  { echo -e "${BOLD}─────────────────────────────────────────${RESET}"; }

sep
echo -e "${BOLD}  Axis AI Frontend — Deploy${RESET}"
echo "  App dir : $APP_DIR"
echo "  Repo dir: $REPO_DIR"
echo "  Branch  : $GIT_BRANCH"
sep

cd "$APP_DIR"

# ── PREFLIGHT CHECKS ────────────────────────────────────────
for cmd in node npm git pm2; do
  command -v "$cmd" &>/dev/null || fail "$cmd not found. Run initial setup first."
done
ok "node $(node -v) · npm $(npm -v) · pm2 $(pm2 -v)"

[[ -f ".env.local" ]] || fail ".env.local missing. See setup guide."
ok ".env.local found"

# ── STEP 1: GIT PULL ─────────────────────────────────────────
sep
log "Step 1/5 — Pulling latest code…"
cd "$REPO_DIR"
git stash --quiet 2>/dev/null || true
git fetch origin "$GIT_BRANCH" --quiet
git checkout "$GIT_BRANCH" --quiet
git pull origin "$GIT_BRANCH"
ok "Updated. Latest commit: $(git log --oneline -1)"
cd "$APP_DIR"

# ── STEP 2: INSTALL DEPS ─────────────────────────────────────
sep
log "Step 2/5 — Installing npm dependencies…"
npm ci --prefer-offline 2>&1 | tail -3
ok "Dependencies ready"

# ── STEP 3: BUILD ────────────────────────────────────────────
sep
log "Step 3/5 — Building Next.js (production)…"
NODE_ENV=production npm run build 2>&1 | tail -15
ok "Build complete"

# ── STEP 4: PM2 RESTART ──────────────────────────────────────
sep
log "Step 4/5 — Restarting PM2…"
if pm2 list | grep -q "$PM2_APP_NAME"; then
  pm2 reload "$PM2_APP_NAME" --update-env
  ok "Reloaded (zero downtime)"
else
  pm2 start pm2.config.js --env production
  pm2 save
  ok "Started and saved"
fi

# ── STEP 5: HEALTH CHECK ─────────────────────────────────────
sep
log "Step 5/5 — Health check on localhost:$NODE_PORT…"
sleep 3
for i in $(seq 1 $MAX_HEALTH_RETRIES); do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$NODE_PORT" || echo "000")
  if [[ "$CODE" == "200" ]]; then
    ok "App is live (HTTP $CODE)"; break
  fi
  [[ $i -eq $MAX_HEALTH_RETRIES ]] \
    && warn "No response after 60s — check: pm2 logs $PM2_APP_NAME" \
    || { log "Waiting… ($i/$MAX_HEALTH_RETRIES, got $CODE)"; sleep 5; }
done

sep
echo -e "${GREEN}${BOLD}  ✓ Deploy done!${RESET}"
echo -e "  Logs : ${CYAN}pm2 logs $PM2_APP_NAME${RESET}"
echo -e "  Watch: ${CYAN}pm2 monit${RESET}"
echo ""
pm2 status
sep
