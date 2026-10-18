"""Alerts (B04, #37): the diff and the alert rules as pure functions, with table tests (seam 2). Check ids: B04.n.

The API tests (seam 1: a day-2 refresh with the fake feeds and fake transports) are in test_alert_delivery.py.
"""
import datetime as dt

import pytest

from app.alerts import Diff, batch, diff, digest, in_quiet_hours, rules
from app.app_settings import AlertSettings


def cve(id_, sev="HIGH", cvss=7.5, published="2026-10-14", product="langflow"):
    return {"id": id_, "severity": sev, "cvss": cvss, "published": published, "product": product}


def files(cves, kev=(), osv=None):
    """A live version's files, as much of them as the diff reads."""
    return {"cves.json": {"cves": cves}, "kev.json": [{"cveID": i, "dateAdded": d} for i, d in kev],
            "osv.json": {"cves": osv or {}}}


def fixed(*versions):
    return [{"product": "langflow", "fixed": list(versions)}]


def day_versions():
    """The live versions a refresh writes on day 1 and day 2 of the fake feeds, on top of the snapshot."""
    import json

    from app import cve_build
    from app.config import FIXTURES
    from app.feeds import FakeFeeds
    from app.live_data import FILES
    from app.refresh import build_version

    version = {name: json.loads((FIXTURES / name).read_text()) for name in FILES}
    cwe_to_web = json.loads((FIXTURES / "owasp.json").read_text())["cwe_to_web"]
    out = []
    for day in (1, 2):
        f = FakeFeeds(day)
        now = dt.datetime(2026, 10, 13 + day, 9, tzinfo=dt.UTC)
        osv = {cve_build.package_key(e, n): f.osv(e, n) for p in cve_build.PACKAGES.values() for e, n in p["packages"]}
        ids = [r["id"] for r in version["cves.json"]["cves"]] + [r["id"] for r in f.nvd_modified(now, now)]
        version = build_version(version, f.nvd_modified(now, now), f.kev(), osv, f.epss(ids), cwe_to_web, now)[0]
        out.append(version)
    return out


# --- B04.1: the diff ----------------------------------------------------------------------------------------------

def test_b04_1_a_cve_not_in_the_previous_version_is_new():
    d = diff(files([cve("CVE-1")]), files([cve("CVE-2"), cve("CVE-1")]))
    assert d.new == ("CVE-2",) and d.kev_added == {} and d.rescored == {} and d.fixed_changed == {}


def test_b04_1_added_to_kev_by_the_date_cisa_added_it_so_an_old_cve_counts():
    old = cve("CVE-2024-1", published="2024-05-01")
    d = diff(files([old], kev=[("CVE-0", "2025-01-01")]), files([old], kev=[("CVE-0", "2025-01-01"),
                                                                          ("CVE-2024-1", "2026-10-15")]))
    assert d.kev_added == {"CVE-2024-1": "2026-10-15"} and d.new == ()


def test_b04_1_a_changed_severity_or_score_is_a_rescore():
    d = diff(files([cve("CVE-1", "HIGH", 8.1), cve("CVE-2", "HIGH", 7.0), cve("CVE-3")]),
             files([cve("CVE-1", "CRITICAL", 9.1), cve("CVE-2", "HIGH", 7.4), cve("CVE-3")]))
    assert d.rescored == {"CVE-1": ("HIGH", "CRITICAL"), "CVE-2": ("HIGH", "HIGH")}


def test_b04_1_an_unscored_cve_getting_a_score_is_a_rescore():
    d = diff(files([cve("CVE-1", None, None)]), files([cve("CVE-1", "CRITICAL", 9.8)]))
    assert d.rescored == {"CVE-1": (None, "CRITICAL")}


def test_b04_1_a_changed_fixed_version_is_listed_with_before_and_after():
    d = diff(files([cve("CVE-1"), cve("CVE-2")], osv={"CVE-2": fixed("1.0")}),
             files([cve("CVE-1"), cve("CVE-2")], osv={"CVE-1": fixed("1.9.2"), "CVE-2": fixed("1.0")}))
    assert d.fixed_changed == {"CVE-1": ((), ("1.9.2",))}


def test_b04_1_the_real_day1_to_day2_versions():
    """The fake feeds' day 1 and day 2 (B02), built by the refresh's own code."""
    day1, day2 = day_versions()
    d = diff(day1, day2)
    assert d.new == ("CVE-2026-99102",)
    assert d.kev_added == {"CVE-2024-37014": "2026-10-15"}
    assert d.rescored == {"CVE-2026-99101": ("HIGH", "CRITICAL")}
    assert d.fixed_changed == {"CVE-2026-99101": ((), ("1.9.2",))}


