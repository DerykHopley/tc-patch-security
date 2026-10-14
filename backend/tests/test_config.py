"""Settings come from the environment; .env.example lists every one. Check ids: A01.n."""
import dataclasses
import re

import pytest

from app.config import ROOT, ConfigError, Settings


def test_a01_6_settings_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", " Fake ")
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "s.json"))
    monkeypatch.setenv("AS_OF", "2026-11-01")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5174, http://example.test")
    s = Settings.from_env()
    assert (s.llm_provider, s.state_path, s.as_of) == ("fake", tmp_path / "s.json", "2026-11-01")
    assert s.cors_origins == ["http://localhost:5174", "http://example.test"]


def test_a01_6_defaults_without_environment(monkeypatch):
    for name in ("LLM_PROVIDER", "STATE_PATH", "AS_OF", "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    s = Settings.from_env()
    assert s.llm_provider == "fake"
    assert s.as_of == "2026-10-13"  # empty AS_OF = the snapshot date
    assert s.state_path == ROOT / "data" / "state.json"


def test_a01_6_relative_state_path_is_under_the_backend(monkeypatch):
    monkeypatch.setenv("STATE_PATH", "data/other.json")
    assert Settings.from_env().state_path == ROOT / "data" / "other.json"


def test_a01_6_unknown_provider_fails_with_a_plain_message():
    with pytest.raises(ConfigError, match="LLM_PROVIDER must be one of fake, openrouter, local, not 'gpt'"):
        Settings(llm_provider="gpt").check()


def test_a01_7_env_example_lists_every_setting():
    listed = set(re.findall(r"^([A-Z_]+)=", (ROOT / ".env.example").read_text(), re.M))
    assert listed == {f.name.upper() for f in dataclasses.fields(Settings)}


def test_a01_7_env_example_holds_no_values_that_look_like_keys():
    for line in (ROOT / ".env.example").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            name, value = line.split("=", 1)
            assert not re.search(r"(sk-|key|token|secret|password)", value, re.I), name


@pytest.mark.parametrize(("value", "expected"), [("true", True), (" 1 ", True), ("yes", True), ("false", False), ("0", False), ("", True)])
def test_a02_1_dev_panel_from_environment(monkeypatch, value, expected):
    monkeypatch.setenv("DEV_PANEL", value)
    assert Settings.from_env().dev_panel is expected
