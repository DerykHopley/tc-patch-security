"""Priority, policy and due dates through the HTTP API and the chat tools (seam 1). Check ids: A16.n, from #18.

The rules themselves are table-tested in test_priority.py; these check they're wired through: the policy and the
threshold in Settings, the CVEs table's fields and order, the KEV tile, lookup_cve and the test alert.
"""
import json

import pytest

from app.priority import LEVELS


def _row(client, cve_id, product):
    rows = client.get(f"/cves?status=all&product={product}&limit=200").json()["rows"]
    return next(r for r in rows if r["id"] == cve_id)


def _policy(client, **changes):
    body = client.get("/settings").json()["settings"]
    body["policy"] |= changes
    return client.put("/settings", json=body)


# --- A16.4: the policy and the threshold are settings, validated -------------------------------------------------

def test_a16_4_policy_and_threshold_defaults(client):
    s = client.get("/settings").json()["settings"]
    assert s["policy"] == {"urgent_days": 7, "high_days": 30, "normal_days": 90, "low_days": 180,
                           "adopt_kev_deadline": True}
    assert s["priority"] == {"epss_percentile": 90}


@pytest.mark.parametrize("part,bad", [
    ("policy", {"urgent_days": 0}), ("policy", {"low_days": 731}), ("policy", {"high_days": "soon"}),
    ("policy", {"urgent_days": 40}),  # more days than high (30): urgent must not get longer than high
    ("policy", {"adopt_kev_deadline": "maybe"}), ("priority", {"epss_percentile": 100}),
    ("priority", {"epss_percentile": 0.9}),
])
def test_a16_4_bad_policy_values_are_400(client, part, bad):
    body = client.get("/settings").json()["settings"]
    body[part] |= bad
    r = client.put("/settings", json=body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_request"


def test_a16_4_a_state_file_without_a_policy_loads_with_defaults(settings, client):
    settings.state_path.write_text(json.dumps({"watchlist": ["langflow"], "statuses": {},
                                               "settings": {"alerts": {"kev": False}}}))
    assert client.get("/settings").json()["settings"]["policy"]["normal_days"] == 90
    assert _row(client, "CVE-2025-3248", "langflow")["priority"] == "urgent"


# --- A16.5: every CVE row has its priority, reasons, due date and overdue; the table sorts by priority -----------

def test_a16_5_rows_carry_priority_reasons_due_date_overdue_and_the_kev_deadline(client):
    row = _row(client, "CVE-2025-3248", "langflow")  # in KEV, critical; KEV deadline 2025-05-26
    assert (row["priority"], row["priority_reasons"], row["alert_priority"]) == ("urgent", ["in KEV", "EPSS 99th percentile"], 5)
    assert (row["due_date"], row["due_from"], row["overdue"]) == ("2025-05-26", "KEV deadline", True)
    assert row["kev_deadline"] == "2025-05-26"


def test_a16_5_the_kev_deadline_stays_a_fact_when_the_policy_doesnt_adopt_it(client):
    assert _policy(client, adopt_kev_deadline=False).status_code == 200
    row = _row(client, "CVE-2025-3248", "langflow")  # added to KEV 2025-05-05
    assert (row["due_date"], row["due_from"]) == ("2025-05-12", "added to KEV + 7 days")
    assert row["kev_deadline"] == "2025-05-26"


def test_a16_5_policy_days_change_due_dates(client):
    before = _row(client, "CVE-2026-21445", "langflow")  # high severity, published 2026-01-02
    assert (before["priority"], before["due_date"]) == ("normal", "2026-04-02")
    _policy(client, normal_days=120, low_days=200)
    after = _row(client, "CVE-2026-21445", "langflow")
    assert (after["due_date"], after["due_from"]) == ("2026-05-02", "published + 120 days")


def test_a16_5_sorted_by_priority_then_due_date(client):
    rows = client.get("/cves?limit=200").json()["rows"]
    keys = [(LEVELS.index(r["priority"]), r["due_date"]) for r in rows]
    assert keys == sorted(keys)
    assert rows[0]["priority"] == "urgent" and {r["priority"] for r in rows} >= {"urgent", "high", "normal"}


def test_a16_5_internet_facing_and_the_verdict_move_a_cve(client):
    cve, product = "CVE-2026-21445", "langflow"  # high severity, EPSS 98th percentile, fixed in 1.7.1; no KEV
    assert _row(client, cve, product)["priority"] == "normal"
    client.put("/watchlist", json={"products": ["langchain", "litellm", "ollama", "open-webui",
                                                {"product": "langflow", "internet_facing": True}]})
    row = _row(client, cve, product)
    assert row["priority"] == "high" and row["priority_reasons"] == ["EPSS 98th percentile", "internet-facing"]
    client.put("/watchlist", json={"products": [{"product": "langflow", "internet_facing": True,
                                                 "version": "1.7.1"}]})  # the fixed version: not affected
    row = _row(client, cve, product)
    assert row["verdict"] == "not_affected" and row["priority"] == "normal"
    assert row["priority_reasons"][-1] == "not affected: one level lower"


def test_a16_5_the_threshold_setting_changes_row_2(client):
    client.put("/watchlist", json={"products": [{"product": "langflow", "internet_facing": True}]})
    assert _row(client, "CVE-2026-21445", "langflow")["priority"] == "high"  # EPSS 98th percentile
    body = client.get("/settings").json()["settings"]
    body["priority"]["epss_percentile"] = 99
    assert client.put("/settings", json=body).status_code == 200
    assert _row(client, "CVE-2026-21445", "langflow")["priority"] == "normal"


def test_a16_5_marked_fixed_is_never_overdue(client):
    client.patch("/cves/CVE-2025-3248", json={"status": "fixed"})
    assert _row(client, "CVE-2025-3248", "langflow")["overdue"] is False


# --- A16.6: the KEV tile says overdue against the due date --------------------------------------------------------

def test_a16_6_kev_tile_next_due_is_the_earliest_due_date(client):
    k = client.get("/dashboard").json()["kpis"]
    assert k["kev_next_due"] == {"cve": "CVE-2025-3248", "due": "2025-05-26", "overdue": True,
                                 "no_fix": False}
    assert k["kev_overdue"] == 8  # every KEV deadline is before 2026-10-13; CVE-2026-0770 has no fix yet (A16b)


def test_a16_6_kev_tile_follows_the_policy(client):
    _policy(client, adopt_kev_deadline=False)
    k = client.get("/dashboard").json()["kpis"]
    assert k["kev_next_due"] == {"cve": "CVE-2025-3248", "due": "2025-05-12", "overdue": True,
                                 "no_fix": False}


def test_a16_6_overdue_count_on_the_tiles(client):
    k = client.get("/dashboard").json()["kpis"]
    rows = [r for offset in (0, 200, 400, 600) for r in client.get(f"/cves?limit=200&offset={offset}").json()["rows"]]
    assert len(rows) == k["open"] and k["overdue"] == sum(r["overdue"] for r in rows) > 0


# --- A16.7: lookup_cve returns the priority -----------------------------------------------------------------------

def test_a16_7_lookup_cve_returns_priority_reasons_due_date_overdue_and_kev_deadline(deps):
    from tests.test_affected import call

    res = call(deps, "lookup_cve", cve_id="CVE-2025-3248").result
    assert res["priority"] == {"level": "urgent", "reasons": ["in KEV", "EPSS 99th percentile"], "due_date": "2025-05-26",
                               "due_from": "KEV deadline", "overdue": True, "alert_priority": 5}
    assert res["kev"]["deadline"] == "2025-05-26"


def test_a16_7_lookup_cve_off_the_watchlist_has_no_priority(deps):
    from tests.test_affected import call

    deps.state.set_watchlist(["ollama"])
    assert call(deps, "lookup_cve", cve_id="CVE-2025-3248").result["priority"] is None


# --- A16.8: the test alert is built from the top priority CVE -----------------------------------------------------

def test_a16_8_test_alert_uses_the_top_priority_cve(client):
    top = client.get("/cves?limit=1").json()["rows"][0]
    alert = client.post("/alerts/test", json={"channel": "preview"}).json()["alert"]
    assert top["id"] in alert["body"]
