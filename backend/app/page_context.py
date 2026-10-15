"""Page context (A18): what the user is looking at when they ask, as fixed fields only.

The chat request may carry the page name, the CVEs page's filters (the CVE view, app.cve_filters: product, severity,
status, verdict, kev, since, under the same names as the page's URL and GET /cves) and the selected CVE id; on the dashboard, its product filter (A15b). Each is checked against a fixed list or an id pattern here; anything else (a value not on
the list, another type, an unknown field) is dropped and listed in the reply. So the context can narrow a view but
never carry free text to Patch: an instruction can't ride in on it.

| Field    | Allowed                                                       | Kept as              |
|----------|---------------------------------------------------------------|----------------------|
| page     | dashboard, cves, settings, dev                                | as is                |
| product  | products I track, comma-separated (the dashboard's filter, A15b) | ids: `langflow,ollama` |
| severity | LOW, MEDIUM, HIGH, CRITICAL (any case): "this or worse"       | upper case           |
| status   | open, fixed, not_affected, accepted, all                      | as is                |
| verdict  | affected, not_affected, unknown                               | as is                |
| kev      | true, 1, "1", "true" (false, 0: no filter)                    | true                 |
| since    | a date, YYYY-MM-DD                                            | the date             |
| cve      | CVE-YYYY-NNNN…                                                | upper case           |
"""
import json
import re

from app import cve_filters, guard

PAGES = ("dashboard", "cves", "settings", "dev")
FIELDS = ("page", "product", "severity", "status", "verdict", "kev", "since", "cve")
CVE_ID_RE = re.compile(r"^CVE-\d{4}-\d{4,7}$", re.IGNORECASE)
SHOWN = 40  # characters of a dropped value listed back


def _check(key: str, value, resolve_product) -> tuple[bool, object]:
    """(ok, the kept value). ok with None kept: a value that means "no filter" (kev false). The CVE view's filters
    use its rules (app.cve_filters), the same as the CVEs page's query."""
    if key in cve_filters.FIELDS:
        kept = cve_filters.check(key, value, resolve_product)
        return (True, None) if kept is False else (kept is not None, kept)  # kev false: no filter
    if not isinstance(value, str):
        return False, None
    v = value.strip()
    kept = (v if v in PAGES else None) if key == "page" else (v.upper() if CVE_ID_RE.match(v) else None)  # cve
    return kept is not None, kept


def _shown(key: str, value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(str(text).split())
    return f"{key[:16]}={text[:SHOWN] + '…' if len(text) > SHOWN else text}"


def validate(raw: dict | None, resolve_product) -> tuple[dict, list[str]]:
    """The fields that passed, normalised, and the rest listed as "key=value" (cut short). Never raises."""
    kept, dropped = {}, []
    for key, value in (raw or {}).items():
        if value is None or value == "":
            continue
        ok, v = _check(key, value, resolve_product) if key in FIELDS else (False, None)
        if not ok:
            dropped.append(_shown(str(key), value))
        elif v is not None:
            kept[key] = v
    return {k: kept[k] for k in FIELDS if k in kept}, dropped


def for_model(ctx: dict) -> str:
    """The checked context for the system prompt, wrapped like tool output: data, never instructions."""
    return "The page the user is on, with its filters (checked by the server):\n" + guard.wrap_untrusted(
        "page_context", ctx)
