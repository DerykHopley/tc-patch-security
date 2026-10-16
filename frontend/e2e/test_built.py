"""The built frontend (E2E_BUILT=1, #72): run.sh serves what it was asked for. Check ids: B72.n.

Dev (the default): the Vite dev server, unbundled modules, the API on its own port. Built: one `vite build`, served
by each backend (FRONTEND_DIR) with the API under /api, as the container and Cloud Run serve it.
"""
import os
import urllib.request

import pytest

BUILT = bool(os.environ.get("E2E_BUILT"))


def _html(url: str) -> str:
    with urllib.request.urlopen(url) as r:
        return r.read().decode()


@pytest.mark.parametrize("pair", ["normal", "live"])
def test_b72_1_each_pair_serves_the_frontend_run_sh_was_asked_for(pair, ui_url, api_url, live_ui_url, live_api_url):
    ui, api = (ui_url, api_url) if pair == "normal" else (live_ui_url, live_api_url)
    html = _html(ui)
    if BUILT:
        assert "/@vite/client" not in html and "/assets/index-" in html  # bundled, no dev server
        assert api == f"{ui}/api"  # one origin: the API under /api, as the container serves it
    else:
        assert "/@vite/client" in html  # the dev server
        assert not api.startswith(ui)  # the API on its own port
    assert _html(f"{api}/health")  # the address the check uses for the API answers
