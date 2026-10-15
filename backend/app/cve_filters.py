"""The rules for CVE filter values, in one place: the CVEs page's query (GET /cves), the chat's page context
(app.page_context) and the search filters the LLM proposes (guard.validate_filters) all use them, so they can't drift.

Each function returns the value normalised, or None when it isn't allowed. Callers decide what None means: the
/cves query answers 400, the page context and search filters drop the value and list it.

| Filter   | Allowed                                                      | Normalised to        |
|----------|--------------------------------------------------------------|----------------------|
| product  | a product I track (name or id, with aliases)                 | its id: `langflow`   |
| severity | LOW, MEDIUM, HIGH, CRITICAL (any case): "this or worse"      | upper case           |
| status   | open, fixed, not_affected, accepted, all                     | as is                |
| verdict  | affected, not_affected, unknown                              | as is                |
| date     | a real calendar date written YYYY-MM-DD                      | the date             |
"""
import datetime as dt
import re

from app.knowledge import SEVERITY_ORDER
from app.status import STATUSES
from app.verdict import VERDICTS

STATUS_FILTERS = (*STATUSES, "all")
PRODUCT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .-]{0,39}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")  # strict: fromisoformat alone also takes 20250101 and week dates


def product(value: str, resolve_product) -> str | None:
    v = value.strip()
    return resolve_product(v) if PRODUCT_RE.match(v) else None


def severity(value: str) -> str | None:
    v = value.strip().upper()
    return v if v in SEVERITY_ORDER else None


def status(value: str) -> str | None:
    v = value.strip()
    return v if v in STATUS_FILTERS else None


def verdict(value: str) -> str | None:
    v = value.strip()
    return v if v in VERDICTS else None


def date(value: str) -> str | None:
    v = value.strip()
    if not DATE_RE.match(v):
        return None
    try:
        return dt.date.fromisoformat(v).isoformat()
    except ValueError:
        return None
