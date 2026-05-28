#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LXP Catalogue Refactor — Deployment Script
# Run this on the server as: bash DEPLOY_LXP.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

APP_DIR="/home/axisai/axisai-backend/axis-ai"
FRONTEND_DIR="/home/axisai/axisai-frontend"   # adjust if different
BRANCH="dev-video"

echo "──────────────────────────────────────────"
echo " Step 1 — Pull latest code (backend)"
echo "──────────────────────────────────────────"
cd /home/axisai/axisai-backend
git stash
git pull origin $BRANCH
chmod +x axis-ai/deploy.sh

echo "──────────────────────────────────────────"
echo " Step 2 — Install Python deps"
echo "──────────────────────────────────────────"
cd $APP_DIR
source .venv/bin/activate
pip install -e . --quiet

echo "──────────────────────────────────────────"
echo " Step 3 — Run migration 028"
echo "──────────────────────────────────────────"
alembic upgrade head
echo "Migration complete."

echo "──────────────────────────────────────────"
echo " Step 4 — Restart backend services"
echo "──────────────────────────────────────────"
sudo systemctl restart axis-ai axis-ai-worker axis-ai-beat
sleep 3
sudo systemctl status axis-ai axis-ai-worker axis-ai-beat --no-pager | grep -E "Active:|axis-ai"

echo "──────────────────────────────────────────"
echo " Step 5 — Health check"
echo "──────────────────────────────────────────"
curl -s https://axisai.edzlms.com/api/v1/health
echo ""

echo "──────────────────────────────────────────"
echo " Step 6 — Pull latest code (frontend)"
echo "──────────────────────────────────────────"
cd $FRONTEND_DIR
git stash
git pull origin $BRANCH 2>/dev/null || echo "Frontend on same repo — already pulled"

echo "──────────────────────────────────────────"
echo " Step 7 — Build Next.js frontend"
echo "──────────────────────────────────────────"
npm install --silent
npm run build

echo "──────────────────────────────────────────"
echo " Step 8 — Restart frontend service"
echo "──────────────────────────────────────────"
sudo systemctl restart axis-frontend 2>/dev/null || pm2 restart axis-frontend 2>/dev/null || echo "Restart frontend service manually"

echo ""
echo "✅  LXP deployment complete!"
echo "   Test the Content Library at: https://axis.edzlms.com/library"
