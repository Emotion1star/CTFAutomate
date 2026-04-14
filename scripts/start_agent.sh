#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$ROOT/runtime"
AGENT_LOG="$RUNTIME_DIR/agent.log"

mkdir -p "$RUNTIME_DIR"
cd "$ROOT"

nohup uv run --with-requirements agent/requirements.txt python agent/flaghunter.py >>"$AGENT_LOG" 2>&1 &
AGENT_PID=$!

echo "Agent started."
echo "PID : $AGENT_PID"
echo "Log : $AGENT_LOG"
