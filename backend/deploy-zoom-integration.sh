#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  deploy-zoom-integration.sh — Phase 19B: Zoom Live Class Integration        ║
# ║  Run from: /home/axisai/axisai-backend                                      ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
set -e

BACKEND_DIR="/home/axisai/axisai-backend/axis-ai"
FRONTEND_DIR="/home/axisai/axis-frontend"
VENV="$BACKEND_DIR/.venv"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Phase 19B — Zoom Live Class Integration Deploy"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. Pull latest code ───────────────────────────────────────────────────────
echo ""
echo "▶ [1/6] Pulling latest code..."
cd /home/axisai/axisai-backend
git stash
git pull origin dev-video
echo "✓ Code updated"

# ── 2. Backend: install deps + run migration ──────────────────────────────────
echo ""
echo "▶ [2/6] Installing Python dependencies..."
cd "$BACKEND_DIR"
source "$VENV/bin/activate"
pip install -e . --quiet
echo "✓ Dependencies installed"

echo ""
echo "▶ [3/6] Running Alembic migration 032 (live_class_sessions + live_class_attendance)..."
alembic upgrade head
echo "✓ Migration complete"

# ── 3. Restart backend services ───────────────────────────────────────────────
echo ""
echo "▶ [4/6] Restarting backend services..."
sudo systemctl restart axis-ai axis-ai-worker axis-ai-beat
sleep 4

# Verify all services up
FAILED=0
for svc in axis-ai axis-ai-worker axis-ai-beat; do
    STATUS=$(systemctl is-active "$svc" 2>/dev/null)
    if [ "$STATUS" = "active" ]; then
        echo "  ✓ $svc — active"
    else
        echo "  ✗ $svc — $STATUS (check: sudo journalctl -u $svc -n 30)"
        FAILED=1
    fi
done

if [ $FAILED -eq 1 ]; then
    echo ""
    echo "ERROR: One or more services failed. Check logs before deploying frontend."
    exit 1
fi

# ── 4. Health check ───────────────────────────────────────────────────────────
echo ""
echo "▶ [5/6] API health check..."
HEALTH=$(curl -sf https://axisai.edzlms.com/api/v1/health 2>/dev/null || echo "FAIL")
if echo "$HEALTH" | grep -q '"ok"'; then
    echo "✓ API healthy"
else
    echo "✗ Health check failed: $HEALTH"
    exit 1
fi

# ── 5. Frontend build + restart ───────────────────────────────────────────────
echo ""
echo "▶ [6/6] Building and restarting frontend..."
cd "$FRONTEND_DIR"
npm run build
pm2 restart axis-frontend --update-env
sleep 3

if pm2 list | grep -q "axis-frontend.*online"; then
    echo "✓ Frontend restarted"
else
    echo "⚠ Frontend may not be running — check: pm2 logs axis-frontend"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅  Deploy complete!"
echo ""
echo "  Next steps:"
echo "  1. In Zoom Marketplace → your Server-to-Server OAuth app:"
echo "     → Set webhook URL: https://axisai.edzlms.com/api/v1/webhooks/zoom"
echo "     → Subscribe to: meeting.ended, recording.completed"
echo "  2. In axis.edzlms.com → Admin → Zoom Integration:"
echo "     → Enter Account ID, Client ID, Client Secret, Webhook Secret"
echo "     → Click 'Test Connection'"
echo "  3. As creator: open any space → scroll to 'Live Classes' → Schedule a class"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
