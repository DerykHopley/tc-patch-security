"""Live mode reads the real feeds by default (B28, #74). Check ids: B28.n.

Seams: the settings and `make_feeds` (which feeds the app and the CLI build), the conftest guard (no test reaches
the real services), the HTTP API (the owner sees which feeds; a live folder of the other kind is refused) and the CLI
(the schedule in snapshot mode). No test calls the network: the real feeds are only ever built, never asked.
"""
import json

import pytest

from app.config import Settings
from app.feeds import FakeFeeds, FeedUrls, HttpFeeds, make_feeds


# --- B28.1: FEEDS defaults to real, in code and from the environment -------------------------------------------

@pytest.mark.builds_real_feeds
def test_b28_1_feeds_default_to_the_real_services(monkeypatch):
    monkeypatch.delenv("FEEDS", raising=False)
    assert Settings().feeds == "real" and Settings.from_env().feeds == "real"
    feeds = make_feeds(Settings())
    assert isinstance(feeds, HttpFeeds) and feeds.urls == FeedUrls()
    assert isinstance(make_feeds(Settings(feeds="fake")), FakeFeeds)  # tests, run.sh and container.sh say fake


# --- B28.2: the conftest guard fails a test that builds the real feeds ------------------------------------------

def test_b28_2_building_the_real_feeds_without_the_fake_server_fails_the_test():
    with pytest.raises(pytest.fail.Exception, match="real feeds"):
        make_feeds(Settings())


def test_b28_2_the_fake_http_server_is_allowed(fake_http):
    assert HttpFeeds(urls=FeedUrls.at(fake_http.url)).urls.nvd.startswith("http://127.0.0.1")


@pytest.mark.builds_real_feeds
def test_b28_2_even_a_marked_test_cannot_ask_a_real_service():
    with pytest.raises(pytest.fail.Exception, match="network"):
        make_feeds(Settings()).kev()
