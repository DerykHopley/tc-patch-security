#!/usr/bin/env bash
# The container's smoke test (B12, #34): build the hash index and the image, start it on a free port with FakeLLM and
# the baked index, check /health, the embedder check and that no .env got in, then the short browser check
# (test_container.py: the dashboard loads, the chat answers). Removes its container and image at the end.
# Never touches the user's app on 8000/5173. Used locally and in CI.
#
#   frontend/e2e/container.sh                    # Chromium
#   frontend/e2e/container.sh --browser firefox  # extra arguments go to pytest
#   KEEP_IMAGE=1 frontend/e2e/container.sh       # keep the image (tagged patch:smoke) afterwards
#
# Needs: docker, backend deps (uv), and the browser: uv run --project frontend/e2e playwright install chromium
#
# Snapshot mode and sign-in off are the app's defaults today. B02 (#35) and B10 (#42) add their settings: set them
# off here when they land.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
IMAGE="patch:smoke-$$"
NAME="patch-smoke-$$"
# A free port from the OS (above 32767), so never 8000/5173 and never a parallel run's
PORT="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"

cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  if [ -n "${KEEP_IMAGE:-}" ]; then docker tag "$IMAGE" patch:smoke >/dev/null 2>&1 || true; fi
  docker rmi -f "$IMAGE" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "== Building the hash index (the existing script) and the image"
(cd "$ROOT/backend" && EMBEDDER=hash EMBED_MODEL= INDEX_PATH=data/index-image uv run python -m app.rag.build_index)
docker build -t "$IMAGE" "$ROOT"

echo "== B12.7: no key or .env in the image"
found="$(docker run --rm --entrypoint sh "$IMAGE" -c \
  'find / -xdev \( -name ".env" -o -name "*.env" \) -not -path "/proc/*" 2>/dev/null; env | grep -E "^(OPENROUTER_API_KEY|NTFY_TOPIC|NTFY_TOKEN|SMTP_PASSWORD)=." || true')"
if [ -n "$found" ]; then echo "Found in the image: $found" >&2; exit 1; fi

echo "== B12.8: another embedder than the index's stops the start-up"
if out="$(docker run --rm -e EMBEDDER=ollama "$IMAGE" 2>&1)"; then
  echo "The image started with EMBEDDER=ollama on a hash index. Output:" >&2; echo "$out" >&2; exit 1
fi
grep -q "was built with hash" <<<"$out" || { echo "Not the index-mismatch error:" >&2; echo "$out" >&2; exit 1; }

echo "== Starting the image on port $PORT"
docker run -d --name "$NAME" -p "127.0.0.1:$PORT:8080" -e LLM_PROVIDER=fake "$IMAGE" >/dev/null
for _ in $(seq 1 60); do
  if curl -fsS "http://localhost:$PORT/health" >/dev/null 2>&1; then break; fi
  if [ "$(docker inspect -f '{{.State.Running}}' "$NAME")" != true ]; then break; fi
  sleep 0.5
done

echo "== B12.9: /health answers, from the baked index"
health="$(curl -fsS "http://localhost:$PORT/health")" || { echo "No /health. Logs:" >&2; docker logs "$NAME" >&2; exit 1; }
echo "$health"
grep -q '"llm":"fake"' <<<"$health" || { echo "Not FakeLLM" >&2; exit 1; }
if docker logs "$NAME" 2>&1 | grep -q "Rebuilding the free hash search index"; then
  echo "The image rebuilt its index at start-up: the baked one didn't match." >&2; exit 1
fi

echo "== Browser check against the image"
case " $* " in
  *" --browser "* | *" --browser="*) ;;
  *) set -- --browser chromium "$@" ;;
esac
cd "$HERE"
status=0
UI_URL="http://localhost:$PORT" API_URL="http://localhost:$PORT/api" \
  uv run --project "$HERE" pytest -q test_container.py "$@" || status=$?
if [ "$status" -ne 0 ]; then docker logs "$NAME" >&2; fi
exit "$status"
