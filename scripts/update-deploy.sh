#!/usr/bin/env bash
# Update the live Patch on Cloud Run to the code checked out here. One command, no questions (DEPLOY.md, B71).
#
#   scripts/update-deploy.sh                    # check, build, deploy, verify
#   scripts/update-deploy.sh --dry-run          # every check, then print what it would do; nothing changes
#   scripts/update-deploy.sh --rotate telegram  # also store a new TELEGRAM_BOT_TOKEN from backend/.env (or tavily)
#
# It stops, and changes nothing live, when something is wrong: uncommitted changes, a branch that has diverged from
# GitHub, CI not green for this code, a missing key, or a new version that doesn't answer. It never asks.
# Needs the first deploy (scripts/deploy-wizard.sh): it reads deploy/cloudrun/wizard.env and env.yaml.
#
# Other flags: --skip-ci (deploy without the CI check), --rebuild-index, --keep N (images kept, default 3).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
WIZARD_ENV="deploy/cloudrun/wizard.env"
ENV_YAML="deploy/cloudrun/env.yaml"
LOCAL_ENV="backend/.env"
SERVICE=patch
WORKFLOW=CI
DRY=no; SKIP_CI=no; REBUILD=auto; KEEP=3; ROTATE=()

while (( $# )); do
  case "$1" in
    --dry-run) DRY=yes ;;
    --skip-ci) SKIP_CI=yes ;;
    --rebuild-index) REBUILD=yes ;;
    --keep) KEEP="${2:?--keep needs a number}"; shift ;;
    --rotate) ROTATE+=("${2:?--rotate needs telegram or tavily}"); shift ;;
    -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) printf 'Unknown option %s (see --help).\n' "$1"; exit 2 ;;
  esac
  shift
