"""Priority (seam 2): a pure function, table-driven. Check ids: A16.n, from ticket #18.

Each row of the owner's rule table (comment on #18, DECISIONS.md 2026-10-14) has at least one case, plus the
step-down, the threshold, due dates from the policy, KEV deadline adoption on and off, and overdue at the as-of date.
Expected values are written by hand from the table and a calendar, never recomputed the way the code does.
"""
import pytest

from app.app_settings import PolicySettings
from app.priority import ALERT_PRIORITY, CveFacts, priority

AS_OF = "2026-10-13"  # the snapshot date
DEFAULT = PolicySettings()  # urgent 7, high 30, normal 90, low 180 days; adopt the KEV deadline
NO_KEV_DEADLINE = PolicySettings(adopt_kev_deadline=False)


def facts(severity="HIGH", kev=False, epss=None, verdict="unknown", internet_facing=False, status="open",
          published="2026-10-01", kev_added=None, kev_deadline=None, review_date=None, no_fix=False):
    return CveFacts(severity=severity, kev=kev, epss_percentile=epss, verdict=verdict,
                    internet_facing=internet_facing, status=status, published=published,
                    kev_added=kev_added, kev_deadline=kev_deadline, review_date=review_date, no_fix=no_fix)


KEV = {"kev": True, "kev_added": "2025-05-05", "kev_deadline": "2025-05-26"}  # CVE-2025-3248's dates

# --- A16.1: every row of the rule table, and the step-down -------------------------------------------------------

LEVELS = [
    # case, facts, level, reasons
    # Row 1: in KEV and verdict isn't "not affected" -> urgent
    ("1: in KEV, affected", facts(verdict="affected", **KEV), "urgent", ["in KEV"]),
    ("1: in KEV, verdict unknown, low severity", facts(severity="LOW", **KEV), "urgent", ["in KEV"]),
    ("1: in KEV with every other signal", facts(epss=0.98592, internet_facing=True, **KEV), "urgent",
     ["in KEV", "EPSS 98th percentile", "internet-facing"]),
    # Row 2: critical, or EPSS >= threshold, on an internet-facing product -> high
    ("2: critical, internet-facing", facts(severity="CRITICAL", epss=0.4, internet_facing=True), "high",
     ["critical", "internet-facing"]),
    ("2: medium with high EPSS, internet-facing", facts(severity="MEDIUM", epss=0.95, internet_facing=True), "high",
     ["EPSS 95th percentile", "internet-facing"]),
    ("2: critical and high EPSS, internet-facing", facts(severity="CRITICAL", epss=0.99, internet_facing=True),
     "high", ["critical", "EPSS 99th percentile", "internet-facing"]),
    ("2: EPSS exactly at the threshold counts", facts(severity="LOW", epss=0.90, internet_facing=True), "high",
     ["EPSS 90th percentile", "internet-facing"]),
    ("2: EPSS just under the threshold doesn't", facts(severity="MEDIUM", epss=0.89931, internet_facing=True),
     "normal", ["medium severity"]),
    ("2: high EPSS but not internet-facing", facts(severity="MEDIUM", epss=0.99), "normal", ["medium severity"]),
    # Row 3: otherwise critical -> high
    ("3: critical, not internet-facing", facts(severity="CRITICAL"), "high", ["critical"]),
    # Row 4: otherwise high -> normal
    ("4: high severity", facts(severity="HIGH"), "normal", ["high severity"]),
    ("4: high severity, internet-facing, low EPSS", facts(severity="HIGH", epss=0.5, internet_facing=True),
     "normal", ["high severity"]),
    # Row 5: medium -> normal
    ("5: medium severity", facts(severity="MEDIUM"), "normal", ["medium severity"]),
    # Row 6: low -> low
    ("6: low severity", facts(severity="LOW"), "low", ["low severity"]),
    # Not in the owner's table: no severity yet (3 snapshot CVEs) is treated like medium
    ("unscored (no severity)", facts(severity=None), "normal", ["not scored yet"]),
    ("unscored (NVD's NONE)", facts(severity="NONE"), "normal", ["not scored yet"]),
    # The step-down: verdict "not affected" -> one level lower; low stays low
    ("step: critical internet-facing, not affected", facts(severity="CRITICAL", internet_facing=True,
                                                            verdict="not_affected"),
     "normal", ["critical", "internet-facing", "not affected: one level lower"]),
    ("step: critical, not affected", facts(severity="CRITICAL", verdict="not_affected"), "normal",
     ["critical", "not affected: one level lower"]),
    ("step: high, not affected", facts(severity="HIGH", verdict="not_affected"), "low",
     ["high severity", "not affected: one level lower"]),
    ("step: medium, not affected", facts(severity="MEDIUM", verdict="not_affected"), "low",
     ["medium severity", "not affected: one level lower"]),
    ("step: low stays low", facts(severity="LOW", verdict="not_affected"), "low",
     ["low severity", "not affected: low stays low"]),
    ("step: affected changes nothing", facts(severity="HIGH", verdict="affected"), "normal", ["high severity"]),
    # A not-affected KEV CVE isn't urgent: rows 2-6, then one step down
    ("step: KEV, not affected, high", facts(severity="HIGH", verdict="not_affected", **KEV), "low",
     ["high severity", "in KEV, but not affected: one level lower"]),
    ("step: KEV, not affected, critical internet-facing", facts(severity="CRITICAL", internet_facing=True,
                                                                verdict="not_affected", **KEV),
     "normal", ["critical", "internet-facing", "in KEV, but not affected: one level lower"]),
]


