#!/usr/bin/env bash
# The browser check, end to end: start a throwaway backend (FakeLLM, hash embedder, temp state file and
# index) and the frontend on two free ports, run the checks in Firefox and Chromium, stop both servers.
# Web research (B08) is on, against a fake Tavily (backend/tests/fake_tavily.py) on a third free port: no network.
# Never touches the user's app on 8000/5173. Used locally and in CI.
#
#   frontend/e2e/run.sh                      # both browsers
#   frontend/e2e/run.sh -k a02               # extra arguments go to pytest; still both browsers
#   frontend/e2e/run.sh --browser firefox    # one browser: any --browser replaces the default pair
#   E2E_API_PORT=8011 E2E_UI_PORT=5184 frontend/e2e/run.sh   # a fixed pair instead of two free ports
#   E2E_LATENCY_MS=300 frontend/e2e/run.sh   # slow mode: every API response 300 ms late, to find timing races
#                                            # before CI's slower runner does (conftest.py)
#
# Needs: backend deps (uv), frontend deps (npm ci), python3, and the browsers:
#   uv run --project frontend/e2e playwright install firefox chromium
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
# Two free ports from the OS, both held open until both are known, so they differ. Parallel runs and worktrees
# then never collide, and the ports are never 8000/5173 (the OS hands out ports above 32767).
read -r FREE_API FREE_UI TAVILY_PORT < <(python3 -c '
import socket
a, b, c = socket.socket(), socket.socket(), socket.socket()
a.bind(("127.0.0.1", 0)); b.bind(("127.0.0.1", 0)); c.bind(("127.0.0.1", 0))
print(a.getsockname()[1], b.getsockname()[1], c.getsockname()[1])')
API_PORT="${E2E_API_PORT:-$FREE_API}"
UI_PORT="${E2E_UI_PORT:-$FREE_UI}"

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

(cd "$ROOT/backend" && exec uv run python tests/fake_tavily.py --port "$TAVILY_PORT") >"$LOG_DIR/tavily.log" 2>&1 &
PIDS+=($!)
(cd "$ROOT/backend" && LLM_PROVIDER=fake STATE_PATH="$STATE_DIR/state.json" AS_OF= \
  EMBEDDER=hash INDEX_PATH="$STATE_DIR/index" SEARCH_MIN_SCORE= \
  CORS_ORIGINS="http://localhost:$UI_PORT,http://127.0.0.1:$UI_PORT" \
  TAVILY_API_KEY=tvly-fake-e2e TAVILY_MCP_URL="http://127.0.0.1:$TAVILY_PORT/mcp/" \
  TAVILY_API_URL="http://127.0.0.1:$TAVILY_PORT" WEB_RESEARCH_DAILY_CAP=1000 WEB_RESEARCH_USER_DAILY_CAP=1000 \
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

# Both browsers unless the arguments pick one: `run.sh -k a02` runs Firefox and Chromium.
case " $* " in
  *" --browser "* | *" --browser="*) ;;
  *) set -- --browser firefox --browser chromium "$@" ;;
esac
echo "Browser check on API port $API_PORT, UI port $UI_PORT${E2E_LATENCY_MS:+, slow mode ${E2E_LATENCY_MS} ms}: pytest $*"
cd "$HERE"
API_URL="http://localhost:$API_PORT" UI_URL="http://localhost:$UI_PORT" uv run --project "$HERE" pytest -q "$@"
