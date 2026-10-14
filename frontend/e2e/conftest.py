"""The browser check runs against servers that are already up (run.sh starts them).

UI_URL defaults to the throwaway pair on 5174, never the user's app on 5173: the checks change data.
"""
import os

import pytest

UI_URL = os.environ.get("UI_URL", "http://localhost:5174")
API_URL = os.environ.get("API_URL", "http://localhost:8001")


@pytest.fixture
def ui_url() -> str:
    return UI_URL


@pytest.fixture
def api_url() -> str:
    """The throwaway backend, for reading expected values and putting state back after a test."""
    return API_URL
