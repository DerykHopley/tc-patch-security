"""Explain levels: simple, normal, deep dive (shortlist #2). Check ids: A19.n, from ticket #21.

Seams: the HTTP API (settings, chat), the readability score (a pure function), and the model check (FakeLLM only).
"""
import json
import re

import pytest
from fastapi.testclient import TestClient

from app.evals.readability import flesch_reading_ease
from app.llm.fake import FakeLLM
from app.main import create_app


# --- A19.5: the readability score, on worked examples ------------------------------------------------------------

def test_a19_5_flesch_reading_ease_on_worked_examples():
    # 6 words, 1 sentence, 6 syllables: 206.835 - 1.015 * 6 - 84.6 * 1 = 116.145
    assert flesch_reading_ease("The cat sat on the mat.") == pytest.approx(116.145)
    # 4 words, 1 sentence, 13 syllables (at-tack-ers ex-ploit vul-ner-a-ble ap-pli-ca-tions):
    # 206.835 - 1.015 * 4 - 84.6 * 13 / 4 = -72.175
    assert flesch_reading_ease("Attackers exploit vulnerable applications.") == pytest.approx(-72.175)
    # 2 sentences of 3 words, 3 syllables each: 206.835 - 1.015 * 3 - 84.6 * 1 = 119.19
    assert flesch_reading_ease("Lock the door. Check the keys!") == pytest.approx(119.19)


def test_a19_5_citations_markdown_and_ids_do_not_count_as_words():
    plain = flesch_reading_ease("The cat sat on the mat.")
    assert flesch_reading_ease("**The cat** sat on the mat [1].") == pytest.approx(plain)


def test_a19_5_empty_text_has_no_score():
    assert flesch_reading_ease("") is None


# --- A19.1: the saved level: default normal, saved, validated ---------------------------------------------------

def test_a19_1_explain_level_defaults_to_normal(client):
    assert client.get("/settings").json()["settings"]["explain_level"] == "normal"


def test_a19_1_explain_level_is_saved_and_keeps_the_alert_rules(client):
    body = client.get("/settings").json()["settings"]
    body["explain_level"] = "deep_dive"
    assert client.put("/settings", json=body).json()["settings"]["explain_level"] == "deep_dive"
    again = client.get("/settings").json()["settings"]
    assert again["explain_level"] == "deep_dive" and again["alerts"] == body["alerts"]


@pytest.mark.parametrize("bad", ["expert", "", None, 2, "Simple"])
def test_a19_1_an_unknown_explain_level_is_400(client, bad):
    body = client.get("/settings").json()["settings"] | {"explain_level": bad}
    r = client.put("/settings", json=body)
    assert r.status_code == 400 and "explain_level" in r.json()["error"]["message"]


def test_a19_1_a_state_file_from_before_explain_levels_still_loads(settings, client):
    settings.state_path.write_text(json.dumps({"watchlist": [], "statuses": {}, "settings": {"alerts": {"kev": False}}}))
    s = client.get("/settings").json()["settings"]
    assert s["explain_level"] == "normal" and s["alerts"]["kev"] is False


# --- A19.2: the chat request's optional override; the reply says which level was used ----------------------------

LEVELS = ("simple", "normal", "deep_dive")
Q12 = "What is prompt injection and how do I prevent it?"


def save_level(client, level):
    body = client.get("/settings").json()["settings"] | {"explain_level": level}
    assert client.put("/settings", json=body).status_code == 200


def test_a19_2_without_an_override_the_saved_level_is_used(client):
    assert client.post("/chat", json={"message": Q12}).json()["explain_level"] == "normal"
    save_level(client, "simple")
    assert client.post("/chat", json={"message": Q12}).json()["explain_level"] == "simple"


def test_a19_2_an_override_applies_to_this_message_only(client):
    save_level(client, "simple")
    r = client.post("/chat", json={"message": Q12, "explain_level": "deep_dive"})
    assert r.status_code == 200 and r.json()["explain_level"] == "deep_dive"
    assert client.get("/settings").json()["settings"]["explain_level"] == "simple"  # the saved level is untouched
    assert client.post("/chat", json={"message": Q12, "explain_level": None}).json()["explain_level"] == "simple"


@pytest.mark.parametrize("bad", ["expert", "", "Deep dive", 3])
def test_a19_2_an_unknown_override_is_400(client, bad):
    r = client.post("/chat", json={"message": Q12, "explain_level": bad})
    assert r.status_code == 400 and "explain_level" in r.json()["error"]["message"]


# --- A19.3: one system-prompt line per level; tools, sources and citations unchanged ------------------------------

class SpyLLM(FakeLLM):
    """FakeLLM that keeps every message list it was given, to see what the model reads."""

    def __init__(self):
        super().__init__()
        self.seen: list[list[dict]] = []

    def step(self, messages, tools):
        self.seen.append([dict(m) for m in messages])
        return super().step(messages, tools)


def test_a19_3_the_system_prompt_differs_by_one_line_per_level(deps):
    spy = SpyLLM()
    deps.llm = spy
    client = TestClient(create_app(deps))
    prompts = {}
    for level in LEVELS:
        assert client.post("/chat", json={"message": Q12, "explain_level": level}).status_code == 200
        prompts[level] = spy.seen[-1][0]["content"].splitlines()
    base = [line for line in prompts["normal"] if line in prompts["simple"] and line in prompts["deep_dive"]]
    for level in LEVELS:
        extra = [line for line in prompts[level] if line not in base]
        assert len(extra) == 1 and len(prompts[level]) == len(base) + 1, extra
    assert "simple" in " ".join(prompts["simple"]).lower() and "deep dive" in " ".join(prompts["deep_dive"]).lower()


def test_a19_3_same_tools_sources_and_citations_at_every_level(client):
    replies = {level: client.post("/chat", json={"message": Q12, "explain_level": level}).json() for level in LEVELS}
    calls = {lv: [(t["name"], t["args"]) for t in r["tool_calls"]] for lv, r in replies.items()}
    sources = {lv: [s["chunk_id"] for s in r["sources"]] for lv, r in replies.items()}
    cited = {lv: sorted(set(re.findall(r"\[(\d+)\]", r["answer"]))) for lv, r in replies.items()}
    assert calls["simple"] == calls["normal"] == calls["deep_dive"] and calls["normal"]
    assert sources["simple"] == sources["normal"] == sources["deep_dive"] and sources["normal"]
    assert cited["simple"] == cited["normal"] == cited["deep_dive"] and cited["normal"]
    assert len({r["answer"] for r in replies.values()}) == 3  # only the wording changes
    assert all(r["bad_citations"] == [] for r in replies.values())
