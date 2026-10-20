#!/usr/bin/env bash
# Make the link-preview image again (B61, #108): the 1200 x 630 picture in the card a chat app shows for a link to
# the landing page (/ or /about). Run it from anywhere after a change to Patch, the brand or the landing page's words.
#
#   scripts/link-preview-image.sh
#
# It starts run.sh's throwaway servers (two free ports, a temp state file: never the app on 8000/5173), runs
# frontend/e2e/link_preview_image.py in Chromium, and writes frontend/public/link-preview/patch.png. Look at it, then
# commit it. Needs what the browser check needs: uv, `npm ci` in frontend/, and
# `uv run --project frontend/e2e playwright install chromium`.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/frontend/e2e/run.sh" --browser chromium link_preview_image.py -s
