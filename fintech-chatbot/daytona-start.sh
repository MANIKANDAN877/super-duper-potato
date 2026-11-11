#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [ ! -f backend/.env ]; then
  cp backend/.env.example backend/.env
fi

docker compose up --build -d

echo "Daytona sandbox stack is starting."
echo "Frontend: http://localhost:5173"
echo "Backend: http://localhost:8000"
echo "PostgreSQL: localhost:5432"
