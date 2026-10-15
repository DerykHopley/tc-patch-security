"""The CVE view (app.cve_filters.CveView): the CVEs page's filters under one set of names, the same in the URL, GET
/cves, the chat's page context, WatchedCves.rows and prioritise.

Round trips: a dict (a query string or the page context) → the view → the rows it filters. Old /cves names
(severity_min, published_since) are aliases: they give the same rows as the new names.
Expected values are the frozen snapshot's facts (as-of 2026-10-13), checked by hand.
"""
import pytest

from app.cve_filters import CveView, InvalidFilter
from app.state import State
from app.watched import WatchedCves

AS_OF = "2026-10-13"


@pytest.fixture
def watched(tmp_path, knowledge):
    state = State(tmp_path / "state.json", knowledge)  # the default watchlist
    state.set_status("CVE-2025-3248", "fixed", AS_OF)  # Langflow
    return WatchedCves(knowledge, state, AS_OF)


def parse(knowledge, raw):
    return CveView.parse(raw, knowledge.resolve_product)


def ids(rows):
    return [r["id"] for r in rows]


# --- dict → view: each filter normalised -------------------------------------------------------------------------

@pytest.mark.parametrize("raw,view", [
    ({}, CveView()),
    ({"product": "LangFlow"}, CveView(product="langflow")),
    ({"product": "Ollama,langflow,ollama"}, CveView(product="ollama,langflow")),
    ({"severity": "high"}, CveView(severity="HIGH")),
    ({"status": "all"}, CveView(status="all")),
    ({"kev": "1"}, CveView(kev=True)),
    ({"kev": "true"}, CveView(kev=True)),
    ({"kev": True}, CveView(kev=True)),
    ({"kev": "false"}, CveView(kev=False)),
    ({"since": "2026-09-14"}, CveView(since="2026-09-14")),
    ({"verdict": "affected"}, CveView(verdict="affected")),
    ({"severity_min": "critical", "published_since": "2025-01-01"}, CveView(severity="CRITICAL", since="2025-01-01")),
    ({"severity": "", "limit": "5", "page": "cves"}, CveView()),  # empty: no filter; other keys: not the view's
])
def test_a_dict_becomes_the_view(knowledge, raw, view):
    assert parse(knowledge, raw) == view


@pytest.mark.parametrize("raw,message", [
    ({"product": "notion"}, "'notion' isn't a product I track."),
    ({"product": "langflow,notion"}, "'notion' isn't a product I track."),
    ({"severity": "huge"}, "severity must be LOW, MEDIUM, HIGH or CRITICAL."),
    ({"severity_min": "huge"}, "severity_min must be LOW, MEDIUM, HIGH or CRITICAL."),  # named as it was sent
    ({"status": "closed"}, "status must be open, fixed, not_affected, accepted or all."),
    ({"kev": "maybe"}, "kev must be true or false."),
    ({"since": "last-week"}, "since must be a date, YYYY-MM-DD."),
    ({"published_since": "2026-02-30"}, "published_since must be a date, YYYY-MM-DD."),
    ({"verdict": "maybe"}, "verdict must be affected, not_affected or unknown."),
])
def test_a_bad_value_names_its_filter(knowledge, raw, message):
    with pytest.raises(InvalidFilter) as e:
        parse(knowledge, raw)
    assert str(e.value) == message


# --- view → rows: each filter narrows WatchedCves.rows ----------------------------------------------------------

def test_the_view_filters_the_rows(knowledge, watched):
    rows = lambda raw: watched.rows(**parse(knowledge, raw).filters())  # noqa: E731
    assert ids(rows({"product": "langflow,ollama"})) == ids(watched.rows(product="langflow,ollama"))
    assert {r["product"] for r in rows({"product": "langflow,ollama"})} == {"langflow", "ollama"}
    assert rows({"severity": "critical"}) and all(r["severity"] == "CRITICAL" for r in rows({"severity": "critical"}))
    kev = rows({"kev": "1", "status": "all"})
    assert len(kev) == 9 and all(r["kev"] for r in kev)  # the KEV tile
    assert not any(r["kev"] for r in rows({"kev": "false"}))
    new = rows({"status": "all", "since": "2026-09-14"})
    assert new and all(r["published"] >= "2026-09-14" for r in new)
    assert all(r["verdict"] == "unknown" for r in rows({"verdict": "unknown"}))
    assert "CVE-2025-3248" not in ids(rows({})) and "CVE-2025-3248" in ids(rows({"status": "all"}))  # open by default
    assert ids(rows({"status": "fixed"})) == ["CVE-2025-3248"]
    assert ids(rows({})) == ids(watched.rows())


# --- GET /cves: the new names, and the old ones as aliases ---------------------------------------------------------

@pytest.mark.parametrize("new,old", [
    ("severity=HIGH", "severity_min=HIGH"),
    ("since=2026-09-14&status=all", "published_since=2026-09-14&status=all"),
    ("product=langflow&severity=critical&since=2025-01-01", "product=langflow&severity_min=critical&published_since=2025-01-01"),
])
def test_cves_takes_the_new_names_and_the_old_ones_as_aliases(client, new, old):
    by_new = client.get(f"/cves?limit=200&{new}").json()
    by_old = client.get(f"/cves?limit=200&{old}").json()
    assert by_new["total"] > 0 and by_new == by_old
    assert by_new != client.get("/cves?limit=200").json()  # the filter did narrow it


def test_cves_takes_the_urls_kev_1(client):
    assert client.get("/cves?kev=1&limit=200").json() == client.get("/cves?kev=true&limit=200").json()


def test_cves_names_a_bad_filter_in_a_plain_400(client):
    r = client.get("/cves?since=last-week")
    assert r.status_code == 400 and r.json()["error"]["message"] == "since must be a date, YYYY-MM-DD."
    r = client.get("/cves?kev=maybe")
    assert r.status_code == 400 and r.json()["error"]["message"] == "kev must be true or false."


# --- the page context: the same names, so it is a view as it stands ---------------------------------------------

def test_the_page_context_is_a_view(knowledge, watched):
    ctx = {"page": "cves", "product": "langflow", "severity": "HIGH", "status": "all", "kev": True,
           "since": "2025-01-01", "cve": "CVE-2025-3248"}
    view = parse(knowledge, ctx)
    assert view == CveView(product="langflow", severity="HIGH", status="all", kev=True, since="2025-01-01")
    assert all(r["product"] == "langflow" and r["kev"] for r in watched.rows(**view.filters()))
