"""The browser check runs against servers that are already up (run.sh starts them).

UI_URL defaults to the throwaway pair on 5174, never the user's app on 5173: the checks change data.
"""
import os

import pytest

UI_URL = os.environ.get("UI_URL", "http://localhost:5174")


@pytest.fixture
def ui_url() -> str:
    return UI_URL
