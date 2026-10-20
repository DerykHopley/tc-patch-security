# Deploy Patch to Google Cloud Run

How to put Patch on a public URL, open only to the people the owner approves (B38), at no cost at this use. Written for the owner's first deploy (B14, [#45](https://github.com/DerykHopley/tc-patch-security/issues/45)) and any redeploy after it. Built in B13 ([#44](https://github.com/DerykHopley/tc-patch-security/issues/44)); why it's built this way: [DECISIONS.md](./DECISIONS.md) (2026-10-14 "Where it runs", the B13 rows).

> **Easiest: run `scripts/deploy-wizard.sh`** from the repo root. It walks through every step below, one at a time: it explains each, shows the command and asks before running it, skips what already exists (so you can stop and re-run), reuses the Clerk keys, user id and keys from `backend/.env`, and never writes a secret to a file. Its plain answers (project id, billing account, image tag, time zone) are kept in `deploy/cloudrun/wizard.env` (git-ignored). Running it inside Claude Code as `! scripts/deploy-wizard.sh` puts its output in the chat. The steps below are the same commands by hand.

> **Checked on the first deploy (2026-10-19):** the owner ran these steps through `scripts/deploy-wizard.sh`, and the live app at https://patch-976248543439.europe-west1.run.app runs from them ([STATUS.md](./STATUS.md#the-live-app)). The steps that failed were fixed here (the budget's currency, the time zone, the scheduler's retries). The commands typed by hand, outside the wizard, are *unverified* where a step doesn't say otherwise. The app's side is also tested against a fake bucket (`backend/tests/test_deploy.py`) and by the container smoke test.

## What runs where

