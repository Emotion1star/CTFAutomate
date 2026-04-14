#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT/runtime/services.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "No runtime record found."
  exit 0
fi

source "$PID_FILE"

for name in AGENT FRONTEND BACKEND; do
  pid_var="${name}_PID"
  pid="${!pid_var:-}"
  if [[ -z "${pid}" ]]; then
    continue
  fi

  if kill -0 "$pid" >/dev/null 2>&1; then
    pkill -TERM -P "$pid" >/dev/null 2>&1 || true
    kill "$pid" >/dev/null 2>&1 || true
    echo "Stopped ${name,,} (PID $pid)"
  else
    echo "${name,,} already exited or PID $pid was not found"
  fi
done

rm -f "$PID_FILE"
echo "PID file removed."
