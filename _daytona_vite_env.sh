#!/bin/bash
set -euo pipefail
APP=/home/daytona/fintech-project/fintech-chatbot
printf '%s\n' 'VITE_API_URL=http://localhost:8000' > "$APP/frontend/.env"
pkill -f "vite --host" || true
sleep 1
cd "$APP/frontend"
nohup npm run dev -- --host 0.0.0.0 --port 5173 > /tmp/frontend.log 2>&1 &
sleep 4
tail -20 /tmp/frontend.log
curl -sS -m 3 -o /dev/null -w "fe:%{http_code}\n" http://127.0.0.1:5173/
ss -tlnp | grep -E "8000|5173" || true