- **Region.** The commands use `us-central1`, the region with free Cloud Storage. **Patch itself runs in `europe-west1` (Belgium)** since 2026-10-19, for EU data and a shorter way from Germany: Cloud Run's free allowance is a discount at Tier 1 prices wherever it runs, and europe-west1 is Tier 1 (Frankfurt and Berlin are Tier 2: the same allowance covers less), while Cloud Storage's always-free 5 GB is US-only, so the EU bucket costs a fraction of a cent at under 10 MB ([pricing](https://cloud.google.com/run/pricing), [locations](https://docs.cloud.google.com/run/docs/locations)). The wizard and `scripts/update-deploy.sh` take the region and bucket from `deploy/cloudrun/wizard.env` (`REGION=`, `BUCKET=`). Moving later means a new bucket (copy with `gcloud storage rsync -r`), registry, service and job, then deleting the old ones: a bucket can't change region.
- **One container on Cloud Run** (`us-central1` in the commands below; `europe-west1` for the owner's): the API under `/api` and the built frontend, with the search index built into the image ([README: In a container](./README.md#in-a-container)). Minimum 0 instances (it sleeps when nobody uses it), **maximum 1**: the rate limits and the refresh lock are in memory, so a second instance would double them.
- **Cloud Storage** (one bucket, `us-central1`): each user's state is one object, `users/<clerk user id>.json`; the live data and the refresh log are under `live/`; the finished model-check and retrieval runs (the Dev page's Past runs, Compare and report) are under `evals/` (B58). Each write carries the object's generation, so two writers can't lose each other's change (B09). The instance's disk is memory and goes when it stops; the bucket stays.
- **Secret Manager**: the OpenRouter key, the scheduler secret, and the optional Tavily key and ntfy topic. Cloud Run passes them in as environment variables. They are never in the image, the repo or `env.yaml`.
- **Cloud Scheduler**: one job calls `POST /api/refresh/scheduled` every hour with the scheduler secret in the `X-Scheduler-Secret` header. The route runs the refresh only when your Settings schedule (every 1 to 24 hours) is due and not paused, exactly like the local systemd timer.
- **A cold start catches up:** the image's index is the snapshot's. On start, the server reads the live version from the bucket and embeds only the CVEs that differ (log line `Search index caught up with the live data: N chunks embedded in T s`).
- **The Dev page** is on (`DEV_PANEL: "true"` in `env.yaml`, since B45 roles, 2026-10-19). Who sees what is set by role, not by the switch: a Viewer (everyone you approve, by default) has no Dev page at all; Trusted sees it read-only with the playground; a Reviewer changes their own copy only; only the owner changes the shared settings and runs the model check. On, you can change the model without a redeploy. `"false"` still hides it from everyone, the owner included.
- **Clerk** (development instance, [#65](https://github.com/DerykHopley/tc-patch-security/issues/65)) signs users in. Every route except `/health` and the scheduled route needs a signed-in user.

## What it costs

Expected: **$0 a month**, or a few cents for image storage. Set the budget alert in step 1 so a surprise shows up early.

| Service | Free each month | Patch's use | Source |
|---|---|---|---|
| Cloud Run | 2M requests, 360,000 GB-s, 180,000 vCPU-s | 1 GiB, 1 vCPU, billed only while serving. 720 scheduler ticks (most skip in under a second, plus a cold start) and the refresh runs: roughly 20,000 vCPU-s, about a tenth of the free amount | free tier *checked* (docs/SOURCE-CHECKS.md); the use is an *unverified* estimate |
| Cloud Scheduler | 3 jobs per billing account | 1 job | *checked* |
| Cloud Storage | 5 GB in us-central1 | under 10 MB: about 1 MB per live version (2 kept), well under 1 MB per user | *checked*; sizes from `backend/fixtures/` |
| Cloud Storage operations | 5,000 class A, 50,000 class B (from memory) | each API request reads the live version and the user's state; each refresh writes about 10 objects | *unverified* |
| Secret Manager | 6 active secret versions, 10,000 accesses (from memory) | 2 to 4 secrets, read at each instance start | *unverified* |
| Artifact Registry | 0.5 GB storage (from memory) | one image: 1.7 GB uncompressed (`frontend/e2e/container.sh` prints it, 2026-10-16), less compressed in the registry. At about $0.10 per GB-month over the free amount, at most about 12 cents a month. Delete old tags (step 9) | *unverified* |
| OpenRouter | none (pay per use) | capped by the key's spending cap | *checked* (SOURCE-CHECKS) |
| Tavily | 1,000 credits | at most 30 searches a day (B08's cap) | *checked* |
| Clerk | development instance: 100 users | a few approved users (open sign-up counts every account made, approved or not) | *checked* |

## Before you start

- The Google Cloud CLI (`gcloud`), signed in: `gcloud auth login`. On a system with a read-only `/usr` (Fedora Atomic, Silverblue), install it in your home folder with Google's script (`curl https://sdk.cloud.google.com | bash`, [Google's guide](https://cloud.google.com/sdk/docs/install#linux)), then open a new terminal. Docker, as for `frontend/e2e/container.sh`.
- A billing account in Google Cloud (free-tier use still needs one linked).
- The Clerk instance and its keys from [#65](https://github.com/DerykHopley/tc-patch-security/issues/65): the publishable key, the JWT public key (PEM) and your user id, plus the **secret key** (B38/B48: the Requests card's names and emails, and the name in an access-request alert; without it, user ids). The development instance is fine: a production instance needs a domain you own, which `run.app` isn't.
- An OpenRouter key **with a spending cap** set in OpenRouter's settings. Optional: a Tavily key (web research), an ntfy topic (alerts on your phone).
- A checkout of the branch to deploy (spec B is on `spec-b` until it's merged), with `uv sync` done in `backend/`.

Run every command from the repo root, in one shell: the variables from step 0 are used throughout.

## 0. Names

```bash
export PROJECT_ID=patch-<something-unique>     # 6-30 characters: lower-case letters, digits, hyphens
export REGION=us-central1                      # free Cloud Storage; Cloud Run and Scheduler run here too
export BUCKET=$PROJECT_ID-state
export SERVICE=patch
export SA=patch-run@$PROJECT_ID.iam.gserviceaccount.com
export IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/patch/patch
```

## 1. Project, billing and a budget alert

```bash
gcloud projects create $PROJECT_ID --name="Patch"
gcloud config set project $PROJECT_ID
gcloud billing accounts list                                       # copy your ACCOUNT_ID
gcloud billing projects link $PROJECT_ID --billing-account=<ACCOUNT_ID>
gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com \
  cloudscheduler.googleapis.com storage.googleapis.com billingbudgets.googleapis.com
gcloud billing budgets create --billing-account=<ACCOUNT_ID> --display-name="Patch" --budget-amount=1USD \
  --threshold-rule=percent=0.5 --threshold-rule=percent=1.0
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
```

- The budget emails the billing account's admins at 50 cents and at $1. It alerts; it doesn't stop anything.
- The budget's currency must be the billing account's own: an account opened in Germany bills in EUR, and `1USD` then fails with `INVALID_ARGUMENT` (*checked* on the owner's first deploy, 2026-10-19: `1USD` failed, `1EUR` worked). Use `--budget-amount=1EUR` there; `gcloud billing accounts describe <ACCOUNT_ID> --format='value(currencyCode)'` says which.
- If `budgets create` fails, set the same budget in the console: Billing → Budgets & alerts.

## 2. The service account

Cloud Run runs as its own account, allowed only the bucket and the secrets (not the project's broad default account).

```bash
gcloud iam service-accounts create patch-run --display-name="Patch on Cloud Run"
```

## 3. The bucket

```bash
gcloud storage buckets create gs://$BUCKET --location=$REGION --uniform-bucket-level-access \
  --public-access-prevention
gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
  --member=serviceAccount:$SA --role=roles/storage.objectUser
```

- `roles/storage.objectUser` reads, writes, lists and deletes objects in this bucket only.
- The app creates everything in it on its first start (the live data starts as a copy of the snapshot).

## 4. The secrets

Each value is typed at a hidden prompt, so it never lands in your shell history.

```bash
add_secret() {   # add_secret <name>: create it from a hidden prompt, and let the service read it
  read -rsp "$1: " value; echo
  printf '%s' "$value" | gcloud secrets create "$1" --replication-policy=automatic --data-file=-
  unset value
  gcloud secrets add-iam-policy-binding "$1" --member=serviceAccount:$SA --role=roles/secretmanager.secretAccessor
}
add_secret openrouter-api-key          # sk-or-...
openssl rand -hex 32 | tr -d '\n' | gcloud secrets create scheduler-secret --replication-policy=automatic --data-file=-
gcloud secrets add-iam-policy-binding scheduler-secret --member=serviceAccount:$SA \
  --role=roles/secretmanager.secretAccessor
add_secret clerk-secret-key            # sk_test_... (names on the Requests card and in request alerts)
add_secret tavily-api-key              # optional: tvly-... (web research)
add_secret ntfy-topic                  # optional: your ntfy topic (alerts on your phone)
add_secret ntfy-token                  # optional: only if your ntfy topic needs an access token
add_secret telegram-bot-token          # optional, recommended: from @BotFather (README "Alerts"); phone alerts from Cloud Run
```

- Skip the optional ones you don't use, and leave their line out of `--set-secrets` in step 6.
- **Telegram, not ntfy, for phone alerts from Cloud Run** (B57, #102): ntfy.sh counts its daily quota per IP address and Cloud Run's outgoing addresses are shared, so its sends fail by the afternoon (docs/SOURCE-CHECKS.md, "ntfy.sh from Cloud Run"). Telegram limits per bot. Its chat id isn't a secret: it goes in `env.yaml` (step 6), or on Settings → Delivery → Telegram → Find my chat id.
- To change a secret later: `printf '%s' "<new value>" | gcloud secrets versions add <name> --data-file=-`, then redeploy (step 9) so a new instance reads it.

## 5. Build and push the image

The image carries the search index. Build it with OpenRouter's embedder (`text-embedding-3-small`, well under a cent), so Patch searches with real embeddings; queries and refreshes then embed through the same key.

```bash
read -rsp "OpenRouter key: " OPENROUTER_API_KEY; echo; export OPENROUTER_API_KEY
rm -rf backend/data/index-image
(cd backend && EMBEDDER=openrouter EMBED_MODEL= INDEX_PATH=data/index-image uv run python -m app.rag.build_index)
unset OPENROUTER_API_KEY
docker build --build-arg EMBEDDER=openrouter -t $IMAGE:v1 .

gcloud artifacts repositories create patch --repository-format=docker --location=$REGION
gcloud auth configure-docker $REGION-docker.pkg.dev
docker push $IMAGE:v1
```

- No key goes into the image: the index records only the embedder's name. `frontend/e2e/container.sh` checks that for the hash image.
- *Unverified:* only the hash index has run in the image so far (README). The free alternative: build the hash index (`EMBEDDER=hash`) and leave out `--build-arg`. Search is then word matching only.

## 6. Deploy the service

The service's address is known before the first deploy: `https://$SERVICE-$PROJECT_NUMBER.$REGION.run.app`. Sign-in needs it at start-up.

```bash
echo https://$SERVICE-$PROJECT_NUMBER.$REGION.run.app       # the address
cp deploy/cloudrun/env.example.yaml deploy/cloudrun/env.yaml   # git-ignored
```

Fill in every `<...>` in `deploy/cloudrun/env.yaml`: the bucket name, the Clerk keys and your user id, the address three times, your time zone, and (optional) `TELEGRAM_CHAT_ID`. Then:

```bash
gcloud run deploy $SERVICE --image=$IMAGE:v1 --region=$REGION --service-account=$SA \
  --allow-unauthenticated --min-instances=0 --max-instances=1 --memory=1Gi --cpu=1 --cpu-boost --timeout=900 \
  --env-vars-file=deploy/cloudrun/env.yaml \
  --set-secrets=OPENROUTER_API_KEY=openrouter-api-key:latest,SCHEDULER_SECRET=scheduler-secret:latest,CLERK_SECRET_KEY=clerk-secret-key:latest,TAVILY_API_KEY=tavily-api-key:latest,NTFY_TOPIC=ntfy-topic:latest,NTFY_TOKEN=ntfy-token:latest,TELEGRAM_BOT_TOKEN=telegram-bot-token:latest
gcloud run services describe $SERVICE --region=$REGION --format='value(status.url)'
```

- List only the secrets you created in step 4: a missing one fails the deploy.
- Check it answers: `curl -fsS https://$SERVICE-$PROJECT_NUMBER.$REGION.run.app/api/health` (the first answer starts the container, 10-30 s). *Unverified:* that Cloud Run serves this `patch-<project number>` address; `describe` may print an older-style address, which works too. If yours doesn't answer, use the `describe` one in `env.yaml`.
- `--allow-unauthenticated` lets the public reach the app; Clerk sign-in then guards every route.
- `--max-instances=1` is required, not a cost setting (see "What runs where").
- If the `describe` address differs from the one in `env.yaml`, put it in `AUTH_ALLOWED_ORIGINS`, `APP_URL` and `CORS_ORIGINS` (comma-separate both addresses in the first) and run the same deploy again.
- A bad setting stops the start-up with a plain message: `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="patch"' --limit=50 --freshness=1h`.
- *Unverified:* that 1 GiB is enough. If the log says the memory limit was exceeded, deploy again with `--memory=2Gi` (still inside the free tier at this use).

## 7. Clerk: allow the address

1. In `deploy/cloudrun/env.yaml`, `AUTH_ALLOWED_ORIGINS` is the address (done in step 6): the app refuses a session token made on any other page.
2. Open the address. You should see Patch's landing page (B42). Press Sign in and sign in: "Opening Patch", then the dashboard.
3. *Unverified:* whether a Clerk development instance needs the address added on its side (docs/SOURCE-CHECKS.md, Clerk: "likely yes, it works"). If the sign-in form refuses the origin, add it with Clerk's Backend API (the secret key is used here only, never by the app):

   ```bash
   read -rsp "Clerk secret key: " CLERK_SECRET_KEY; echo
   curl -sS -X PATCH https://api.clerk.com/v1/instance -H "Authorization: Bearer $CLERK_SECRET_KEY" \
     -H "Content-Type: application/json" -d "{\"allowed_origins\": [\"https://$SERVICE-$PROJECT_NUMBER.$REGION.run.app\"]}"
   unset CLERK_SECRET_KEY
   ```
4. **Sign-up is open; you approve each account** (B38, README "Sign-in"): set Clerk's sign-up mode to Public and turn on "Challenge suspicious sign-ups" (Clerk dashboard), as for the local app. Names on the Requests card come from the `clerk-secret-key` secret (step 4). *Checked* locally on 2026-10-19 against the dev instance; *unverified* on Google Cloud.

## 8. The hourly schedule

```bash
gcloud scheduler jobs create http patch-refresh --location=$REGION --schedule="0 * * * *" --time-zone=UTC \
  --uri="https://$SERVICE-$PROJECT_NUMBER.$REGION.run.app/api/refresh/scheduled" --http-method=POST \
  --headers="X-Scheduler-Secret=$(gcloud secrets versions access latest --secret=scheduler-secret)" \
  --attempt-deadline=600s --max-retry-attempts=2 --min-backoff=120s --max-backoff=120s
gcloud scheduler jobs run patch-refresh --location=$REGION     # one tick now, to check
```

- The tick answers 200 with the run's result, or `{"ran": false, "skipped": "not_due"}` / `"paused"`. A run where no feed answered is a 502, so it shows as a failed attempt in the job's log. A missing or wrong secret is a 401 and runs nothing.
- **Daily instead:** `--schedule="0 8 * * *" --time-zone="Europe/Berlin"` (the owner's choice on the first deploy, 2026-10-19). Then set Settings → schedule to every 24 hours, so the app's "next check" is honest. New CVEs and KEV alerts then arrive up to a day late; Check now still works.
- How often the refresh really runs is set in the app: Settings → schedule (every 1, 3, 6, 12 or 24 hours, default 6), or Pause. The job only knocks every hour.
- **Two retries, 2 minutes apart** (added 2026-10-20). The app scales to zero. On 2026-10-20 the 08:00 tick found no instance, got a 500 and wasn't retried, so that day had no refresh (*checked* in the logs; the instance took about 90 s to start). Retries start by 08:04, inside the schedule's 10-minute slack, so the next day's tick is still due. A doubling backoff would push the last retry past it. A retry after a finished run is a harmless `not_due` skip. For an older job: `gcloud scheduler jobs update http patch-refresh --location=$REGION --max-retry-attempts=2 --min-backoff=120s --max-backoff=120s`.
- The secret is stored in the job's settings, readable by whoever can see the project's scheduler jobs (only you). If you change the secret, update the job: `gcloud scheduler jobs update http patch-refresh --location=$REGION --update-headers=X-Scheduler-Secret=<new>`.

## 9. Check it, redeploy, roll back, remove

The checks for #45:

1. Sign in, set your watchlist. In a private window, a second account asks for access (B38): you get the alert (if Telegram or ntfy is set), approve it on Settings → Requests with a role (B45), and they see the default watchlist, not yours, and only their "Yours" part of Settings (B48).
2. Dashboard → **Check now**: it runs and says what it found.
3. Ask Patch "Who's talking about CVE-2025-3248?" (needs the Tavily secret): an answer with web sources.
4. After the next hourly tick: `gcloud scheduler jobs describe patch-refresh --location=$REGION` (last attempt) and Settings → Refresh runs (trigger "schedule").
5. Cold-start time: after 15 idle minutes, open the app and time the first page. The log has the start-up and the `Search index caught up` line.
6. After a week: Billing → Reports, filtered to the project. Expected $0.

**Update after a change: `scripts/update-deploy.sh`.** It shows what's live and what's new, suggests the next version (`v2`, `v3`…), rebuilds the search index only when the snapshot or the chunking changed (it compares the index's fingerprint), builds, uploads and deploys the new tag, checks it answers, and offers to delete the old image. It reads the first deploy's `deploy/cloudrun/wizard.env` and `env.yaml`; the secrets stay as they are. It also offers Telegram (B57): it stores the bot token as the `telegram-bot-token` secret (from `backend/.env` or typed, hidden), lets the service read it, adds it to the deploy (`--update-secrets`, so the other secrets stay), and puts `TELEGRAM_CHAT_ID` from `backend/.env` in `env.yaml` if you like. Once added, every later update keeps both. By hand: step 4's `add_secret telegram-bot-token`, then `gcloud run deploy ... --update-secrets=TELEGRAM_BOT_TOKEN=telegram-bot-token:latest`. By hand: build and push a new tag (step 5 with `v2`), then `gcloud run deploy $SERVICE --image=$IMAGE:v2 --region=$REGION` (the other settings stay). Delete old tags to keep storage free: `gcloud artifacts docker images delete $IMAGE:v1`.

Roll back: `gcloud run revisions list --service=$SERVICE --region=$REGION`, then `gcloud run services update-traffic $SERVICE --region=$REGION --to-revisions=<revision>=100`.

Remove everything (stops all cost; deletes the bucket's data): `gcloud projects delete $PROJECT_ID`.

## Known limits

- **One instance.** During a deploy, the old and new revision can run side by side for a moment. The bucket's generation checks keep users' state safe; the in-memory limits and the refresh lock are per instance for that moment.
- **Each request reads the bucket** (the live version and the user's state), a few tens of milliseconds each (*unverified*). Fine at this use; a cache would be the next step if it isn't.
- **The development instance** shows Clerk's banner and allows 100 users. A production instance needs a domain (DECISIONS.md, "Auth").
