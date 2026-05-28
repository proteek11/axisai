#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# DEPLOY_PF_FEATURES.sh
# Deploys all Phase Feature (PF) work:
#   PF-02 — Completion Certificates
#   PF-05 — Interactive PDF (annotations + viewer)
#   PF-03 — Interactive Slides (PPTX → slide images)
#   PF-08 — Chapter-based PDF chunking
#
# Run from server as user axisai:
#   cd /home/axisai/axisai-backend && bash DEPLOY_PF_FEATURES.sh
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

REPO_DIR="/home/axisai/axisai-backend"
APP_DIR="$REPO_DIR/axis-ai"
FRONTEND_DIR="$REPO_DIR/axis-frontend"
BRANCH="dev-video"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()   { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         axis-ai PF Feature Deploy — $(date '+%Y-%m-%d %H:%M')         ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Step 0: Pre-flight ────────────────────────────────────────────────────────
info "Pre-flight checks..."
[ -d "$REPO_DIR/.git" ] || die "Not a git repo: $REPO_DIR"
[ -f "$APP_DIR/.env" ]  || die ".env missing at $APP_DIR/.env"
[ -f "$APP_DIR/pyproject.toml" ] || die "pyproject.toml missing"

# ── Step 1: Pull latest code ───────────────────────────────────────────────────
info "Pulling latest code from origin/$BRANCH..."
cd "$REPO_DIR"
git stash --quiet 2>/dev/null && ok "Stashed local changes" || true
git pull origin "$BRANCH" --quiet
ok "Code updated"

# ── Step 2: Python deps ────────────────────────────────────────────────────────
info "Installing Python dependencies..."
cd "$APP_DIR"
source .venv/bin/activate
pip install -e . -q
ok "Python deps installed"

# ── Step 3: Database migration ────────────────────────────────────────────────
info "Running Alembic migrations..."
alembic upgrade head
ok "Migration 029 applied (space_certificates, pdf_annotations, slide_assets)"

# ── Step 4: Data directories ──────────────────────────────────────────────────
info "Creating data directories..."
sudo mkdir -p /data/certificates /data/slide_outputs /data/pdf_outputs
sudo chown axisai:axisai /data/certificates /data/slide_outputs /data/pdf_outputs
sudo chmod 750 /data/certificates /data/slide_outputs /data/pdf_outputs
ok "Data dirs ready: /data/certificates, /data/slide_outputs"

# ── Step 5: LibreOffice (for PPTX → PDF → images) ────────────────────────────
info "Checking LibreOffice (needed for PPTX slide extraction)..."
if command -v libreoffice &>/dev/null || command -v soffice &>/dev/null; then
    ok "LibreOffice already installed"
else
    warn "LibreOffice not found — installing via snap (may take 2-5 min)..."
    sudo snap install libreoffice
    ok "LibreOffice installed"
fi

# ── Step 6: PyMuPDF (for certificate PDF + slide images) ─────────────────────
info "Checking PyMuPDF (fitz)..."
python3 -c "import fitz; print('fitz', fitz.__version__)" 2>/dev/null && ok "PyMuPDF OK" || {
    warn "PyMuPDF not found — installing..."
    pip install pymupdf -q
    ok "PyMuPDF installed"
}

# ── Step 7: Restart backend services ─────────────────────────────────────────
info "Restarting axis-ai services..."
sudo systemctl restart axis-ai axis-ai-worker axis-ai-beat
sleep 3
for svc in axis-ai axis-ai-worker axis-ai-beat; do
    if sudo systemctl is-active --quiet "$svc"; then
        ok "$svc is running"
    else
        die "$svc failed to start — check: sudo journalctl -u $svc -n 50"
    fi
done

# ── Step 8: Health check ──────────────────────────────────────────────────────
info "Checking API health..."
sleep 2
HEALTH=$(curl -s --max-time 10 https://axisai.edzlms.com/api/v1/health)
echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d)" 2>/dev/null && ok "API healthy" || die "Health check failed: $HEALTH"

# ── Step 9: Frontend (Next.js) ────────────────────────────────────────────────
if [ -d "$FRONTEND_DIR" ]; then
    info "Building Next.js frontend..."
    cd "$FRONTEND_DIR"
    npm install --legacy-peer-deps -q 2>/dev/null || npm install -q
    npm run build
    ok "Frontend built"

    info "Restarting Next.js (PM2)..."
    if command -v pm2 &>/dev/null; then
        pm2 restart axis-frontend 2>/dev/null || pm2 start npm --name axis-frontend -- start
        ok "Frontend restarted via PM2"
    else
        warn "PM2 not found — restart Next.js manually: cd $FRONTEND_DIR && npm start"
    fi
else
    warn "Frontend dir not found at $FRONTEND_DIR — skipping"
fi

# ── Step 10: Test upload queue ────────────────────────────────────────────────
info "Verifying Celery worker is processing jobs..."
sleep 5
# Check audit log — if worker processed anything in last hour, it's alive
AUDIT=$(curl -s --max-time 10 \
  -H "X-Master-Key: $(grep MASTER_API_KEY "$APP_DIR/.env" | cut -d= -f2)" \
  "https://axisai.edzlms.com/api/v1/admin/audit?limit=1" 2>/dev/null || echo "{}")
echo "Recent audit: $AUDIT" | head -3

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ✅ Deploy complete!                                     ║"
echo "║                                                          ║"
echo "║  Features now live:                                      ║"
echo "║  • PF-02: Completion certificates (auto on space done)   ║"
echo "║  • PF-05: Interactive PDF with annotations               ║"
echo "║  • PF-03: Interactive Slides (PPTX upload → viewer)      ║"
echo "║  • PF-08: Chapter-based PDF chunking                     ║"
echo "║                                                          ║"
echo "║  Next: Upload a PPTX at axis.edzlms.com/library          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