done
[[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || { printf -- '--keep needs a number from 1.\n'; exit 2; }

if [[ -t 1 ]]; then B=$'\e[1m'; D=$'\e[2m'; G=$'\e[32m'; Y=$'\e[33m'; R=$'\e[31m'; N=$'\e[0m'; else B= D= G= Y= R= N=; fi
step() { printf '\n%s▸ %s%s\n' "$B" "$1" "$N"; }
ok()   { printf '  %s✓%s %s\n' "$G" "$N" "$1"; }
info() { printf '  %s%s%s\n' "$D" "$1" "$N"; }
stop() { printf '\n  %s✗ %s%s\n  %sNothing on the live app changed.%s\n\n' "$R" "$1" "$N" "$D" "$N"; exit 1; }
# do_ "what" cmd...: runs it, or in a dry run prints it
do_() { local what="$1"; shift; if [[ $DRY == yes ]]; then info "would run: $what"; else "$@"; fi; }

saved()  { grep -E "^${1}=" "$WIZARD_ENV" 2>/dev/null | tail -n1 | cut -d= -f2-; }
local_() { grep -E "^${1}=" "$LOCAL_ENV" 2>/dev/null | tail -n1 | cut -d= -f2- | sed -E "s/^['\"]|['\"]$//g"; }
save() {
  local tmp; tmp=$(mktemp)
  grep -vE "^${1}=" "$WIZARD_ENV" > "$tmp" || true
  printf '%s=%s\n' "$1" "$2" >> "$tmp"; mv "$tmp" "$WIZARD_ENV"
}

[[ -f "$WIZARD_ENV" && -f "$ENV_YAML" ]] || stop "No first deploy found ($WIZARD_ENV, $ENV_YAML). Run scripts/deploy-wizard.sh first."
PROJECT_ID=$(saved PROJECT_ID); PROJECT_NUMBER=$(saved PROJECT_NUMBER); REGION=$(saved REGION)
[[ -n "$PROJECT_ID" && -n "$PROJECT_NUMBER" && -n "$REGION" ]] || stop "$WIZARD_ENV lacks PROJECT_ID, PROJECT_NUMBER or REGION."
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/patch/patch"
URL="https://$SERVICE-$PROJECT_NUMBER.$REGION.run.app"
SA="patch-run@$PROJECT_ID.iam.gserviceaccount.com"
[[ -d scripts/google-cloud-sdk/bin ]] && PATH="$ROOT/scripts/google-cloud-sdk/bin:$PATH"

printf '%sUpdate Patch on Cloud Run%s  %s%s%s%s\n' "$B" "$N" "$D" "$URL" "$([[ $DRY == yes ]] && echo '  (dry run)')" "$N"

# ── 1. The code ──────────────────────────────────────────────────────────────────────────────────────────────────────
step "The code"
for tool in gcloud docker uv git; do command -v "$tool" >/dev/null 2>&1 || stop "$tool is missing."; done
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || stop "This checkout has uncommitted changes. Commit or stash them first: they would go into the image."
BRANCH=$(git rev-parse --abbrev-ref HEAD)
git fetch -q origin 2>/dev/null || info "couldn't reach GitHub: comparing with what was last fetched"
UPSTREAM=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)
if [[ -n "$UPSTREAM" ]] && (( $(git rev-list --count HEAD.."$UPSTREAM") > 0 )); then
  git merge-base --is-ancestor HEAD "$UPSTREAM" || stop "$BRANCH and $UPSTREAM have diverged. Sort that out first."
  do_ "git merge --ff-only $UPSTREAM" git merge --ff-only -q "$UPSTREAM"
  ok "fast-forwarded to $UPSTREAM"
fi
HEAD_SHA=$(git rev-parse HEAD)
ok "$BRANCH at $(git log -1 --format='%h %s' | cut -c1-80)"
LAST=$(saved DEPLOYED_COMMIT)
if [[ -n "$LAST" ]] && git cat-file -e "$LAST" 2>/dev/null; then
  NEW=$(git rev-list --count "$LAST"..HEAD)
  info "live now: $(git log -1 --format='%h' "$LAST") ($(saved TAG)); $NEW new commit(s)"
  (( NEW > 0 )) || info "nothing new since the live version: this redeploys the same code"
fi

# ── 2. CI ────────────────────────────────────────────────────────────────────────────────────────────────────────────
# HEAD's own run must pass. A docs-only push skips the browser checks and shows green while the code under it may
# not be, so the newest run before it that did run them must pass too (the B71 rule; v7 shipped past a red run).
step "CI"
if [[ $SKIP_CI == yes ]]; then
  printf '  %s⚠ skipped (--skip-ci)%s\n' "$Y" "$N"
else
  command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1 || stop "gh isn't signed in, so CI can't be checked. Run gh auth login, or pass --skip-ci."
  run_for() { gh run list --workflow "$WORKFLOW" --branch "$BRANCH" --commit "$1" --event push --limit 1 \
                --json databaseId,status,conclusion -q '.[0] | "\(.databaseId) \(.status) \(.conclusion)"' 2>/dev/null; }
  browser_ran() { gh run view "$1" --json jobs -q '[.jobs[] | select(.name|startswith("Browser check")) | .conclusion]
                    | any(. == "success" or . == "failure" or . == "cancelled" or . == "timed_out")' 2>/dev/null; }
  read -r RUN STATUS CONCL <<<"$(run_for "$HEAD_SHA")"
  [[ -n "${RUN:-}" ]] || stop "No CI run for $(git rev-parse --short HEAD) yet. Was it pushed?"
  if [[ "$STATUS" != completed ]]; then
    info "CI for $(git rev-parse --short HEAD) is still running: waiting for it (gh run watch $RUN)..."
    gh run watch "$RUN" --interval 60 >/dev/null 2>&1 || true
    read -r RUN STATUS CONCL <<<"$(run_for "$HEAD_SHA")"
  fi
  [[ "$CONCL" == success ]] || stop "CI for $(git rev-parse --short HEAD) is $CONCL: gh run view $RUN"
  ok "CI passed for $(git rev-parse --short HEAD)"
  if [[ "$(browser_ran "$RUN")" != true ]]; then
    for sha in $(git rev-list --max-count=40 HEAD~1 2>/dev/null); do
      read -r R2 S2 C2 <<<"$(run_for "$sha")"
      [[ -n "${R2:-}" ]] || continue
      if [[ "$S2" != completed ]]; then
        info "CI for $(git rev-parse --short "$sha") is still running: waiting for it (gh run watch $R2)..."
        gh run watch "$R2" --interval 60 >/dev/null 2>&1 || true
        read -r R2 S2 C2 <<<"$(run_for "$sha")"
      fi
      [[ "$(browser_ran "$R2")" == true ]] || continue
      [[ "$C2" == success ]] || stop "The browser checks last ran on $(git rev-parse --short "$sha") and failed: gh run view $R2"
      ok "the browser checks last ran on $(git rev-parse --short "$sha") and passed"
      break
    done
  fi
fi

# ── 3. The search index ──────────────────────────────────────────────────────────────────────────────────────────────
step "The search index"
if [[ $REBUILD == auto ]]; then
  STATE=$( (cd backend && uv run --quiet python - <<'PY'
from app.knowledge import load_knowledge
from app.rag.chunking import build_chunks
from app.rag.vector import COLLECTION, _client, fingerprint
try:
    c = _client("data/index-image").get_collection(COLLECTION, embedding_function=None)
except Exception:
    print("missing"); raise SystemExit
print("same" if (c.metadata or {}).get("chunks") == fingerprint(build_chunks(load_knowledge())) else "changed")
PY
) 2>/dev/null || echo missing)
  [[ "$STATE" == same ]] && REBUILD=no || REBUILD=yes
fi
if [[ $REBUILD == yes ]]; then
  KEY=$(local_ OPENROUTER_API_KEY)
  [[ -n "$KEY" ]] || stop "The index needs rebuilding, and backend/.env has no OPENROUTER_API_KEY."
  info "rebuilding with OpenRouter's embedder: a few minutes, well under a cent"
  if [[ $DRY == no ]]; then
    rm -rf backend/data/index-image
    (cd backend && OPENROUTER_API_KEY="$KEY" EMBEDDER=openrouter EMBED_MODEL= INDEX_PATH=data/index-image \
       uv run --quiet python -m app.rag.build_index >/dev/null) || { KEY=; stop "The index build failed: see above."; }
  else info "would rebuild backend/data/index-image"; fi
  KEY=
  ok "index rebuilt"
else
  ok "the index is current"
fi

# ── 4. Build and upload ──────────────────────────────────────────────────────────────────────────────────────────────
PREV=$(saved TAG); TAG=v1
[[ "$PREV" =~ ^v([0-9]+)$ ]] && TAG="v$(( BASH_REMATCH[1] + 1 ))"
step "Build and upload $TAG"
LOG=$(mktemp)
do_ "docker build -t $IMAGE:$TAG ." docker build --build-arg EMBEDDER=openrouter -t "$IMAGE:$TAG" . >"$LOG" 2>&1 \
  || { tail -n 25 "$LOG"; rm -f "$LOG"; stop "The image didn't build (above)."; }
rm -f "$LOG"
grep -q "$REGION-docker.pkg.dev" "$HOME/.docker/config.json" 2>/dev/null \
  || do_ "gcloud auth configure-docker" gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet >/dev/null
do_ "docker push $IMAGE:$TAG" docker push -q "$IMAGE:$TAG" >/dev/null || stop "The upload failed: see above."
ok "$TAG built and uploaded"

# ── 5. Secrets and settings ──────────────────────────────────────────────────────────────────────────────────────────
# Each optional secret is added once, from backend/.env, and then left alone: an update never asks again. --rotate
# stores a new version from backend/.env. The deploy names every secret that exists, so a new one is attached and the
# rest stay as they are.
step "Secrets and settings"
UPDATE_SECRETS=()
for pair in telegram:telegram-bot-token:TELEGRAM_BOT_TOKEN tavily:tavily-api-key:TAVILY_API_KEY; do
  IFS=: read -r short secret var <<<"$pair"
  value=$(local_ "$var")
  if gcloud secrets describe "$secret" --project="$PROJECT_ID" >/dev/null 2>&1; then
    if [[ " ${ROTATE[*]:-} " == *" $short "* ]]; then
      [[ -n "$value" ]] || stop "--rotate $short: backend/.env has no $var."
      [[ $DRY == no ]] && { printf '%s' "$value" | gcloud secrets versions add "$secret" --project="$PROJECT_ID" --data-file=- >/dev/null; }
      ok "$secret: new version stored from backend/.env"
    else
      ok "$secret: kept"
    fi
    UPDATE_SECRETS+=("$var=$secret:latest")
  elif [[ -n "$value" ]]; then
    if [[ $DRY == no ]]; then
      printf '%s' "$value" | gcloud secrets create "$secret" --project="$PROJECT_ID" --replication-policy=automatic \
        --data-file=- >/dev/null
      gcloud secrets add-iam-policy-binding "$secret" --project="$PROJECT_ID" --member="serviceAccount:$SA" \
        --role=roles/secretmanager.secretAccessor >/dev/null
    fi
    ok "$secret: added from backend/.env"
    UPDATE_SECRETS+=("$var=$secret:latest")
  else
    info "$secret: not set up (no $var in backend/.env)"
  fi
  value=
done
CHAT=$(local_ TELEGRAM_CHAT_ID)
if [[ -n "$CHAT" ]] && ! grep -qE '^TELEGRAM_CHAT_ID:' "$ENV_YAML"; then
  [[ $DRY == no ]] && printf 'TELEGRAM_CHAT_ID: "%s"\n' "$CHAT" >> "$ENV_YAML"
  ok "TELEGRAM_CHAT_ID added to $ENV_YAML"
fi
SECRETS_FLAG=()
(( ${#UPDATE_SECRETS[@]} )) && SECRETS_FLAG=(--update-secrets="$(IFS=,; echo "${UPDATE_SECRETS[*]}")")

# ── 6. Deploy and check ──────────────────────────────────────────────────────────────────────────────────────────────
step "Deploy $TAG"
LOG=$(mktemp)
do_ "gcloud run deploy $SERVICE --image=$IMAGE:$TAG ${SECRETS_FLAG[*]:-}" \
  gcloud run deploy "$SERVICE" --image="$IMAGE:$TAG" --region="$REGION" --project="$PROJECT_ID" \
    --env-vars-file="$ENV_YAML" "${SECRETS_FLAG[@]}" --quiet >"$LOG" 2>&1 \
  || { tail -n 15 "$LOG"; rm -f "$LOG"; stop "The deploy failed (above). The old version keeps serving."; }
rm -f "$LOG"
if [[ $DRY == no ]]; then
  REV=$(gcloud run services describe "$SERVICE" --region="$REGION" --project="$PROJECT_ID" \
          --format='value(status.latestReadyRevisionName)' 2>/dev/null)
  healthy=no
  for _ in 1 2 3; do curl -fsS --max-time 120 -o /dev/null "$URL/api/health" && { healthy=yes; break; }; done
  if [[ $healthy == no ]]; then
    printf '\n  %s✗ %s is deployed (%s) but %s/api/health doesn'"'"'t answer.%s\n' "$R" "$TAG" "$REV" "$URL" "$N"
    info "the log: gcloud logging read 'resource.labels.service_name=\"$SERVICE\"' --limit=50 --freshness=1h"
    info "go back: gcloud run services update-traffic $SERVICE --region=$REGION --to-revisions=<previous revision>=100"
    exit 1
  fi
  save TAG "$TAG"; save DEPLOYED_COMMIT "$HEAD_SHA"
  ok "$TAG is live ($REV) and answers"
fi

# ── 7. Old images ────────────────────────────────────────────────────────────────────────────────────────────────────
# The newest $KEEP version tags stay (the live one among them), so there is always something to roll back to.
step "Old images"
OLD=$(gcloud artifacts docker tags list "$IMAGE" --project="$PROJECT_ID" --format='value(tag)' 2>/dev/null \
        | sed 's#.*/##' | grep -E '^v[0-9]+$' | sed 's/^v//' | sort -n | head -n -"$KEEP" | sed 's/^/v/' || true)
if [[ -z "$OLD" ]]; then
  ok "nothing to delete (keeping the newest $KEEP)"
else
  for t in $OLD; do
    do_ "delete image $t" gcloud artifacts docker images delete "$IMAGE:$t" --delete-tags --quiet >/dev/null 2>&1 \
      && ok "deleted $t" || info "couldn't delete $t; it can stay"
  done
fi

printf '\n%s%s✓ Done.%s %s\n\n' "$B" "$G" "$N" "$([[ $DRY == yes ]] && echo 'Dry run: nothing changed.' || echo "$URL runs $TAG.")"
