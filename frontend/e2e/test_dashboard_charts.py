"""Browser check (seam 3) for the dashboard's charts, side panels and Patch's welcome banner. Check ids: A05.n (#7).

Runs in Firefox and Chromium (run.sh). Expected numbers come from the backend's API (tested on its own in
backend/tests/test_dashboard.py); expected looks come from docs/design/DESIGN.md §5.4, §5.8, §7.1 and §8.2.
"""
import pytest
from playwright.sync_api import Page, expect

from test_dashboard import DESKTOP, PHONE, SHOTS, api, clean_state, open_dash  # noqa: F401 (fixtures)

SEV_LIGHT = {"CRITICAL": "rgb(46, 26, 128)", "HIGH": "rgb(82, 53, 214)", "MEDIUM": "rgb(123, 92, 255)",
             "LOW": "rgb(164, 139, 255)"}


def chart(page: Page, title: str):
    return page.get_by_role("region", name=title, exact=True)


BY_PRODUCT = "Open CVEs by product and severity"
PER_MONTH = "CVEs per month"
BY_OWASP = "Open CVEs by OWASP category"


# --- Open CVEs by product and severity (DESIGN.md §5.4) -----------------------------------------------------------

def test_a05_1_stacked_bars_per_product_with_severity_ramp_gaps_and_totals(open_dash, api_url):
    page = open_dash(reduced=True)
    data = api(api_url, "/dashboard")["by_product"]
    card = chart(page, BY_PRODUCT)
    expect(card.locator("svg .bar-row")).to_have_count(len(data))
    for i, p in enumerate(data):
        row = card.locator("svg .bar-row").nth(i)
        expect(row.locator(".axis-label")).to_have_text(p["name"])
        expect(row.locator(".value-label")).to_have_text(str(p["total"]))
        segs = row.locator(".fill").evaluate_all("""els => els.map(el => { const b = el.getBBox();
            return { sev: el.dataset.severity, x: b.x, w: b.width, fill: getComputedStyle(el).fill } })""")
        expected = [s for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW") if p[s] > 0]
        assert [s["sev"] for s in segs] == expected, p["name"]
        assert all(s["fill"] == SEV_LIGHT[s["sev"]] for s in segs)
        for a, b in zip(segs, segs[1:]):  # a 2px surface gap between touching segments
            assert abs(b["x"] - (a["x"] + a["w"]) - 2) < 0.6, (p["name"], a, b)
        if segs:  # the total sits just past the bar's end
            label_x = row.locator(".value-label").evaluate("el => el.getBBox().x")
            assert 0 < label_x - (segs[-1]["x"] + segs[-1]["w"]) < 12


# --- CVEs per month (DESIGN.md §5.4) -------------------------------------------------------------------------------

def test_a05_2_columns_per_month_in_series_1_with_labels_on_peaks(open_dash, api_url):
    page = open_dash(reduced=True)
    months = api(api_url, "/dashboard")["per_month"]
    card = chart(page, PER_MONTH)
    expect(card.locator("svg .hit")).to_have_count(len(months))  # one hover target per month
    expect(card.locator("svg .fill")).to_have_count(sum(m["count"] > 0 for m in months))
    fills = card.locator("svg .fill").evaluate_all("els => els.map(el => getComputedStyle(el).fill)")
    assert set(fills) == {"rgb(123, 92, 255)"}  # --series-1
    peak = max(m["count"] for m in months)
    labels = [int(t) for t in card.locator("svg .value-label").all_text_contents()]
    assert peak in labels and len(labels) <= 3, labels  # the peaks, not every column
    assert card.locator("svg .grid").first.evaluate("el => getComputedStyle(el).stroke") == "rgb(236, 238, 251)"
    axis = card.locator("svg .axis-label").first.evaluate("el => getComputedStyle(el).fontSize")
    value = card.locator("svg .value-label").first.evaluate("el => getComputedStyle(el).fontSize")
    assert axis == value == "11px"


# --- Open CVEs by OWASP category (DESIGN.md §5.4) ------------------------------------------------------------------

def test_a05_3_horizontal_bars_per_owasp_category(open_dash, api_url):
    page = open_dash(reduced=True)
    d = api(api_url, "/dashboard")
    card = chart(page, BY_OWASP)
    bars = card.locator("svg .fill")
    expect(bars).to_have_count(len(d["by_owasp"]))
    assert card.locator("svg .value-label").all_text_contents() == [str(o["count"]) for o in d["by_owasp"]]
    labels = card.locator("svg .axis-label").all_text_contents()
    assert all(lab.startswith(o["code"]) for lab, o in zip(labels, d["by_owasp"])), labels  # the code always shows
    boxes = bars.evaluate_all("els => els.map(el => [el.getBBox().x, getComputedStyle(el).fill])")
    assert len({round(b[0]) for b in boxes}) == 1  # every bar starts at the axis
    assert {b[1] for b in boxes} == {"rgb(123, 92, 255)"}
    if d["owasp_unmapped"]:
        expect(card.get_by_text(f"{d['owasp_unmapped']} open CVEs have no CWE in OWASP's lists")).to_be_visible()
