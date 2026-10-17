"""CVE statuses and "open CVE" (A16b): the one place that decides whether a CVE is open. Pure functions.

| Your status   | At the as-of date                 | Open? |
|---------------|-----------------------------------|-------|
| open          | always                            | yes   |
| fixed         | always                            | no    |
| not affected  | always                            | no    |
| accepted      | before its review date            | no    |
| accepted      | on or after its review date       | yes: "review due", until you decide again |

Only the user sets a status. Rules, the verdict and Patch never do.
"""

import datetime as dt

from app.errors import InputError

STATUSES = ("open", "fixed", "not_affected", "accepted")
# VEX justifications for "not affected" (CISA's VEX minimum requirements; OpenVEX uses the same names)
JUSTIFICATIONS = ("component_not_present", "vulnerable_code_not_present", "vulnerable_code_not_in_execute_path",
                  "vulnerable_code_cannot_be_controlled_by_adversary", "inline_mitigations_already_exist")
# The fields each status takes; anything else is a 400. Required ones are checked below.
FIELDS = {"open": ("note",), "fixed": ("note",), "not_affected": ("justification", "note"),
          "accepted": ("reason", "review_date", "compensating_control")}
LABELS = {"note": "a note", "justification": "a justification", "reason": "a reason",
          "review_date": "a review date", "compensating_control": "a compensating control"}
LEGACY_NOTE = "recorded before decision records"
DECIDED_BY = "owner"  # the default user (sign-in off); a signed-in user is named by Deps.decided_by (B10)


def decision(status: str, fields: dict, as_of: str) -> dict:
    """A checked decision record (without when and who) for a status change. InputError with a plain message if a
    required field is missing, a value isn't allowed or a field doesn't belong to the status."""
    if status not in STATUSES:
        raise InputError(f"Status must be one of {', '.join(STATUSES)}, not {status!r}.")
    given = {k: v.strip() if isinstance(v, str) else v for k, v in fields.items()}
    given = {k: v for k, v in given.items() if v not in (None, "")}
    for k in given:
        if k not in FIELDS[status]:
            raise InputError(f"{status.replace('_', ' ').capitalize()} doesn't take {LABELS.get(k, k)}.")
    out = {"status": status, "justification": None, "reason": None, "note": None, "review_date": None,
           "compensating_control": None} | given
    if status == "not_affected":
        if "justification" not in given:
            raise InputError("Not affected needs a justification: one of " + ", ".join(JUSTIFICATIONS) + ".")
        if given["justification"] not in JUSTIFICATIONS:
            raise InputError(f"{given['justification']!r} isn't a justification. Choose one of "
                             + ", ".join(JUSTIFICATIONS) + ".")
    if status == "accepted":
        if "reason" not in given:
            raise InputError("Accepting a risk needs a reason: why it's acceptable for now.")
        if "review_date" not in given:
            raise InputError("Accepting a risk needs a review date: when to look at it again.")
        try:
            review = dt.date.fromisoformat(given["review_date"]).isoformat()
        except (TypeError, ValueError):
            raise InputError("The review date must be a date, YYYY-MM-DD.") from None
        if review <= as_of:
            raise InputError(f"The review date must be after the as-of date, {as_of}.")
        out["review_date"] = review
    return out


def review_due(status: str, review_date: str | None, as_of: str) -> bool:
    """An accepted CVE whose review date has come. No review date (a hand-edited file) counts as due."""
    return status == "accepted" and (review_date is None or as_of >= review_date)


def is_open(status: str, review_date: str | None, as_of: str) -> bool:
    return status == "open" or review_due(status, review_date, as_of)
