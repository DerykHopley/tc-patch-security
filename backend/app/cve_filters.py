"""The CVE view: the CVEs page's filters, under one set of names everywhere. The page's URL, GET /cves, the chat's
page context (app.page_context), WatchedCves.rows and prioritise all use these names, and the rules for their
values live here, so they can't drift. The search filters the LLM proposes (guard.validate_filters) use the same
value rules.

| Filter   | Allowed                                                      | Normalised to          |
|----------|--------------------------------------------------------------|------------------------|
| product  | products I track (name or id, with aliases), comma-separated | ids: `langflow,ollama` |
| severity | LOW, MEDIUM, HIGH, CRITICAL (any case): "this or worse"      | upper case             |
| status   | open, fixed, not_affected, accepted, all                     | as is                  |
| verdict  | affected, not_affected, unknown                              | as is                  |
| kev      | true, 1, "1", "true" / false, 0, "0", "false"                | True / False           |
| since    | a real calendar date written YYYY-MM-DD, inclusive           | the date               |

GET /cves still takes its old names as aliases: severity_min (severity) and published_since (since).

The value functions below return the value normalised, or None when it isn't allowed. CveView.parse raises
InvalidFilter (the /cves query answers 400); the page context drops the value and lists it.
"""
import datetime as dt
import re
from dataclasses import asdict, dataclass

from app.knowledge import SEVERITY_ORDER
from app.status import STATUSES
from app.verdict import VERDICTS

STATUS_FILTERS = (*STATUSES, "all")
PRODUCT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .-]{0,39}$")
MAX_PRODUCTS = 20  # more than the snapshot tracks
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")  # strict: fromisoformat alone also takes 20250101 and week dates
FIELDS = ("product", "severity", "status", "verdict", "kev", "since")  # the page context's order
ALIASES = {"severity_min": "severity", "published_since": "since"}  # GET /cves's old names, still accepted
# The view in words, for FakeLLM's answers (prioritise: "in this view (Langflow, high or worse)")
WORDS = {"product": "{}", "severity": "{} or worse", "verdict": "verdict {}", "kev": "in CISA KEV",
         "since": "published since {}"}


def product(value: str, resolve_product) -> str | None:
    v = value.strip()
    return resolve_product(v) if PRODUCT_RE.match(v) else None


def products(value: str, resolve_product) -> str | None:
    """One product or several, comma-separated (A15b: the dashboard's filter, carried by its tile links). Every one
    must be a product I track; kept as ids, without repeats: `langflow,ollama`."""
    parts = value.split(",")
    if len(parts) > MAX_PRODUCTS:
        return None
    ids = [product(v, resolve_product) for v in parts]
    return ",".join(dict.fromkeys(ids)) if all(ids) else None


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


def kev(value) -> bool | None:
    """True or False; None when it's neither (a URL says `kev=1`, JSON says `true`)."""
    if value in (True, 1, "1", "true"):
        return True
    return False if value in (False, 0, "0", "false") else None


def check(key: str, value, resolve_product):
    """One of the view's filters normalised, or None when the value isn't allowed (or isn't text, but for kev)."""
    if key == "kev":
        return kev(value)
    if not isinstance(value, str):
        return None
    if key == "product":
        return products(value, resolve_product)  # one, or several from the dashboard (A15b)
    return {"severity": severity, "status": status, "since": date, "verdict": verdict}[key](value)


class InvalidFilter(ValueError):
    """A filter value that isn't allowed; the message names the filter as it was sent."""


MESSAGES = {
    "severity": "must be LOW, MEDIUM, HIGH or CRITICAL.",
    "status": "must be open, fixed, not_affected, accepted or all.",
    "kev": "must be true or false.",
    "since": "must be a date, YYYY-MM-DD.",
    "verdict": "must be affected, not_affected or unknown.",
}


@dataclass(frozen=True)
class CveView:
    """What the CVEs page shows: its filters, checked. The defaults (every watched product, any severity, open) are
    no filter. `product`: one id or several, comma-separated (`langflow,ollama`, A15b)."""
    product: str | None = None
    severity: str | None = None
    status: str = "open"
    verdict: str | None = None
    kev: bool | None = None
    since: str | None = None

    @classmethod
    def parse(cls, raw, resolve_product) -> "CveView":
        """The view from a dict: a query string or the page context. Keys that aren't the view's (limit, page, cve)
        are ignored, empty values are no filter, and the old /cves names count as their new ones. Raises
        InvalidFilter for the first value that isn't allowed."""
        view = {}
        for given, value in sorted(raw.items(), key=lambda kv: kv[0] in ALIASES):  # the new name wins, if both
            key = ALIASES.get(given, given)
            if key not in FIELDS or value is None or value == "":
                continue
            kept = check(key, value, resolve_product)
            if kept is None:
                if key == "product":
                    bad = next((p for p in str(value).split(",") if not product(p, resolve_product)), str(value))
                    raise InvalidFilter(f"{bad.strip()!r} isn't a product I track.")
                raise InvalidFilter(f"{given} {MESSAGES[key]}")
            view.setdefault(key, kept)
        return cls(**view)

    def filters(self) -> dict:
        """Every filter by name: WatchedCves.rows' keyword arguments."""
        return asdict(self)
