"""The container's smoke test (B12, #34): the dashboard loads and the chat answers. Check ids: B12.n.

container.sh runs only this file, in Chromium, against the image on one port (UI_URL, with the API at UI_URL/api).
run.sh runs it too, against Vite and the API on their own ports: the same checks hold for both. Nothing here
changes state.
"""
import json
import re
import urllib.request

from playwright.sync_api import Page, expect

from test_chat import ask, open_chat


def test_b12_5_the_dashboard_loads_with_the_apis_numbers(page: Page, ui_url: str, api_url: str):
    with urllib.request.urlopen(f"{api_url}/dashboard") as r:
        kpis = json.load(r)["kpis"]
    page.goto(ui_url)
    expect(page.get_by_role("heading", level=1)).to_have_text("Dashboard")
    expect(page.locator(".tile .tile-value")).to_have_text([str(kpis[k]) for k in ("open", "critical", "kev", "new_30d")])
    expect(page.locator(".top-cves li").first).to_be_visible()


def test_b12_5_a_page_opened_by_its_address_is_that_page(page: Page, ui_url: str):
    """On one port /cves is also an API path: a reload or a link must get the page."""
    page.goto(f"{ui_url}/cves?product=langflow")
    expect(page.get_by_role("heading", level=1)).to_have_text("CVEs")
    expect(page.locator("table.cves tbody tr").first).to_be_visible()


def test_b12_6_the_chat_answers_with_a_tool_call(page: Page, ui_url: str):
    page.goto(ui_url)
    open_chat(page)
    answer = ask(page, "Explain CVE-2024-8309 and how to prevent that kind of bug")
    expect(answer).to_contain_text("CVE-2024-8309")
    expect(answer.get_by_role("button", name=re.compile(r"Show \d+ sources · 2 tool calls"))).to_be_visible()
