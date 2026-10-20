"""Browser check for the landing page's link-preview tags (B61, #108). Check ids: B61.n.

The tags come from the server that serves the built frontend (backend/app/link_preview.py), so this runs on the
built pairs only (E2E_BUILT=1, as CI runs it); the dev server serves index.html as it is. The backend tests check
each tag and rule (backend/tests/test_link_previews.py); this checks that a real browser still reads the page as
valid HTML with the tags in its head, and that the app still starts on `/` and `/about`.

The tags need a public https app address: run.sh's backends have none, so each test saves one as the owner (B26) and
removes it after. They also need the image in the build (frontend/public/link-preview/patch.png): until it is
committed, the check expects no tags and still checks that both pages load.
"""
import os
import pathlib

import pytest
from playwright.sync_api import Browser, Page, expect

from test_dashboard import api

pytestmark = pytest.mark.skipif(not os.environ.get("E2E_BUILT"), reason="the tags come from the built server (B12)")

PUBLIC = "https://patch.example.org"
IMAGE = pathlib.Path(__file__).resolve().parents[1] / "public" / "link-preview" / "patch.png"
HAS_IMAGE = IMAGE.is_file()


@pytest.fixture
def public_address(api_url: str):
    api(api_url, "/settings/server", "PUT", {"app_url": PUBLIC})
    yield PUBLIC
    api(api_url, "/settings/server", "PUT", {"app_url": None})


def head_metas(page: Page) -> dict[str, str]:
    """The <meta> tags the browser put in <head>: a tag the parser pushed into <body> (bad markup) wouldn't count."""
    return page.evaluate("""() => Object.fromEntries([...document.head.querySelectorAll('meta[property], meta[name]')]
        .map(m => [m.getAttribute('property') || m.getAttribute('name'), m.content]))""")


@pytest.mark.parametrize(("path", "heading"), [("/", "Dashboard"), ("/about", "About")])
def test_b61_8_the_landing_page_has_its_tags_in_head_and_the_app_still_starts(browser: Browser, ui_url, public_address,
                                                                               path, heading):
    ctx = browser.new_context()
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(ui_url + path)
    expect(page.get_by_role("heading", level=1, name=heading)).to_be_visible()  # React started on top of the tags
    expect(page).to_have_title("Patch, the LLM-security assistant")
    tags = head_metas(page)
    if HAS_IMAGE:
        assert tags["og:url"] == PUBLIC + path
        assert tags["og:title"] == "Patch, the LLM-security assistant"
        assert tags["twitter:card"] == "summary_large_image"
        image = page.request.get(ui_url + tags["og:image"].removeprefix(PUBLIC))  # the same file, from this server
        assert image.ok and image.headers["content-type"] == "image/png"
        assert len(image.body()) < 1_000_000
    else:
        assert not any(k.startswith("og:") for k in tags)  # no image in the build: no card (link_preview.py)
    assert errors == []
    ctx.close()


def test_b61_8_other_pages_get_no_tags(browser: Browser, ui_url, public_address):
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(ui_url + "/cves/CVE-2025-3248")
    expect(page.get_by_role("heading", level=1, name="CVE-2025-3248")).to_be_visible()
    assert not any(k.startswith(("og:", "twitter:")) or k == "description" for k in head_metas(page))
    ctx.close()
