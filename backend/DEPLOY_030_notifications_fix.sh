#!/bin/bash
# Deploy fix: migration 030 — notifications user_id type fix
set -e

cd /home/axisai/axisai-backend

echo "=== Stashing local changes and pulling ==="
git stash
git pull origin dev-video

echo "=== Running migration 030 ==="
cd axis-ai
source ../.venv/bin/activate
alembic upgrade head

echo "=== Restarting services ==="
sudo systemctl restart axis-ai axis-ai-worker axis-ai-beat
sleep 3
sudo systemctl status axis-ai axis-ai-worker axis-ai-beat --no-pager

echo "=== Health check ==="
curl -s https://axisai.edzlms.com/api/v1/health

echo ""
echo "=== Done. Upload should now work. ==="
