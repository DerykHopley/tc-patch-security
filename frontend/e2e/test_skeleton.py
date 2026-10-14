"""Browser check (seam 3), run in Firefox and Chromium. Check ids: A01.n, from ticket #3."""
from playwright.sync_api import Page, expect


def test_a01_8_page_loads_and_shows_the_as_of_date(page: Page, ui_url: str):
    page.goto(ui_url)
    expect(page).to_have_title("Patch, the LLM-security assistant")
    expect(page.get_by_text("Data as of 2026-10-13")).to_be_visible()
