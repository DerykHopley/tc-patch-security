#!/usr/bin/env bash
# The browser check, end to end: start a throwaway backend (FakeLLM, temp state file) on 8001 and
# the frontend on 5174, run the checks in Firefox and Chromium, stop both servers.
# Never touches the user's app on 8000/5173. Used locally and in CI.
#
#   frontend/e2e/run.sh                      # both browsers
#   frontend/e2e/run.sh --browser firefox    # extra arguments go to pytest
#
# Needs: backend deps (uv), frontend deps (npm ci), and the browsers:
#   uv run --project frontend/e2e playwright install firefox chromium
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
API_PORT=8001
UI_PORT=5174

for port in "$API_PORT" "$UI_PORT"; do
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    echo "Port $port is already in use. Stop that server first: the check needs its own pair." >&2
    exit 1
  fi
done

STATE_DIR="$(mktemp -d)"
LOG_DIR="${E2E_LOG_DIR:-$STATE_DIR}"
PIDS=()
cleanup() {
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
  rm -rf "$STATE_DIR"
}
trap cleanup EXIT

(cd "$ROOT/backend" && LLM_PROVIDER=fake STATE_PATH="$STATE_DIR/state.json" AS_OF= \
  CORS_ORIGINS="http://localhost:$UI_PORT,http://127.0.0.1:$UI_PORT" \
  exec uv run uvicorn app.main:app --port "$API_PORT") >"$LOG_DIR/backend.log" 2>&1 &
PIDS+=($!)
(cd "$ROOT/frontend" && VITE_API_URL="http://localhost:$API_PORT" \
  exec node_modules/.bin/vite --port "$UI_PORT" --strictPort) >"$LOG_DIR/frontend.log" 2>&1 &
PIDS+=($!)

wait_for() {
  for _ in $(seq 1 60); do
    if curl -fsS "$1" >/dev/null 2>&1; then return 0; fi
    sleep 0.5
  done
  echo "$1 didn't answer within 30 s. Logs:" >&2
  cat "$LOG_DIR"/*.log >&2
  return 1
}
wait_for "http://localhost:$API_PORT/health"
wait_for "http://localhost:$UI_PORT/"

if [ "$#" -eq 0 ]; then set -- --browser firefox --browser chromium; fi
cd "$HERE"
UI_URL="http://localhost:$UI_PORT" uv run --project "$HERE" pytest -q "$@"
