#!/bin/bash
# Quick frontend-only redeploy (for UI-only fixes)
set -e
cd /home/axisai/axis-frontend
git stash
git pull origin main  # or dev-video — match your branch
npm run build
pm2 restart axis-frontend --update-env
sleep 2
pm2 list | grep axis-frontend
echo "✓ Frontend redeployed"
