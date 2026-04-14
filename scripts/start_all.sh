#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$ROOT/runtime"
PID_FILE="$RUNTIME_DIR/services.pid"
START_AGENT="${START_AGENT:-0}"

mkdir -p "$RUNTIME_DIR"

if [[ -f "$PID_FILE" ]]; then
  echo "Existing runtime record found. Run scripts/stop_all.sh first."
  exit 1
fi

BACKEND_LOG="$RUNTIME_DIR/backend.log"
FRONTEND_LOG="$RUNTIME_DIR/frontend.log"
AGENT_LOG="$RUNTIME_DIR/agent.log"
cd "$ROOT"

nohup uv run --with-requirements server/backend/requirements.txt python server/backend/app.py >>"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

for _ in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:5000/health >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS http://127.0.0.1:5000/health >/dev/null 2>&1; then
  echo "Backend did not become healthy in time. Check $BACKEND_LOG"
  kill "$BACKEND_PID" >/dev/null 2>&1 || true
  exit 1
fi

nohup uv run python scripts/serve_frontend.py >>"$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

sleep 1

AGENT_PID=""
if [[ "$START_AGENT" == "1" || "$START_AGENT" == "true" || "$START_AGENT" == "TRUE" ]]; then
  nohup uv run --with-requirements agent/requirements.txt python agent/flaghunter.py >>"$AGENT_LOG" 2>&1 &
  AGENT_PID=$!
  sleep 2
fi

cat >"$PID_FILE" <<EOF
BACKEND_PID=$BACKEND_PID
FRONTEND_PID=$FRONTEND_PID
AGENT_PID=$AGENT_PID
EOF

echo "Services started."
echo "Backend : http://127.0.0.1:5000"
echo "Frontend: http://127.0.0.1:8080"
if [[ -n "$AGENT_PID" ]]; then
  echo "Agent   : started (PID $AGENT_PID)"
else
  echo "Agent   : 当前未启动，请执行 scripts/start_agent.sh"
fi
echo "PID file: $PID_FILE"
echo "Logs    : $RUNTIME_DIR"
