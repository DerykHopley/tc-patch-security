"""Slow mode (E2E_LATENCY_MS, conftest.py) delays the API. Check ids: A56.n, from ticket #56."""
import pytest

from conftest import LATENCY_MS
from test_shell import open_app  # noqa: F401 (fixture)


@pytest.mark.skipif(not LATENCY_MS, reason="slow mode is off (set E2E_LATENCY_MS)")
def test_a56_3_slow_mode_delays_every_api_response(open_app, api_url):  # noqa: F811
    page = open_app()
    took = page.evaluate("""async url => {
        const t = performance.now();
        await Promise.all([fetch(url + '/health'), fetch(url + '/health')]);
        return performance.now() - t;
    }""", api_url)
    assert LATENCY_MS <= took < 2 * LATENCY_MS + 1000  # delayed, and side by side rather than one after the other
