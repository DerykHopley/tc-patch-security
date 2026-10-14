"""Priority (A16): how urgent an open CVE is for you, with the reasons and a due date. A pure function; the rules are
the table below, settled by the owner on 2026-10-14 (comment on #18, DECISIONS.md). Rules decide; Patch only explains.

The first row that matches gives the level. Then the step-down applies.

| # | Condition                                                                    | Priority                       |
|---|------------------------------------------------------------------------------|--------------------------------|
| 1 | In KEV and verdict isn't "not affected"                                      | urgent                         |
| 2 | Critical, or EPSS >= the threshold (90th percentile), on an internet-facing  | high                           |
|   | product                                                                      |                                |
| 3 | Otherwise critical                                                           | high                           |
| 4 | Otherwise high                                                               | normal                         |
| 5 | Medium                                                                       | normal                         |
| 6 | Low                                                                          | low                            |
| 7 | Not scored yet (not in the owner's table: treated like medium; Gate B check) | normal                         |
| - | Verdict "not affected"                                                       | one level lower; low stays low |

A not-affected KEV CVE isn't urgent: row 1 skips it, so it takes the level rows 2-7 give, then steps down.

Reasons are the facts the matched row tested ("critical", "internet-facing"); row 1 also lists the other signals
present (high EPSS, internet-facing). A step-down adds its own reason.

Due date (your policy): the publication date, or for a KEV CVE the date it was added to KEV, plus the policy's days
for the level. With "adopt the KEV deadline" on, a KEV CVE's due date is CISA's KEV deadline instead. Overdue = the
CVE is open and the as-of date is after the due date.

Levels map to alert priorities 5/4/3/2 (ntfy's scale; spec B's alerts use it).
"""
import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass

from app.app_settings import PolicySettings

LEVELS = ("urgent", "high", "normal", "low")  # most urgent first: the sort order
ALERT_PRIORITY = {"urgent": 5, "high": 4, "normal": 3, "low": 2}
SEVERITY_REASON = {"CRITICAL": "critical", "HIGH": "high severity", "MEDIUM": "medium severity",
                   "LOW": "low severity"}


@dataclass(frozen=True)
class CveFacts:
    severity: str | None  # CRITICAL, HIGH, MEDIUM, LOW; None or NONE when NVD hasn't scored it
    kev: bool
    epss_percentile: float | None  # 0-1, EPSS by FIRST
    verdict: str  # affected, not_affected, unknown (A15)
    internet_facing: bool  # your mark on the product
    status: str  # your CVE status: open, fixed, not_affected
    published: str  # YYYY-MM-DD
    kev_added: str | None = None
    kev_deadline: str | None = None


@dataclass(frozen=True)
class Priority:
    level: str
    reasons: tuple[str, ...]
    rule: int  # the table row that matched
    due_date: str
    due_from: str  # "KEV deadline", "published + 90 days", "added to KEV + 7 days"
    overdue: bool
    alert_priority: int


@dataclass(frozen=True)
class _Signals:
    """What the rows test, worked out once from the facts and the threshold."""
    f: CveFacts
    severity: str | None  # None when not scored
    epss_high: bool
    epss_reason: str | None


def _severity_is(sev: str) -> Callable[[_Signals], bool]:
    return lambda s: s.severity == sev


def _row1_reasons(s: _Signals) -> list[str]:
    return ["in KEV"] + ([s.epss_reason] if s.epss_high else []) + (["internet-facing"] if s.f.internet_facing else [])


def _row2_reasons(s: _Signals) -> list[str]:
    return (["critical"] if s.severity == "CRITICAL" else []) + ([s.epss_reason] if s.epss_high else []) + [
        "internet-facing"]


def _severity_reason(s: _Signals) -> list[str]:
    return [SEVERITY_REASON[s.severity] if s.severity else "not scored yet"]


# The rule table: (row, condition, level, reasons). Read top to bottom; the first match wins.
RULES: list[tuple[int, Callable[[_Signals], bool], str, Callable[[_Signals], list[str]]]] = [
    (1, lambda s: s.f.kev and s.f.verdict != "not_affected", "urgent", _row1_reasons),
    (2, lambda s: s.f.internet_facing and (s.severity == "CRITICAL" or s.epss_high), "high", _row2_reasons),
    (3, _severity_is("CRITICAL"), "high", _severity_reason),
    (4, _severity_is("HIGH"), "normal", _severity_reason),
    (5, _severity_is("MEDIUM"), "normal", _severity_reason),
    (6, _severity_is("LOW"), "low", _severity_reason),
    (7, lambda s: s.severity is None, "normal", _severity_reason),
]


def ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _percent(p: float) -> int:
    return int(round(p * 100, 6))  # 0.9 -> 90, not 89.99999


def _add_days(date: str, days: int) -> str:
    return (dt.date.fromisoformat(date) + dt.timedelta(days=days)).isoformat()


def priority(f: CveFacts, policy: PolicySettings, as_of: str, epss_percentile: int = 90) -> Priority:
    """The level, reasons, due date and overdue for one CVE. `epss_percentile`: row 2's threshold (a setting)."""
    pct = _percent(f.epss_percentile) if f.epss_percentile is not None else None
    s = _Signals(f, f.severity if f.severity in SEVERITY_REASON else None,
                 pct is not None and pct >= epss_percentile, f"EPSS {ordinal(pct)} percentile" if pct else None)
    row, _, level, why = next(r for r in RULES if r[1](s))
    reasons = why(s)

    if f.verdict == "not_affected":
        if level == "low":
            reasons.append("not affected: low stays low")
        else:
            level = LEVELS[LEVELS.index(level) + 1]
            reasons.append(("in KEV, but not affected" if f.kev else "not affected") + ": one level lower")

    if f.kev and policy.adopt_kev_deadline and f.kev_deadline:
        due, due_from = f.kev_deadline, "KEV deadline"
    else:
        days = policy.days(level)
        start, label = (f.kev_added, "added to KEV") if f.kev and f.kev_added else (f.published, "published")
        due, due_from = _add_days(start, days), f"{label} + {days} days"

    return Priority(level, tuple(reasons), row, due, due_from, f.status == "open" and as_of > due,
                    ALERT_PRIORITY[level])


def sort_key(level: str, due_date: str) -> tuple[int, str]:
    """Most urgent level first; inside a level, the earliest due date first."""
    return LEVELS.index(level), due_date
