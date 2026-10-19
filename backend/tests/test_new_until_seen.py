""""New" stays until you've seen it, through the HTTP API (seam 1). Check ids: B40.n, from #92.

The live app on the fake feeds, as in test_new_since_check.py: day 1 adds NEW_DAY1 (Langflow), day 2 adds NEW_DAY2
(Ollama), both on the default watchlist. A CVE leaves "New" when its page is opened (`POST /cves/<id>/seen`, sent by
the CVE page) or on "Mark all as seen" (`POST /cves/seen`); a check that finds nothing leaves it as it was.
"""
import json

import pytest

from test_alert_delivery import LiveAlerts
from test_per_user import LiveUsers
from test_refresh import NEW_DAY1, NEW_DAY2


@pytest.fixture
def app(tmp_path, index_dir, index):
    return LiveAlerts(tmp_path, index_dir)


def new_ids(client) -> set[str]:
    r = client.get("/cves", params={"new": "1", "status": "all", "limit": 200})
    assert r.status_code == 200, r.text
    return {row["id"] for row in r.json()["rows"]}


# --- B40.1: a check that finds nothing leaves "New" as it was ------------------------------------------------------

def test_b40_1_new_stays_through_checks_that_find_nothing(app):
    app.check_now()
    assert new_ids(app.client) == {NEW_DAY1}
    app.next_day()
    assert new_ids(app.client) == {NEW_DAY1, NEW_DAY2}  # day 1's CVE is still unseen
    app.clock.advance(10)
    assert app.check_now()["result"]["status"] == "ok"  # a good check that finds nothing
    assert new_ids(app.client) == {NEW_DAY1, NEW_DAY2}
    assert app.client.get("/cves").json()["new_total"] == 2  # for "Mark all as seen": every new row, any filter


# --- B40.2: opening a CVE's page marks only that CVE seen; reading it doesn't -----------------------------------------

def test_b40_2_opening_a_cve_page_removes_only_that_cve(app):
    app.check_now()
    app.next_day()
    assert app.client.get(f"/cves/{NEW_DAY1}").json()["row"]["new"] is True  # a read changes nothing
    assert new_ids(app.client) == {NEW_DAY1, NEW_DAY2}

    r = app.client.post(f"/cves/{NEW_DAY1.lower()}/seen")
    assert r.status_code == 200 and r.json() == {"id": NEW_DAY1, "new_total": 1}
    assert new_ids(app.client) == {NEW_DAY2}
    assert app.client.post(f"/cves/{NEW_DAY1}/seen").status_code == 200  # again: nothing to do, still fine
    assert app.client.post("/cves/CVE-1999-0001/seen").status_code == 404

    app.start()  # kept in the state file, through a restart
    assert new_ids(app.client) == {NEW_DAY2}


# --- B40.3: "Mark all as seen" empties the list; the next check is still not a first check -------------------------

def test_b40_3_mark_all_as_seen_empties_new_and_later_checks_add_again(app):
    app.check_now()
    r = app.client.post("/cves/seen")
    assert r.status_code == 200 and r.json() == {"new_total": 0}
    assert new_ids(app.client) == set()
    assert app.deps.state.checked_before()  # B34: seen marks don't make the next check a first check

    app.next_day()
    assert new_ids(app.client) == {NEW_DAY2}  # what a later check finds is new again


# --- B40.4: seen marks are each user's own -------------------------------------------------------------------------

def test_b40_4_another_users_new_list_is_unaffected(tmp_path, index_dir, index):
    app = LiveUsers(tmp_path, index_dir)
    alice, bob = app("alice"), app("bob")
    for c in (alice, bob):
        c.put("/watchlist", json={"products": ["langflow", "ollama"]})
    app.live.check_now()
    app.live.next_day()

    alice.post(f"/cves/{NEW_DAY1}/seen")
    assert new_ids(alice) == {NEW_DAY2} and new_ids(bob) == {NEW_DAY1, NEW_DAY2}
    alice.post("/cves/seen")
    assert new_ids(alice) == set() and new_ids(bob) == {NEW_DAY1, NEW_DAY2}


# --- B40.5: a state file of today's shape (B05's `new_since_check`) loads and moves over -----------------------------

def test_b40_5_a_state_saved_before_b40_loads_with_its_new_cves_unseen(app):
    app.check_now()
    app.next_day()  # the live data holds both CVEs; then the state file as B05 left it
    old = json.loads(app.settings.state_path.read_text())
    old.pop("new_cves", None)
    old["new_since_check"] = {"at": "2026-10-14T09:00:00Z", "cves": [NEW_DAY1], "pending": [NEW_DAY2]}
    app.settings.state_path.write_text(json.dumps(old))
    app.start()

    assert new_ids(app.client) == {NEW_DAY1, NEW_DAY2}  # the last check's and the partial runs' since
    assert app.deps.state.checked_before()  # still not a first check (B34)
    app.client.post(f"/cves/{NEW_DAY2}/seen")
    saved = json.loads(app.settings.state_path.read_text())
    assert "new_since_check" not in saved and saved["new_cves"]["cves"] == [NEW_DAY1]
    assert new_ids(app.client) == {NEW_DAY1}


# --- B43.2 (#93): the dashboard counts the new CVEs you haven't seen, for "See the N new CVEs →" -----------------

def new_unseen(client, query: str = "") -> int:
    return client.get(f"/dashboard{query}").json()["kpis"]["new_unseen"]


def test_b43_2_the_dashboard_counts_new_cves_not_seen_within_its_product_filter(app):
    assert new_unseen(app.client) == 0  # before any check nothing is new
    app.check_now()
    app.next_day()
    assert new_unseen(app.client) == 2
    assert new_unseen(app.client, "?product=ollama") == 1  # the dashboard's filter narrows it, as it does the tiles
    app.client.patch(f"/cves/{NEW_DAY2}", json={"status": "fixed"})  # a closed CVE you haven't opened is still new
    assert new_unseen(app.client) == 2
    app.client.post(f"/cves/{NEW_DAY1}/seen")
    assert new_unseen(app.client) == 1
    app.client.post("/cves/seen")
    assert new_unseen(app.client) == 0
