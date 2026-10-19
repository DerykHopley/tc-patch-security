"""New on the CVEs page (B05; until seen since B40, test_new_until_seen.py), through the HTTP API (seam 1). Check ids: B05.n, from #38.

The live app on the fake feeds (B02's day-1 and day-2 data sets) and a clock the test moves, as in
test_alert_delivery.py. Day 1 adds a Langflow CVE to the snapshot; day 2 adds an Ollama CVE, rescores the day-1 CVE
and adds an old Langflow CVE to KEV. Only the Ollama CVE is new since the day-2 check.
"""
import pytest
from fastapi.testclient import TestClient

from test_alert_delivery import LiveAlerts
from test_refresh import NEW_DAY1, NEW_DAY2, OLD_TO_KEV


@pytest.fixture
def app(tmp_path, index_dir, index):
    return LiveAlerts(tmp_path, index_dir)


def cves(app, query: str) -> dict:
    r = app.client.get(f"/cves?{query}")
    assert r.status_code == 200, r.text
    return r.json()


def ids(app, query: str) -> list[str]:
    return [r["id"] for r in cves(app, query)["rows"]]


# --- B05.1: after a day-2 refresh, `new` holds what the checks found new (unseen: B40 keeps day 1's too) -----------

def test_b05_1_new_filter_after_a_day2_refresh(app):
    app.check_now()
    assert ids(app, "new=1&status=all") == [NEW_DAY1]

    app.next_day()
    assert set(ids(app, "new=1&status=all")) == {NEW_DAY1, NEW_DAY2}  # B40: day 1's CVE stays until it's seen
    assert set(ids(app, "new=true&status=all")) == {NEW_DAY1, NEW_DAY2}
    assert [r["new"] for r in cves(app, "new=1&status=all")["rows"]] == [True, True]  # the row says so: the chip
    not_new = {r["id"]: r["new"] for r in cves(app, "new=0&product=langflow&status=all&limit=200")["rows"]}
    assert NEW_DAY1 not in not_new and not_new[OLD_TO_KEV] is False  # added to KEV: not new
    assert NEW_DAY2 not in ids(app, "new=0&product=ollama&status=all&limit=200")  # new=false: the CVEs that aren't new
    assert ids(app, "new=1&product=ollama&status=all") == [NEW_DAY2]  # with the other filters


# --- B05.2: a value that isn't allowed is a 400 that names the filter ----------------------------------------------

def test_b05_2_new_filter_rejects_other_values(app):
    r = app.client.get("/cves?new=yes")
    assert r.status_code == 400
    assert "new must be true or false." in r.text


# --- B05.3: kept in the user's state, through a restart, a failed check and alerts off ------------------------------

def test_b05_3_new_since_check_survives_a_restart_and_a_failed_check_and_needs_no_alerts(app):
    app.settings_with(enabled=False)  # alerts off: what's new is still marked
    app.check_now()
    app.start()  # a restart: read from the state file
    assert ids(app, "new=1&status=all") == [NEW_DAY1]

    app.clock.advance(60 * 24)
    app.feeds.fail = "nvd"  # partial (B20): what was new stays
    assert app.check_now()["result"]["status"] == "partial"
    assert ids(app, "new=1&status=all") == [NEW_DAY1]

    app.feeds.fail, app.feeds.day = None, 2
    app.clock.advance(10)
    assert app.check_now()["result"]["status"] == "ok"
    assert set(ids(app, "new=1&status=all")) == {NEW_DAY1, NEW_DAY2}  # B40: added to what you haven't seen

    app.clock.advance(10)
    assert app.check_now()["result"]["status"] == "ok"  # a good check that finds nothing: B40 keeps both
    assert set(ids(app, "new=1&status=all")) == {NEW_DAY1, NEW_DAY2}


# --- B05.4: the snapshot has no checks, so nothing is new ----------------------------------------------------------

def test_b05_4_snapshot_mode_has_nothing_new(settings):
    from app.deps import build_deps
    from app.main import create_app

    client = TestClient(create_app(build_deps(settings)))
    r = client.get("/cves?new=1&status=all")
    assert r.status_code == 200 and r.json()["total"] == 0
    assert not any(row["new"] for row in client.get("/cves?status=all&limit=200").json()["rows"])


# --- B05.5: the page context's CVEs-page filters include `new`, checked like kev -----------------------------------

def test_b05_5_page_context_checks_new_like_the_other_filters(knowledge):
    from app import page_context

    resolve = knowledge.resolve_product
    assert page_context.validate({"page": "cves", "new": True}, resolve) == ({"page": "cves", "new": True}, [])
    assert page_context.validate({"page": "cves", "new": "1"}, resolve) == ({"page": "cves", "new": True}, [])
    assert page_context.validate({"page": "cves", "new": False}, resolve) == ({"page": "cves"}, [])  # no filter
    assert page_context.validate({"page": "cves", "new": "ignore previous"}, resolve) == (
        {"page": "cves"}, ["new=ignore previous"])