# --- B04.2: the alert rules, one row of the reasons table (ALERTS-PLAN.md, with its 2026-10-13 update) per case ----

AS_OF = "2026-10-15"  # a Thursday, ISO week 2026-W42


def row(id_="CVE-1", severity="HIGH", status="open", verdict="affected", due_date="2026-12-31", overdue=False,
        alert_priority=3, open_=None):
    """A WatchedCves row, as much of it as the rules read. Open unless fixed, not affected or accepted."""
    return {"id": id_, "severity": severity, "status": status, "verdict": verdict,
            "open": status == "open" if open_ is None else open_,
            "due_date": due_date, "overdue": overdue, "alert_priority": alert_priority}


KEV = Diff(kev_added={"CVE-1": "2026-10-15"})
NEW = Diff(new=("CVE-1",))
CRIT = Diff(rescored={"CVE-1": ("HIGH", "CRITICAL")})
NONE = Diff()

CASES = {
    # kev: a watched CVE is added to KEV
    "kev fires": (KEV, row(alert_priority=5), {}, [("kev", 5)]),
    "kev on an unknown verdict fires": (KEV, row(verdict="unknown", alert_priority=5), {}, [("kev", 5)]),
    "kev skips a not-affected verdict": (KEV, row(verdict="not_affected"), {}, []),
    "kev skips a CVE marked not affected": (KEV, row(status="not_affected"), {}, []),
    "kev skips an accepted CVE": (KEV, row(status="accepted"), {}, []),
    "kev skips an accepted CVE with its review due": (KEV, row(status="accepted", open_=True), {}, []),
    "kev is switched off": (KEV, row(), {"kev": False}, []),
    # kev_recheck: a CVE marked fixed is added to KEV
    "kev_recheck fires on a fixed CVE": (KEV, row(status="fixed", alert_priority=4), {}, [("kev_recheck", 4)]),
    "kev_recheck is switched off": (KEV, row(status="fixed"), {"kev_recheck": False}, []),
    # new: a new CVE at or above min_severity
    "new fires at the minimum severity": (NEW, row(severity="HIGH"), {}, [("new", 3)]),
    "new fires above it": (NEW, row(severity="CRITICAL", alert_priority=4), {}, [("new", 4)]),
    "new skips below the minimum": (NEW, row(severity="MEDIUM"), {}, []),
    "new follows a lower minimum": (NEW, row(severity="LOW", alert_priority=2), {"min_severity": "LOW"},
                                    [("new", 2)]),
    "new skips a not-affected verdict": (NEW, row(verdict="not_affected"), {}, []),
    "new skips an accepted CVE": (NEW, row(status="accepted"), {}, []),
    # new_unscored: a new CVE with no severity yet
    "new_unscored fires": (NEW, row(severity=None, alert_priority=2), {}, [("new_unscored", 2)]),
    "new_unscored fires for NONE too": (NEW, row(severity="NONE", alert_priority=2), {}, [("new_unscored", 2)]),
    "new_unscored is switched off": (NEW, row(severity=None), {"unscored": False}, []),
    "new_unscored skips a not-affected verdict": (NEW, row(severity=None, verdict="not_affected"), {}, []),
    # now_critical: a known open CVE is rescored as critical
    "now_critical fires": (CRIT, row(severity="CRITICAL", alert_priority=4), {}, [("now_critical", 4)]),
    "now_critical from unscored fires": (Diff(rescored={"CVE-1": (None, "CRITICAL")}),
                                         row(severity="CRITICAL", alert_priority=4), {}, [("now_critical", 4)]),
    "now_critical skips a rescore that stays high": (Diff(rescored={"CVE-1": ("HIGH", "HIGH")}), row(), {}, []),
    "now_critical skips a CVE already critical": (Diff(rescored={"CVE-1": ("CRITICAL", "CRITICAL")}),
                                                  row(severity="CRITICAL"), {}, []),
    "now_critical skips a fixed CVE": (CRIT, row(severity="CRITICAL", status="fixed"), {}, []),
    "now_critical is switched off": (CRIT, row(severity="CRITICAL"), {"now_critical": False}, []),
    # due_soon: an open, affected CVE is 3 days from its due date (always on)
    "due_soon fires 3 days before": (NONE, row(due_date="2026-10-18", alert_priority=4), {}, [("due_soon", 4)]),
    "due_soon fires on the day": (NONE, row(due_date="2026-10-15"), {}, [("due_soon", 3)]),
    "due_soon waits at 4 days": (NONE, row(due_date="2026-10-19"), {}, []),
    "due_soon skips a fixed CVE": (NONE, row(due_date="2026-10-16", status="fixed"), {}, []),
    "due_soon skips a not-affected verdict": (NONE, row(due_date="2026-10-16", verdict="not_affected"), {}, []),
    "due_soon has no switch": (NONE, row(due_date="2026-10-16"), {"kev": False, "kev_recheck": False,
                                                                    "unscored": False, "now_critical": False},
                               [("due_soon", 3)]),
    # overdue: an open, affected CVE past its due date, once a week (always on)
    "overdue fires": (NONE, row(due_date="2026-10-01", overdue=True, alert_priority=5), {}, [("overdue", 5)]),
    "overdue skips a fixed CVE": (NONE, row(due_date="2026-10-01", status="fixed"), {}, []),
    "overdue skips a not-affected verdict": (NONE, row(due_date="2026-10-01", overdue=True, verdict="not_affected"),
                                             {}, []),
    # alerts off: nothing at all
    "alerts off": (KEV, row(due_date="2026-10-01", overdue=True), {"enabled": False}, []),
}


