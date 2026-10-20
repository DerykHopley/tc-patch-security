"""Link previews for the landing page only (B61, #108): Open Graph tags on `/` and `/about`, added by the server.

Seam: the HTTP app with FRONTEND_DIR set (as test_one_port.py). Link fetchers (Telegram, Slack, WhatsApp) read the
HTML and run no JavaScript, so the tags must be in what the server sends. Check ids: B61.n.
"""
import dataclasses
import re
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

INDEX = "<!doctype html><html><head><title>Patch</title></head><body><div id=root></div></body></html>"
PUBLIC = "https://patch.example.org"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64  # enough of a PNG for the server: it never decodes it


class Metas(HTMLParser):
    """Every <meta> in a page, by its property or name: {"og:title": "..."}."""

    def __init__(self, html: str):
        super().__init__()
        self.tags: dict[str, str] = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and (key := a.get("property") or a.get("name")):
            self.tags[key] = a.get("content")


def metas(html: str) -> dict[str, str]:
    return Metas(html).tags


@pytest.fixture
def dist(tmp_path):
    """A stand-in for frontend/dist, with the preview image where the build puts it."""
    d = tmp_path / "dist"
    (d / "link-preview").mkdir(parents=True)
    (d / "index.html").write_text(INDEX)
    (d / "link-preview" / "patch.png").write_bytes(PNG)
    return d


def site_for(settings, knowledge, index, dist, **changes) -> TestClient:
    from app.deps import build_deps

    return TestClient(create_app(build_deps(dataclasses.replace(settings, frontend_dir=dist, **changes),
                                            knowledge=knowledge, index=index)))


@pytest.fixture
def site(settings, knowledge, index, dist):
    """Deployed: APP_URL set in the environment to a public https address, as Cloud Run's env.yaml does."""
    return site_for(settings, knowledge, index, dist, app_url=PUBLIC, env_set=frozenset({"app_url"}))


@pytest.mark.parametrize(("path", "url"), [("/", f"{PUBLIC}/"), ("/about", f"{PUBLIC}/about")])
def test_b61_1_the_landing_page_carries_every_tag_with_absolute_urls(site, path, url):
    tags = metas(site.get(path).text)
    assert tags["og:title"] == "Patch, the LLM-security assistant"
    assert tags["og:type"] == "website"
    assert tags["og:site_name"] == "Patch"
    assert tags["og:url"] == url
    assert re.fullmatch(rf"{PUBLIC}/link-preview/patch\.png\?v=[0-9a-f]{{12}}", tags["og:image"])
    assert (tags["og:image:width"], tags["og:image:height"]) == ("1200", "630")
    assert tags["og:image:alt"]
    assert tags["twitter:card"] == "summary_large_image"
    assert tags["description"] == tags["og:description"]
    assert 40 < len(tags["og:description"]) <= 200  # 1-2 short sentences


def test_b61_1_a_trailing_slash_or_a_query_still_gets_the_tags_with_the_plain_address(site):
    """route.ts trims trailing slashes, so /about/ is About; the card names the page's own address, no query."""
    assert metas(site.get("/about/").text)["og:url"] == f"{PUBLIC}/about"
    assert metas(site.get("/?utm_source=telegram").text)["og:url"] == f"{PUBLIC}/"


@pytest.mark.parametrize("path", ["/dashboard", "/cves", "/cves/CVE-2025-3248", "/settings", "/dev", "/sign-in",
                                  "/nope", "/about/more"])
def test_b61_2_every_other_page_is_index_html_unchanged(site, path):
    r = site.get(path)
    assert r.status_code == 200
    assert r.text == INDEX


@pytest.mark.parametrize("app_url", ["http://localhost:5173", "https://localhost", "http://127.0.0.1:8000",
                                     "http://patch.example.org", "http://192.168.1.20:8000"])
def test_b61_3_no_tags_without_a_public_https_address(settings, knowledge, index, dist, app_url):
    """Locally (the default APP_URL is localhost) a card would point a fetcher at its own machine. A plain-http
    address isn't the deployed app (Cloud Run serves https), so it gets none either."""
    site = site_for(settings, knowledge, index, dist, app_url=app_url, env_set=frozenset({"app_url"}))
    assert site.get("/").text == INDEX


def test_b61_3_the_default_settings_give_no_tags(settings, knowledge, index, dist):
    assert site_for(settings, knowledge, index, dist).get("/about").text == INDEX


def test_b61_4_the_owners_saved_app_address_counts_from_the_first_request(settings, knowledge, index, dist):
    """B26: the environment's APP_URL, else the owner's saved one. A link fetcher may be the first visitor after a cold
    start, before any API call has synced the settings, so the page reads the setting itself."""
    r = site_for(settings, knowledge, index, dist).put("/api/settings/server", json={"app_url": PUBLIC})
    assert r.status_code == 200
    fresh = site_for(settings, knowledge, index, dist)  # a new process over the same state file
    assert metas(fresh.get("/").text)["og:url"] == f"{PUBLIC}/"


def test_b61_5_a_spoofed_host_header_never_reaches_the_tags(site):
    html = site.get("/", headers={"Host": "evil.example", "X-Forwarded-Host": "evil.example"}).text
    assert "evil.example" not in html
    assert metas(html)["og:url"] == f"{PUBLIC}/"


def test_b61_5_every_value_is_escaped(settings, knowledge, index, dist):
    """The saved address is checked only for its shape (B26), which lets a quote through: it must stay text."""
    odd = 'https://patch.example.org/x"><script>alert(1)</script>'
    html = site_for(settings, knowledge, index, dist, app_url=odd, env_set=frozenset({"app_url"})).get("/").text
    assert "<script>" not in html
    assert metas(html)["og:url"] == odd + "/"


def test_b61_6_the_image_is_served_as_a_png_with_a_long_cache(site):
    image = metas(site.get("/").text)["og:image"]
    r = site.get(image.removeprefix(PUBLIC))
    assert r.status_code == 200
    assert r.content == PNG
    assert r.headers["content-type"] == "image/png"
    assert "max-age=31536000" in r.headers["cache-control"]


def test_b61_6_a_new_image_gets_a_new_address(site, dist):
    """Chat apps cache the image by its address: the hash in it changes with the image."""
    before = metas(site.get("/").text)["og:image"]
    (dist / "link-preview" / "patch.png").write_bytes(PNG + b"new")
    assert metas(site.get("/").text)["og:image"] != before


def test_b61_7_no_tags_while_the_image_isnt_in_the_build(site, dist):
    """Open Graph requires og:image (docs/SOURCE-CHECKS.md): without the image the page gets no tags rather than a
    card that points at a missing file."""
    (dist / "link-preview" / "patch.png").unlink()
    assert site.get("/").text == INDEX
