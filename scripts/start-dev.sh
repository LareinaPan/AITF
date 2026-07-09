#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

for port in 8000 5173; do
  if lsof -ti :"$port" >/dev/null 2>&1; then
    echo "Stopping process on port $port..."
    lsof -ti :"$port" | xargs kill -9 2>/dev/null || true
  fi
done

echo "Running database migrations..."
cd "$ROOT/backend"
source .venv/bin/activate
alembic upgrade head

echo "Starting backend on http://127.0.0.1:8000 ..."
nohup uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload \
  > "$ROOT/storage/backend-dev.log" 2>&1 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

echo "Starting frontend on http://127.0.0.1:5173 ..."
cd "$ROOT/frontend"
nohup npx vite --host 127.0.0.1 --port 5173 > "$ROOT/storage/frontend-dev.log" 2>&1 &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"

sleep 3
if curl -sf http://127.0.0.1:8000/health >/dev/null; then
  echo "Backend health check: OK"
else
  echo "Backend health check: FAILED (see storage/backend-dev.log)"
fi

echo ""
echo "Access the app at: http://127.0.0.1:5173"
echo "API docs: http://127.0.0.1:8000/docs"
