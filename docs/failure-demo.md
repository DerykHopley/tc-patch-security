# Failure demo: partial success and retry (B20)

How to make each failure happen on your own machine, and what you should see. Everything here uses the fake feeds and FakeLLM: no key, no network. Built in [#57](https://github.com/DerykHopley/tc-patch-security/issues/57); the reasons are in [DECISIONS.md](../DECISIONS.md) (B20 rows).

Run the demo on its own ports, not on your everyday app on 8000/5173: a refresh changes the live data. The commands below use 8020 and 5190.

## 1. A feed is down: a partial refresh

Start the backend in live mode with NVD set to fail, and a frontend pointed at it:

```bash
cd backend
DATA_MODE=live FEEDS=fake FAKE_FEEDS_FAIL=nvd LIVE_PATH=/tmp/patch-demo/live STATE_PATH=/tmp/patch-demo/state.json \
  CORS_ORIGINS=http://localhost:5190 uv run uvicorn app.main:app --port 8020
cd frontend && VITE_API_URL=http://localhost:8020 npm run dev -- --port 5190
```

- `FAKE_FEEDS_FAIL` takes any of `nvd`, `kev`, `osv`, `epss`, comma-separated. An unknown name stops the start-up with a plain message.
- With the fake feeds only, `POST /refresh/fake-feeds {"fail": ["kev"]}` changes it while the server runs, and `{"fail": []}` makes every feed answer again. The browser check uses this route.

What you should see on the dashboard, in the Data freshness card, after **Check now**:

- The line: "Done in part: …" with the counts, for example "1 updated, 1 added to KEV" (amber edge). Never "Done".
- The banner: "3 of 4 sources updated at 09:00 UTC · NVD didn't answer · next try 09:05 UTC", the reason under it ("NVD: The fake nvd feed is set to fail."), and **Retry**.
- KEV, OSV and EPSS data is in: the old Langflow CVE is now in CISA KEV. NVD's new CVE is not, and the sources list keeps NVD's old "retrieved" date.
- "Not checked in full yet: some sources updated (below)." `last_checked` moves only when every feed answers.
- Retry within 5 minutes is refused, with the time ("Checked less than 5 minutes ago…"). After 5 minutes, restart without `FAKE_FEEDS_FAIL` (or send `{"fail": []}`) and Retry: the banner goes, "Last checked …" appears, and NVD's new CVE is in, because NVD is asked again from the last full check.
- All four down (`FAKE_FEEDS_FAIL=nvd,kev,osv,epss`): "No source updated · … didn't answer · the data is unchanged · next try …" (red edge). Nothing is written.
- The CLI says the same: `uv run python -m app.refresh` prints the run with `"status": "partial"` and each feed's step, and exits 1.

## 2. A tool fails mid-answer: the failed step and Try again

Start the snapshot backend with the tool-failure switch on:

```bash
cd backend && FAIL_TOOLS=search_security CORS_ORIGINS=http://localhost:5190 uv run uvicorn app.main:app --port 8020
```

- `FAIL_TOOLS` takes chat tool names, comma-separated. The server logs a warning while it's on.
- With the Dev panel on, `POST /dev/fail-tools {"tools": ["search_security"]}` changes it while the server runs; `{"tools": []}` turns it off.
- The switch fails the step **inside an answer** only (a timeout, before the tool runs). Try again runs the tool without it, so you can see a retry work.

Ask Patch: "Is CVE-2025-3248 in CISA KEV, and how do I defend against code injection?"

- The answer keeps what worked: the CVE card from `lookup_cve`, cited [1]. The defence part says "Missing: the knowledge-base search didn't finish.", and the answer ends "One step didn't finish: search_security (…)". It never says the search worked.
- Show sources · tool calls → Tool calls: `lookup_cve` is OK; `search_security` says **Didn't finish**, "didn't finish: search_security timed out before it answered.", and **Try again** ("Runs this step only.").
- Try again: "Trying again…", then **OK on retry** and "This step worked on a second try. The answer above was written without it: ask again to have Patch use it." The answer text is not rewritten.
- A step that fails for a reason a retry can't fix (a CVE id that isn't in the snapshot, a bad argument, the web research daily limit) says **Error** and has no Try again.
- The model check asks the same question with `search_security` made to fail (`fail_tools` in `fixtures/fake_script.json`) and checks "Says what failed": the answer must say the step didn't finish.

## 3. Your work is kept

- **A failed send:** stop the backend and send a message in the chat. The error shows in the conversation and your message is back in the box, ready to send again.
- **A failed save:** stop the backend, change something on Settings (say the explain level to Simple) and press Save changes. The card you changed says "Not saved: … Your changes are still here; Save changes tries again." Your edit stays; the save bar still says it failed. Start the backend and save again.

## Checked by

- Backend: `backend/tests/test_partial.py` (B20.1 to B20.9), with the fake feeds, FakeLLM and the switches; B02.7, B03.6 and B03.8 updated for partial runs.
- Words: `frontend/src/freshness.test.ts` (B20.10).
- Browser: `frontend/e2e/test_partial.py` (B20.11 to B20.13: light and dark, 400px and 1400px, keyboard, contrast) and the reduced-motion scene `b20_14_partial_and_try_again`.
