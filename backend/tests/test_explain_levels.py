"""Explain levels: simple, normal, deep dive (shortlist #2). Check ids: A19.n, from ticket #21.

Seams: the HTTP API (settings, chat), the readability score (a pure function), and the model check (FakeLLM only).
"""
import json
import re
import time

import pytest
from fastapi.testclient import TestClient

from app.evals import model_check, report
from app.evals.checks import score_levels
from app.evals.readability import flesch_reading_ease
from app.llm.fake import FakeLLM
from app.main import create_app
from app.schemas import ChatReply, Source, Usage


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


# --- A19.5: the model check asks one question at all three levels: exact checks, no LLM judge ----------------------

def src(n: int) -> Source:
    return Source(n=n, chunk_id=f"c{n}", doc_id=f"d{n}", doc_type="owasp_llm", title=f"T{n}", url="u", snippet="s")


def reply(answer: str, sources=(1, 2)) -> ChatReply:
    return ChatReply(answer=answer, sources=[src(n) for n in sources], tool_calls=[], query=None, usage=Usage(), steps=1)


EXPECT = {"contains_any": ["LLM01"], "cites": True, "levels": list(LEVELS)}
EASY = "LLM01 is a trick. Bad text tells the bot what to do. Keep it on a short leash [1] [2]."
MIDDLE = ("LLM01, prompt injection, happens when input changes the model's behaviour; constrain it and validate "
          "the output [1] [2].")
HARD = ("LLM01 exploits the absence of separation between instructions and data within the model's context window, "
        "enabling adversarial manipulation of privileged operations [1] [2].")


def checks_of(replies: dict) -> dict:
    return {c.name: c for c in score_levels(EXPECT, replies)}


def test_a19_5_all_three_levels_pass_when_fact_citations_and_readability_order_hold():
    got = checks_of({"simple": reply(EASY), "normal": reply(MIDDLE), "deep_dive": reply(HARD)})
    assert {"key_fact", "cites", "real_citations", "same_citations", "readability"} <= set(got)
    assert all(c.passed for c in got.values()), [c for c in got.values() if not c.passed]


def test_a19_5_a_level_missing_the_key_fact_fails_and_names_the_level():
    got = checks_of({"simple": reply(EASY.replace("LLM01", "It")), "normal": reply(MIDDLE), "deep_dive": reply(HARD)})
    assert not got["key_fact"].passed and "simple" in got["key_fact"].got


def test_a19_5_different_citations_at_one_level_fail():
    got = checks_of({"simple": reply(EASY.replace("[2]", "")), "normal": reply(MIDDLE), "deep_dive": reply(HARD)})
    assert not got["same_citations"].passed and "simple" in got["same_citations"].got


@pytest.mark.parametrize("order", [(MIDDLE, EASY, HARD), (EASY, HARD, MIDDLE), (HARD, MIDDLE, EASY)])
def test_a19_5_readability_must_be_easiest_for_simple_and_hardest_for_deep_dive(order):
    got = checks_of(dict(zip(LEVELS, (reply(t) for t in order))))
    assert not got["readability"].passed
    assert "simple" in got["readability"].got and "deep dive" in got["readability"].got  # the scores, by level


def run_check(client, body) -> dict:
    r = client.post("/dev/model-check", json=body)
    assert r.status_code == 200, r.text
    run = r.json()
    for _ in range(400):
        if run["status"] != "running":
            return run
        time.sleep(0.05)
        run = client.get(f"/dev/model-check/{run['id']}").json()
    raise AssertionError("the model check didn't finish")


def test_a19_5_fakellm_passes_the_explain_level_question_at_all_three_levels(client):
    run = run_check(client, {"ids": ["Q12"]})
    row = run["results"][0]
    assert row["passed"], row["failures"]
    assert row["checks"] == {"tools": True, "key_fact": True, "real_citations": True, "cites": True,
                             "same_citations": True, "readability": True}
    levels = row["levels"]
    assert list(levels) == list(LEVELS)
    assert levels["simple"]["reading_ease"] > levels["normal"]["reading_ease"] > levels["deep_dive"]["reading_ease"]
    assert levels["simple"]["cited"] == levels["deep_dive"]["cited"] != []
    assert all(lv["answer"] and lv["words"] > 0 for lv in levels.values())
    assert row["llm_calls"] >= 6  # three answers, two calls each at least


# --- A19.5: the report's readability section ----------------------------------------------------------------------

def report_section(html: str) -> str:
    found = re.search(r'<section id="explain-levels".*?</section>', html, re.S)
    assert found
    return found.group(0)


def test_a19_5_the_report_shows_reading_ease_words_and_citations_per_level(deps):
    run = model_check.start(deps, ids=["Q12"], wait=True)
    levels = run["results"][0]["levels"]
    html = report_section(report.from_store(report.store_of(deps.settings), as_of=deps.settings.as_of))
    assert "Not run yet" not in html and "FakeLLM (scripted)" in html
    for label in ("Simple", "Normal", "Deep dive", "Reading ease", "Words", "Cited"):
        assert label in html, label
    for lv in levels.values():
        assert f'{lv["reading_ease"]:.0f}' in html
    assert "✓" in html  # the order and citation checks passed


def test_a19_5_the_section_stays_a_placeholder_without_an_explain_level_run(deps):
    model_check.start(deps, ids=["Q1"], wait=True)
    html = report_section(report.from_store(report.store_of(deps.settings), as_of=deps.settings.as_of))
    assert "Not run yet" in html


def test_a19_5_answers_in_the_readability_section_are_escaped(deps):
    run = model_check.start(deps, ids=["Q12"], wait=True)
    run["model"] = "<b>m</b>"
    for lv in run["results"][0]["levels"].values():
        lv["answer"] = "<script>x</script>"
    html = report_section(report.build([run], [], as_of="2026-10-13"))
    assert "<script>x" not in html and "<b>m</b>" not in html and "&lt;b&gt;m&lt;/b&gt;" in html