@pytest.mark.parametrize("case,f,level,reasons", LEVELS, ids=[row[0] for row in LEVELS])
def test_a16_1_rule_table(case, f, level, reasons):
    p = priority(f, DEFAULT, AS_OF)
    assert (p.level, list(p.reasons)) == (level, reasons)


def test_a16_1_the_epss_threshold_is_a_setting():  # default: the 90th percentile
    f = facts(severity="MEDIUM", epss=0.93, internet_facing=True)
    assert priority(f, DEFAULT, AS_OF).level == "high"
    assert priority(f, DEFAULT, AS_OF, epss_percentile=95).level == "normal"


def test_a16_1_the_rule_that_matched_is_named():
    assert priority(facts(**KEV), DEFAULT, AS_OF).rule == 1
    assert priority(facts(severity="CRITICAL", internet_facing=True), DEFAULT, AS_OF).rule == 2
    assert priority(facts(severity="LOW"), DEFAULT, AS_OF).rule == 6
    assert priority(facts(severity="HIGH", verdict="not_affected", **KEV), DEFAULT, AS_OF).rule == 4


# --- A16.2: levels map to alert priorities 5/4/3/2 (for spec B's alerts) -----------------------------------------

def test_a16_2_levels_map_to_alert_priorities():
    assert ALERT_PRIORITY == {"urgent": 5, "high": 4, "normal": 3, "low": 2}
    assert priority(facts(**KEV), DEFAULT, AS_OF).alert_priority == 5
    assert priority(facts(severity="LOW"), DEFAULT, AS_OF).alert_priority == 2


# --- A16.3: due dates from the policy, the KEV deadline when adopted, overdue at the as-of date -------------------

DUE = [
    # case, facts, policy, due date, overdue
    ("high: published + 30", facts(severity="CRITICAL", published="2026-10-01"), DEFAULT, "2026-10-31", False),
    ("normal: published + 90", facts(severity="MEDIUM", published="2026-01-01"), DEFAULT, "2026-04-01", True),
    ("low: published + 180", facts(severity="LOW", published="2026-05-01"), DEFAULT, "2026-10-28", False),
    ("the stepped-down level's days", facts(severity="CRITICAL", verdict="not_affected", published="2026-01-01"),
     DEFAULT, "2026-04-01", True),
    ("custom days", facts(severity="CRITICAL", published="2026-10-01"), PolicySettings(high_days=14),
     "2026-10-15", False),
    ("KEV, deadline adopted", facts(**KEV), DEFAULT, "2025-05-26", True),
    ("KEV, not adopted: KEV-added + 7", facts(**KEV), NO_KEV_DEADLINE, "2025-05-12", True),
    ("KEV not affected, not adopted: KEV-added + 90", facts(severity="CRITICAL", verdict="not_affected", **KEV),
     NO_KEV_DEADLINE, "2025-08-03", True),
    ("KEV not affected, adopted: still the KEV deadline", facts(severity="CRITICAL", verdict="not_affected", **KEV),
     DEFAULT, "2025-05-26", True),
    ("due on the as-of date isn't overdue yet", facts(severity="CRITICAL", published="2026-09-13"), DEFAULT,
     "2026-10-13", False),
    ("due the day before is overdue", facts(severity="CRITICAL", published="2026-09-12"), DEFAULT,
     "2026-10-12", True),
    ("fixed is never overdue", facts(severity="MEDIUM", published="2024-01-01", status="fixed"), DEFAULT,
     "2024-03-31", False),
    ("not affected (your mark) is never overdue", facts(severity="MEDIUM", published="2024-01-01",
                                                        status="not_affected"), DEFAULT, "2024-03-31", False),
]


@pytest.mark.parametrize("case,f,policy,due,overdue", DUE, ids=[row[0] for row in DUE])
def test_a16_3_due_date_and_overdue(case, f, policy, due, overdue):
    p = priority(f, policy, AS_OF)
    assert (p.due_date, p.overdue) == (due, overdue)


# --- A16b.3: overdue only when a fix exists and the CVE is open (review due counts as open) ---------------------

OVERDUE = [
    # case, facts, overdue
    ("open, a fix exists, past due", facts(severity="MEDIUM", published="2024-01-01"), True),
    ("open, no fix yet, past due: not overdue", facts(severity="MEDIUM", published="2024-01-01", no_fix=True), False),
    ("accepted before its review date", facts(severity="MEDIUM", published="2024-01-01", status="accepted",
                                              review_date="2027-01-01"), False),
    ("accepted, review due, a fix exists", facts(severity="MEDIUM", published="2024-01-01", status="accepted",
                                                 review_date="2026-10-13"), True),
    ("accepted, review due, no fix yet", facts(severity="MEDIUM", published="2024-01-01", status="accepted",
                                               review_date="2026-10-01", no_fix=True), False),
    ("KEV, no fix yet: not overdue either", facts(no_fix=True, **KEV), False),
]


@pytest.mark.parametrize("case,f,overdue", OVERDUE, ids=[row[0] for row in OVERDUE])
def test_a16b_3_overdue_only_when_a_fix_exists(case, f, overdue):
    p = priority(f, DEFAULT, AS_OF)
    assert p.overdue is overdue
    assert p.due_date  # a no-fix CVE keeps its due date: the "decide by" date


def test_a16_3_the_due_date_says_where_it_came_from():
    assert priority(facts(**KEV), DEFAULT, AS_OF).due_from == "KEV deadline"
    assert priority(facts(**KEV), NO_KEV_DEADLINE, AS_OF).due_from == "added to KEV + 7 days"
    assert priority(facts(severity="LOW"), DEFAULT, AS_OF).due_from == "published + 180 days"
