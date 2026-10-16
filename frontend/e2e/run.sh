#!/usr/bin/env bash
# The browser check, end to end: start a throwaway backend (FakeLLM, hash embedder, temp state file and
# index) and the frontend on two free ports, run the checks in Firefox and Chromium, stop both servers.
# A second pair runs in live mode on the fake feeds (B02), for Check now: its refresh changes the CVE data, so it
# never shares a backend with the snapshot checks (DECISIONS.md, 2026-10-15).
# Web research (B08) is on, against a fake Tavily (backend/tests/fake_tavily.py) on its own free port: no network.
# Never touches the user's app on 8000/5173. Used locally and in CI. NOTIFY_DRY_RUN=1: alerts (a refresh's, B04)
# are recorded, never sent, so no desktop notification pops up on the machine running the check. The chat limits
# (B11) are raised: the check sends hundreds of messages as one user; test_rate_limits.py routes its own 429.
# Both pairs run with sign-in off (AUTH=off). A third pair with sign-in on (B10) starts only when the Clerk test
# instance's keys and a test user are exported: CLERK_SECRET_KEY, CLERK_PUBLISHABLE_KEY, CLERK_JWT_KEY,
# E2E_CLERK_USER_USERNAME, E2E_CLERK_USER_PASSWORD. Then test_sign_in.py signs in with Clerk's testing tokens (that
# check, and only it, calls Clerk); without them it skips.
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
read -r FREE_API FREE_UI LIVE_API_PORT LIVE_UI_PORT TAVILY_PORT < <(python3 -c '
import socket
socks = [socket.socket() for _ in range(5)]
for s in socks: s.bind(("127.0.0.1", 0))
print(*(s.getsockname()[1] for s in socks))')
API_PORT="${E2E_API_PORT:-$FREE_API}"
UI_PORT="${E2E_UI_PORT:-$FREE_UI}"

for port in "$API_PORT" "$UI_PORT" "$LIVE_API_PORT" "$LIVE_UI_PORT"; do
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
(cd "$ROOT/backend" && LLM_PROVIDER=fake STATE_PATH="$STATE_DIR/state.json" AS_OF= NOTIFY_DRY_RUN=1 AUTH=off \
  EMBEDDER=hash INDEX_PATH="$STATE_DIR/index" SEARCH_MIN_SCORE= \
  CORS_ORIGINS="http://localhost:$UI_PORT,http://127.0.0.1:$UI_PORT" \
  TAVILY_API_KEY=tvly-fake-e2e TAVILY_MCP_URL="http://127.0.0.1:$TAVILY_PORT/mcp/" \
  TAVILY_API_URL="http://127.0.0.1:$TAVILY_PORT" WEB_RESEARCH_DAILY_CAP=1000 WEB_RESEARCH_USER_DAILY_CAP=1000 \
  CHAT_PER_MINUTE=10000 CHAT_PER_DAY=100000 \
  exec uv run uvicorn app.main:app --port "$API_PORT") >"$LOG_DIR/backend.log" 2>&1 &
PIDS+=($!)
(cd "$ROOT/frontend" && VITE_API_URL="http://localhost:$API_PORT" \
  exec node_modules/.bin/vite --port "$UI_PORT" --strictPort) >"$LOG_DIR/frontend.log" 2>&1 &
PIDS+=($!)
# The live pair (B02): live mode, the fake feeds on day 2, its own state, live folder and index.
(cd "$ROOT/backend" && LLM_PROVIDER=fake STATE_PATH="$STATE_DIR/live-state.json" AS_OF= NOTIFY_DRY_RUN=1 AUTH=off \
  DATA_MODE=live FEEDS=fake FAKE_FEEDS_DAY=2 LIVE_PATH="$STATE_DIR/live" CHAT_PER_MINUTE=10000 CHAT_PER_DAY=100000 \
  EMBEDDER=hash INDEX_PATH="$STATE_DIR/live-index" SEARCH_MIN_SCORE= \
  CORS_ORIGINS="http://localhost:$LIVE_UI_PORT,http://127.0.0.1:$LIVE_UI_PORT" \
  exec uv run uvicorn app.main:app --port "$LIVE_API_PORT") >"$LOG_DIR/live-backend.log" 2>&1 &
PIDS+=($!)
(cd "$ROOT/frontend" && VITE_API_URL="http://localhost:$LIVE_API_PORT" \
  exec node_modules/.bin/vite --port "$LIVE_UI_PORT" --strictPort) >"$LOG_DIR/live-frontend.log" 2>&1 &
PIDS+=($!)

# The sign-in pair (B10): sign-in on against a real Clerk development instance, only when its keys and a test
# user are in the environment (a laptop with them exported, or CI with the secrets). Without them its check skips.
AUTH_PAIR=""
if [ -n "${CLERK_SECRET_KEY:-}" ] && [ -n "${CLERK_PUBLISHABLE_KEY:-}" ] && [ -n "${CLERK_JWT_KEY:-}" ] \
  && [ -n "${E2E_CLERK_USER_USERNAME:-}" ] && [ -n "${E2E_CLERK_USER_PASSWORD:-}" ]; then
  read -r AUTH_API_PORT AUTH_UI_PORT < <(python3 -c '
import socket
socks = [socket.socket() for _ in range(2)]
for s in socks: s.bind(("127.0.0.1", 0))
print(*(s.getsockname()[1] for s in socks))')
  AUTH_PAIR=1
  (cd "$ROOT/backend" && env -u CLERK_SECRET_KEY LLM_PROVIDER=fake STATE_PATH="$STATE_DIR/auth-state.json" AS_OF= \
    NOTIFY_DRY_RUN=1 EMBEDDER=hash INDEX_PATH="$STATE_DIR/auth-index" SEARCH_MIN_SCORE= \
    CORS_ORIGINS="http://localhost:$AUTH_UI_PORT" AUTH=on AUTH_ALLOWED_ORIGINS="http://localhost:$AUTH_UI_PORT" \
    exec uv run uvicorn app.main:app --port "$AUTH_API_PORT") >"$LOG_DIR/auth-backend.log" 2>&1 &
  PIDS+=($!)
  (cd "$ROOT/frontend" && VITE_API_URL="http://localhost:$AUTH_API_PORT" \
    exec node_modules/.bin/vite --port "$AUTH_UI_PORT" --strictPort) >"$LOG_DIR/auth-frontend.log" 2>&1 &
  PIDS+=($!)
fi

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
wait_for "http://localhost:$LIVE_API_PORT/health"
wait_for "http://localhost:$LIVE_UI_PORT/"
if [ -n "$AUTH_PAIR" ]; then
  wait_for "http://localhost:$AUTH_API_PORT/health"
  wait_for "http://localhost:$AUTH_UI_PORT/"
  export AUTH_API_URL="http://localhost:$AUTH_API_PORT" AUTH_UI_URL="http://localhost:$AUTH_UI_PORT"
fi

# Both browsers unless the arguments pick one: `run.sh -k a02` runs Firefox and Chromium.
case " $* " in
  *" --browser "* | *" --browser="*) ;;
  *) set -- --browser firefox --browser chromium "$@" ;;
esac
echo "Browser check on API port $API_PORT, UI port $UI_PORT${E2E_LATENCY_MS:+, slow mode ${E2E_LATENCY_MS} ms}: pytest $*"
cd "$HERE"
API_URL="http://localhost:$API_PORT" UI_URL="http://localhost:$UI_PORT" \
  LIVE_API_URL="http://localhost:$LIVE_API_PORT" LIVE_UI_URL="http://localhost:$LIVE_UI_PORT" uv run --project "$HERE" pytest -q "$@"
