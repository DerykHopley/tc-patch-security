#!/usr/bin/env bash
# Take the landing page's six screenshots again (B42, #80): the dashboard, the CVEs page and Patch answering, in
# light and dark. Run it from anywhere after a change to those pages (the polish tickets #93 to #96 change them).
#
#   scripts/landing-shots.sh
#
# It starts run.sh's throwaway servers (two free ports, FakeLLM, the example watchlist, a temp state file: never the
# app on 8000/5173), runs frontend/e2e/landing_shots.py in Chromium (it encodes the WebP), and writes
# frontend/src/landing/shots/{dashboard,cves,chat}-{light,dark}.webp. Look at the six images, then commit them.
# Needs what the browser check needs: uv, `npm ci` in frontend/, and `uv run --project frontend/e2e playwright
# install chromium`.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/frontend/e2e/run.sh" --browser chromium landing_shots.py -s
