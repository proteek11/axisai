#!/bin/bash
# Fix: cookie name in /api/me/profile/route.ts
# Run from: /home/axisai/axis-frontend  (or wherever Next.js app lives)
# Then: pm2 restart axis-frontend  OR  systemctl restart axis-frontend

ROUTE_FILE="app/api/me/profile/route.ts"

if [ ! -f "$ROUTE_FILE" ]; then
  echo "❌ File not found: $ROUTE_FILE"
  echo "   Run this script from the axis-frontend directory"
  exit 1
fi

if grep -q "axis_access_token" "$ROUTE_FILE"; then
  sed -i "s/axis_access_token/axis_access/g" "$ROUTE_FILE"
  echo "✅ Fixed cookie name: axis_access_token → axis_access"
else
  echo "⏭  Already correct (or file doesn't match pattern)"
fi

echo ""
echo "Now rebuild and restart:"
echo "  npm run build && pm2 restart axis-frontend"
