"""One port for the API and the built frontend (B12, #34): the container's way of serving the app.

Seam: the HTTP app. With FRONTEND_DIR set, the API moves under /api and every other path is the frontend. Check ids:
B12.n.
"""
import dataclasses

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

INDEX = "<!doctype html><title>Patch</title><div id=root></div>"


@pytest.fixture
def dist(tmp_path):
    """A stand-in for frontend/dist: what `npm run build` writes."""
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text(INDEX)
    (d / "assets" / "index-abc123.js").write_text("console.log('patch')")
    (d / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("outside the build")
    return d


@pytest.fixture
def site(settings, knowledge, index, dist):
    from app.deps import build_deps

    return TestClient(create_app(build_deps(dataclasses.replace(settings, frontend_dir=dist), knowledge=knowledge,
                                            index=index)))


def test_b12_1_the_api_answers_under_api(site, client):
    """The same answers as the API on its own port (`client`, without FRONTEND_DIR), one level down."""
    for path in ["/dashboard", "/cves?limit=3", "/settings", "/watchlist"]:
        r = site.get("/api" + path)
        assert r.status_code == 200, path
        assert r.json() == client.get(path).json(), path


def test_b12_1_health_answers_at_the_root_and_under_api(site):
    assert site.get("/health").json()["status"] == "ok"  # for the CI smoke test and Cloud Run's start-up probe
    assert site.get("/api/health").json() == site.get("/health").json()


@pytest.mark.parametrize("path", ["/", "/cves", "/cves?product=langflow", "/settings", "/dev", "/settings/"])
def test_b12_2_every_page_path_is_the_frontend(site, path):
    """The frontend's pages share names with API routes (/cves, /settings, /dev): a reload must get the page."""
    r = site.get(path)
    assert r.status_code == 200
    assert r.text == INDEX
    assert r.headers["content-type"].startswith("text/html")


def test_b12_2_an_unknown_api_path_is_a_json_404_not_the_page(site):
    r = site.get("/api/nothing-here")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


def test_b12_3_built_files_are_served(site):
    assert site.get("/assets/index-abc123.js").text == "console.log('patch')"
    assert site.get("/favicon.svg").text == "<svg/>"


def test_b12_3_a_path_outside_the_build_is_never_served(site):
    for path in ["/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"]:
        assert "outside the build" not in site.get(path).text


def test_b12_4_without_frontend_dir_the_api_stays_at_the_root(client):
    """Local runs and the browser check (Vite on its own port) are unchanged."""
    assert client.get("/cves?limit=1").headers["content-type"].startswith("application/json")
    assert client.get("/api/health").status_code == 404


def test_b12_4_a_frontend_dir_that_isnt_built_fails_at_start_up(settings, knowledge, index, tmp_path):
    from app.config import ConfigError
    from app.deps import build_deps

    with pytest.raises(ConfigError, match="npm run build"):
        create_app(build_deps(dataclasses.replace(settings, frontend_dir=tmp_path / "missing"), knowledge=knowledge,
                              index=index))


def test_b12_4_frontend_dir_from_the_environment(monkeypatch, tmp_path):
    from app.config import ROOT, Settings

    monkeypatch.delenv("FRONTEND_DIR", raising=False)
    assert Settings.from_env().frontend_dir is None
    monkeypatch.setenv("FRONTEND_DIR", "../frontend/dist")
    assert Settings.from_env().frontend_dir == ROOT / "../frontend/dist"
