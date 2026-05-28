#!/usr/bin/env bash
# ============================================================
# DEPLOY — Content Library Fixes (May 2026)
# ============================================================
# Fixes:
#   1. AI outputs 401 → new JWT-auth /library/{id}/outputs endpoint
#   2. AI outputs not generated → better error surfacing + pipeline fix
#   3. Video/audio upload broken → VideoUploadExtractor (whisper-based)
#   4. Regenerate button working → new /library/{id}/regenerate endpoint
#   5. Startup warning if OPENAI_API_KEY is missing
# ============================================================
set -euo pipefail

BACKEND_DIR="/home/axisai/axisai-backend/axis-ai"
FRONTEND_DIR="/home/axisai/axis-frontend"

echo "=== Step 1: Pull latest backend code ==="
cd "$BACKEND_DIR/.."
git stash || true
git pull origin dev-video
cd "$BACKEND_DIR"

echo "=== Step 2: Install Python deps ==="
source .venv/bin/activate
pip install -e . --quiet

echo "=== Step 3: Run migrations (head) ==="
alembic upgrade head

echo "=== Step 4: Restart backend services ==="
sudo systemctl restart axis-ai axis-ai-worker axis-ai-beat
sleep 4
sudo systemctl status axis-ai axis-ai-worker axis-ai-beat --no-pager | grep -E "Active:|●"

echo "=== Step 5: Health check ==="
sleep 2
curl -sf https://axisai.edzlms.com/api/v1/health && echo " ✅ Backend OK" || echo " ❌ Backend FAILED"

echo ""
echo "=== Step 6: Check AI key at startup ==="
sudo journalctl -u axis-ai -n 30 --no-pager | grep -E "ai_key|no_ai_api_key|OPENAI" || echo "(no key log found — check service logs manually)"

echo ""
echo "=== Step 7: Pull latest frontend code ==="
cd "$FRONTEND_DIR"
git stash || true
git pull origin dev-video

echo "=== Step 8: Build Next.js frontend ==="
npm install --silent
npm run build

echo "=== Step 9: Restart frontend ==="
sudo systemctl restart axis-frontend 2>/dev/null || pm2 restart axis-frontend 2>/dev/null || echo "Restart frontend manually"
sleep 3

echo ""
echo "✅ Deployment complete!"
echo ""
echo "IMPORTANT: If AI outputs are still not generating, check .env:"
echo "  grep OPENAI_API_KEY /home/axisai/axisai-backend/axis-ai/.env"
echo "  If empty or missing: add OPENAI_API_KEY=sk-proj-... to .env"
echo "  Then: sudo systemctl restart axis-ai-worker axis-ai-beat"
echo ""
echo "Test: https://axis.edzlms.com/library"
