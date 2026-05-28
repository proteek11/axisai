#!/bin/bash
# ============================================================================
# DEPLOY_031_full_fix.sh
# Fixes two production bugs:
#   1. Notifications crash — user_notifications.user_id was INTEGER, should be VARCHAR(36)
#   2. File upload 413 — Nginx axis.edzlms.com missing client_max_body_size 500m
# ============================================================================
set -e

REPO_DIR=/home/axisai/axisai-backend
APP_DIR=$REPO_DIR/axis-ai
FRONTEND_NGINX=/etc/nginx/sites-available/axis-frontend

echo "================================================================"
echo " EDZLMS axis-ai — Full Fix Deploy"
echo " Fixes: migration 030 (notifications) + Nginx upload limit"
echo "================================================================"

# ── 1. Pull latest code ───────────────────────────────────────────────────────
echo ""
echo ">>> [1/5] Pulling latest code from dev-video..."
cd "$REPO_DIR"
git stash
git pull origin dev-video
echo "    ✓ Code up to date"

# ── 2. Run Alembic migrations ─────────────────────────────────────────────────
echo ""
echo ">>> [2/5] Running Alembic migrations..."
cd "$APP_DIR"
source ../.venv/bin/activate
alembic upgrade head
echo "    ✓ Migrations applied (migration 030: user_notifications.user_id → VARCHAR(36))"

# ── 3. Fix Nginx client_max_body_size for axis.edzlms.com ────────────────────
echo ""
echo ">>> [3/5] Checking Nginx config for axis.edzlms.com..."

if [ ! -f "$FRONTEND_NGINX" ]; then
    echo "    ⚠  WARNING: $FRONTEND_NGINX not found — creating it from template"
    sudo tee "$FRONTEND_NGINX" > /dev/null << 'NGINX_EOF'
# Nginx vhost for axis.edzlms.com (Next.js frontend)
server {
    listen 80;
    server_name axis.edzlms.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name axis.edzlms.com;

    # SSL — managed by Certbot
    ssl_certificate     /etc/letsencrypt/live/axis.edzlms.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/axis.edzlms.com/privkey.pem;
    include             /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam         /etc/letsencrypt/ssl-dhparams.pem;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;

    # Global upload size limit — allow video files up to 500 MB
    client_max_body_size 500m;

    gzip on;
    gzip_vary on;
    gzip_min_length 1000;
    gzip_proxied any;
    gzip_types text/plain text/css application/json application/javascript text/javascript;

    location /_next/static/ {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        add_header Cache-Control "public, max-age=31536000, immutable";
        access_log off;
    }

    location /api/spaces/ {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 500m;
        proxy_request_buffering off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_connect_timeout 10s;
    }

    location /api/library/ {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 500m;
        proxy_request_buffering off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_connect_timeout 10s;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 300s;
        proxy_connect_timeout 10s;
        proxy_send_timeout 300s;
    }
}
NGINX_EOF
    sudo ln -sf "$FRONTEND_NGINX" /etc/nginx/sites-enabled/axis-frontend 2>/dev/null || true
    echo "    ✓ Created Nginx config with 500m upload limit"
else
    # Config exists — check if client_max_body_size is already set correctly
    if grep -q "client_max_body_size 500m" "$FRONTEND_NGINX"; then
        echo "    ✓ Nginx already has client_max_body_size 500m"
    elif grep -q "client_max_body_size" "$FRONTEND_NGINX"; then
        echo "    ⚠  Nginx has a different client_max_body_size — patching to 500m..."
        sudo sed -i 's/client_max_body_size [^;]*/client_max_body_size 500m/g' "$FRONTEND_NGINX"
        echo "    ✓ Patched to 500m"
    else
        echo "    ⚠  No client_max_body_size found — injecting 500m after server_name directive..."
        sudo sed -i '/server_name axis.edzlms.com;/a\\n    # Upload size limit — allow files up to 500 MB\n    client_max_body_size 500m;' "$FRONTEND_NGINX"
        echo "    ✓ Injected client_max_body_size 500m"
    fi

    # Also ensure /api/library/ location has a 500m limit (add after /api/spaces/ block if missing)
    if ! grep -q "location /api/library/" "$FRONTEND_NGINX"; then
        echo "    + Adding /api/library/ location block with 500m limit..."
        sudo sed -i '/location \/api\/spaces\//,/^    }/{ /^    }/a\\\n    location /api/library/ {\n        proxy_pass http://127.0.0.1:3000;\n        proxy_http_version 1.1;\n        proxy_set_header Host $host;\n        client_max_body_size 500m;\n        proxy_request_buffering off;\n        proxy_read_timeout 600s;\n    }\n }' "$FRONTEND_NGINX" 2>/dev/null || true
    fi
fi

# ── 4. Reload Nginx ───────────────────────────────────────────────────────────
echo ""
echo ">>> [4/5] Testing and reloading Nginx..."
sudo nginx -t
sudo systemctl reload nginx
echo "    ✓ Nginx reloaded"

# ── 5. Restart axis-ai services ───────────────────────────────────────────────
echo ""
echo ">>> [5/5] Restarting axis-ai services..."
sudo systemctl restart axis-ai axis-ai-worker axis-ai-beat
sleep 4
sudo systemctl status axis-ai axis-ai-worker axis-ai-beat --no-pager

echo ""
echo "=== Health check ==="
curl -s https://axisai.edzlms.com/api/v1/health

echo ""
echo "================================================================"
echo " ✅ Deploy complete!"
echo ""
echo " Fixes applied:"
echo "   • Migration 030: user_notifications.user_id → VARCHAR(36)"
echo "   • Nginx: client_max_body_size 500m on axis.edzlms.com"
echo ""
echo " Test now:"
echo "   1. Open https://axis.edzlms.com/library → upload any PDF"
echo "   2. Open any space → Add Content → upload a PDF"
echo "   Both should work without 413 or notification crashes."
echo "================================================================"