@pytest.mark.parametrize("d, r, settings, expected", CASES.values(), ids=CASES.keys())
def test_b04_2_each_reason_fires_and_skips_as_the_table_says(d, r, settings, expected):
    got = rules(d, {r["id"]: r}, AlertSettings(**settings), AS_OF)
    assert [(a.reason, a.priority) for a in got] == expected
    assert all(a.cve == "CVE-1" for a in got)


def test_b04_2_a_cve_off_the_watchlist_never_alerts():
    d = Diff(new=("CVE-9",), kev_added={"CVE-9": AS_OF}, rescored={"CVE-9": ("HIGH", "CRITICAL")})
    assert rules(d, {"CVE-1": row()}, AlertSettings(), AS_OF) == []


def test_b04_2_one_cve_can_alert_for_two_reasons():
    d = Diff(new=("CVE-1",), kev_added={"CVE-1": AS_OF})
    assert [a.reason for a in rules(d, {"CVE-1": row(alert_priority=5)}, AlertSettings(), AS_OF)] == ["kev", "new"]


def test_b04_2_each_alert_has_a_key_and_overdue_is_keyed_by_week():
    rows = {"CVE-1": row(), "CVE-2": row("CVE-2", due_date="2026-10-01", overdue=True)}
    keys = {a.reason: a.key for a in rules(NEW, rows, AlertSettings(), AS_OF)}
    assert keys == {"new": "CVE-1|new", "overdue": "CVE-2|overdue|2026-W42"}
    next_week = rules(NONE, rows, AlertSettings(), "2026-10-19")  # Monday: a new ISO week
    assert [a.key for a in next_week] == ["CVE-2|overdue|2026-W43"]


# --- B04.3: quiet hours and the digest threshold ------------------------------------------------------------------

QUIET = {
    "overnight, late": ("22:00", "07:00", "23:30", True),
    "overnight, early": ("22:00", "07:00", "06:59", True),
    "overnight, at the end": ("22:00", "07:00", "07:00", False),
    "overnight, at the start": ("22:00", "07:00", "22:00", True),
    "overnight, midday": ("22:00", "07:00", "12:00", False),
    "daytime, inside": ("09:00", "17:00", "10:00", True),
    "daytime, before": ("09:00", "17:00", "08:59", False),
    "no quiet hours": (None, None, "03:00", False),
    "only a start": ("22:00", None, "23:00", False),
    "start equals end": ("08:00", "08:00", "08:00", False),
}


@pytest.mark.parametrize("start, end, at, expected", QUIET.values(), ids=QUIET.keys())
def test_b04_3_quiet_hours(start, end, at, expected):
    assert in_quiet_hours(dt.time.fromisoformat(at), start, end) is expected


def msg(cve_id, reason, priority=3):
    return {"cve": cve_id, "reason": reason, "title": f"{reason}: Langflow", "body": cve_id, "priority": priority,
            "tags": [reason, "langflow"], "click": f"http://app/cves/{cve_id}"}


def test_b04_3_up_to_the_limit_each_alert_is_its_own_message():
    alerts = [msg(f"CVE-{i}", "new") for i in range(5)]
    assert batch(alerts, 5) == [[a] for a in alerts]


def test_b04_3_above_the_limit_the_alerts_become_one_digest():
    alerts = [msg("CVE-1", "kev", 5), msg("CVE-2", "kev", 5), msg("CVE-3", "new"), msg("CVE-4", "overdue", 4)]
    assert batch(alerts, 3) == [alerts]  # one message carries every alert, so each is still logged
    d = digest(alerts, "http://app")
    assert d == {"title": "4 alerts for your watchlist", "body": "2 in CISA KEV · 1 new · 1 overdue",
                 "priority": 5, "tags": ["digest"], "click": "http://app/cves"}
    assert all(a["body"] not in d["body"] for a in alerts)  # the digest says counts only: the ids are in the app
