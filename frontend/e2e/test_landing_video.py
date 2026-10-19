"""Browser check for the launch video on the landing page (B47, #99). Check ids: B47.n.

The video sits between the four tiles and "See it working", at the front door and in About. Light and dark files
follow the theme like the screenshots. It never plays by itself and downloads nothing until it's played.
Playing itself isn't checked: Playwright's Chromium has no H.264 decoder. The browsers people use all play it.
"""
import pathlib
import re
import urllib.parse
import urllib.request

from playwright.sync_api import Page, expect

from test_landing import DESKTOP, PHONE, TITLE, landing
from test_shell import no_sideways_scroll, open_app, settled  # noqa: F401 (fixture)
from test_sign_in import open_signed_out  # noqa: F401 (fixture)

VIDEO_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "landing" / "video"
LINES = 6


def video(page: Page):
    return page.locator(".landing-video video")


def section_order(page: Page) -> list[str]:
    return page.locator(".landing > section").evaluate_all("els => els.map(e => e.className)")


# --- B47.1: where it is and how it behaves: after the tiles, never by itself, its text under it --------------------

def test_b47_1_the_video_sits_after_the_tiles_and_waits_to_be_played(open_signed_out):
    page, asked = landing(open_signed_out)
    order = section_order(page)
    assert order.index("landing-video") == order.index("landing-tiles") + 1, order
    assert order.index("landing-video") < order.index("landing-showcase"), order
    expect(page.get_by_role("heading", level=2, name="Patch in 20 seconds")).to_be_visible()
    v = video(page)
    expect(v).to_have_count(1)
    assert v.get_attribute("preload") == "none"
    assert v.get_attribute("autoplay") is None
    assert v.get_attribute("controls") is not None
    assert v.get_attribute("poster")
    assert v.evaluate("v => v.paused") is True
    assert (v.get_attribute("width"), v.get_attribute("height")) == ("1920", "1080")  # no layout jump
    lines = page.locator("#landing-video-lines li")
    expect(lines).to_have_count(LINES)
    assert v.get_attribute("aria-describedby") == "landing-video-lines"
    expect(v.locator("track[kind=captions]")).to_have_count(1)  # no speech: it says what the sound is
    page.get_by_text("The video as text").click()
    expect(lines.first).to_be_visible()
    assert [p for p in asked if p != "/health"] == []  # still no API call (B42.6)


def test_b47_1_nothing_downloads_until_play(open_signed_out):
    page, _ = landing(open_signed_out)
    fetched: list[str] = []
    page.on("request", lambda r: fetched.append(r.url) if ".mp4" in r.url else None)
    video(page).scroll_into_view_if_needed()
    expect(video(page)).to_be_in_viewport()
    page.wait_for_load_state("networkidle")
    assert fetched == []


def test_b47_1_about_has_it_too(open_app):  # noqa: F811
    page = open_app(query="/about")
    expect(page.get_by_role("heading", level=1, name="About")).to_be_visible()
    expect(video(page)).to_have_count(1)
    expect(page.get_by_role("heading", level=2, name=TITLE)).to_be_visible()


# --- B47.2: light and dark: the file and the poster follow the theme, and the switch -------------------------------

def test_b47_2_the_video_follows_the_theme(open_signed_out, ui_url):
    page, _ = landing(open_signed_out, scheme="dark")
    v = video(page)
    assert "-dark" in v.locator("source").get_attribute("src") and "-dark" in v.get_attribute("poster")
    page.get_by_role("button", name="Switch to light mode").click()
    expect(v.locator("source")).to_have_attribute("src", re.compile(r"patch-light"))
    expect(v).to_have_attribute("poster", re.compile(r"patch-light"))
    for attr in (v.locator("source").get_attribute("src"), v.get_attribute("poster")):
        with urllib.request.urlopen(urllib.parse.urljoin(ui_url + "/", attr)) as r:  # served, the right type
            assert r.status == 200 and r.headers["Content-Type"].split(";")[0] in ("video/mp4", "image/webp"), attr


def test_b47_2_the_files_are_small():
    sizes = {p.name: p.stat().st_size for p in VIDEO_DIR.iterdir()}
    assert sorted(sizes) == ["patch-dark.mp4", "patch-dark.webp", "patch-light.mp4", "patch-light.webp", "patch.vtt"], sizes
    assert all(size < 3_000_000 for n, size in sizes.items() if n.endswith(".mp4")), sizes
    assert all(size < 150_000 for n, size in sizes.items() if n.endswith(".webp")), sizes


# --- B47.3: phone and desktop, light and dark: it fits ------------------------------------------------------------

def test_b47_3_the_video_fits_a_phone_and_a_desktop(open_signed_out):
    for width, scheme in ((PHONE, "light"), (PHONE, "dark"), (DESKTOP, "light"), (DESKTOP, "dark")):
        page, _ = landing(open_signed_out, width=width, scheme=scheme)
        settled(page.locator(".landing"))
        assert no_sideways_scroll(page), (width, scheme)
        box = video(page).bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width, (width, scheme)
        assert abs(box["width"] / box["height"] - 16 / 9) < 0.02, box  # the poster's shape, before anything loads
