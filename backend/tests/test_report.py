"""The evaluation report: one self-contained HTML page from saved runs. Check ids: A12.n, from ticket #14.

Built in CI from FakeLLM runs (plus a scripted bad model, so the failure list has something in it) and two fake
embedders. The real runs (OpenRouter, Ollama) are A20's, by hand.
"""
import re

import pytest

from app.evals import model_check, report, retrieval
from app.llm.base import LLMReply
from app.llm.fake import FakeLLM


class Lazy(FakeLLM):
    """Never calls a tool; its answer carries markup that must come out escaped."""
    name = "local"

    def label(self):
        return "Local · lazy-model"

    def step(self, messages, tools):
        return LLMReply(content="<script>alert(1)</script> Here you go [9].", cost=0.0)


@pytest.fixture
def runs(deps, knowledge, tmp_path):
    """A FakeLLM run, a lazy model's run, and retrieval runs for two fake embedders, all saved."""
    from app.rag.chunking import build_chunks
    from app.rag.embed import HashEmbedder
    from app.rag.keyword import BM25Index
    from app.rag.vector import build_index

    fake = model_check.start(deps, wait=True)
    real_llm = deps.llm
    deps.llm = Lazy()
    lazy = model_check.start(deps, ids=["Q2", "Q7"], wait=True)
    deps.llm = real_llm
    small = build_index(build_chunks(knowledge), HashEmbedder(dim=256), tmp_path / "small")
    big_r = retrieval.run(deps, deps.index, deps.keyword)
    small_r = retrieval.run(deps, small, BM25Index(small.chunks))
    return {"fake": fake, "lazy": lazy, "big": big_r, "small": small_r}


def page(deps, **kw) -> str:
    return report.from_store(report.store_of(deps.settings), as_of=deps.settings.as_of, **kw)


# --- A12.4: models side by side ----------------------------------------------------------------------------------

def test_a12_4_models_side_by_side_with_scores_cost_and_time(deps, runs):
    html = page(deps)
    models = section(html, "models")
    assert "FakeLLM (scripted)" in models and "Local · lazy-model" in models
    for label in ("Right tools", "Filters", "Key fact", "Real citations", "Cites sources", "Flagged",
                  "No exploit code", "Questions passed", "Cost", "Time per question"):
        assert label in models, label
    n = runs["fake"]["summary"]["questions"]
    assert f"{n} / {n}" in models and "0 / 2" in models  # FakeLLM passes all, the lazy model none
    assert "$0" in models  # FakeLLM and local models cost nothing


def test_a12_4_each_failure_with_what_the_model_did_and_what_was_expected(deps, runs):
    failures = section(page(deps), "failures")
    assert "Local · lazy-model" in failures and "Q2" in failures
    assert "lookup_cve, search_security" in failures and "no tool" in failures  # expected, got
    assert "FakeLLM (scripted)" not in failures or "No failures" in failures


def test_a12_4_model_output_is_escaped(deps, runs):
    html = page(deps)
    assert "<script>alert(1)" not in html and "&lt;script&gt;alert(1)" in html


# --- A12.4: embedders side by side -------------------------------------------------------------------------------

def test_a12_4_embedders_side_by_side_with_hit_rate_mrr_and_misses(deps, runs):
    emb = section(page(deps), "embedders")
    assert "hash-4096" in emb and "hash-256" in emb
    assert "Hit rate at 5" in emb and "MRR" in emb
    big = runs["big"]["modes"]["vector"]
    assert f"{big['hit_rate_at_5']:.2f}" in emb and f"{big['mrr']:.2f}" in emb
    miss = big["misses"][0]
    assert miss["question"] in emb  # the questions it missed are listed


def test_a12_4_the_latest_run_per_model_and_per_embedder_by_default(deps, runs):
    newer = retrieval.run(deps, deps.index, deps.keyword)
    html = page(deps)
    assert newer["id"] in html and runs["big"]["id"] not in html
    picked = page(deps, model_ids=[runs["lazy"]["id"]], retrieval_ids=[runs["small"]["id"]])
    assert "Local · lazy-model" in picked and "FakeLLM (scripted)" not in section(picked, "models")
    assert "hash-256" in picked and "hash-4096" not in section(picked, "embedders")


# --- A12.4: placeholders, findings, self-contained, design tokens ------------------------------------------------

def test_a12_4_placeholders_for_later_tickets_and_a_findings_section(deps, runs):
    html = page(deps)
    assert "Not run yet" in section(html, "explain-levels")  # A19 fills it
    assert "Not run yet" in section(html, "fix-first")  # A18 fills it
    assert "To be written" in section(html, "findings")
    written = page(deps, findings="<p>gpt-oss-120b passed 10 of 11 (checked).</p>")
    assert "gpt-oss-120b passed 10 of 11 (checked)." in section(written, "findings")


def test_a12_4_one_self_contained_page_styled_with_the_design_tokens(deps, runs):
    html = page(deps)
    assert html.startswith("<!doctype html>")
    assert not re.search(r"<link|<script[^>]+src=|@import|url\(", html)  # nothing loaded from elsewhere
    assert "--accent: #6c4cf5" in html and "[data-theme='dark']" in html  # tokens.css, light and dark
    assert 'data-design="playful"' in html
    assert 'aria-label="Switch to dark mode"' in html  # the theme button has a name


def test_a12_4_no_runs_still_builds_a_page(deps):
    html = page(deps)
    assert "No model-check runs saved yet" in html and "No retrieval runs saved yet" in html


# --- A12.5: the command line and the dev panel route -------------------------------------------------------------

def test_a12_5_the_fakellm_report_builds_from_the_command_line(tmp_path):
    from app.evals.__main__ import main

    out = tmp_path / "report.html"
    assert main(["fake-report", "--out", str(out)]) == 0
    html = out.read_text()
    assert "FakeLLM (scripted)" in html and "hash-4096" in html and "hash-256" in html
    assert "No failures" in section(html, "failures")


def test_a12_5_the_dev_panel_serves_the_report(client, runs):
    r = client.get("/dev/report")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "FakeLLM (scripted)" in r.text
    picked = client.get("/dev/report", params={"models": runs["lazy"]["id"], "retrieval": runs["small"]["id"]})
    assert "Local · lazy-model" in picked.text and "hash-4096" not in section(picked.text, "embedders")
    assert client.get("/dev/report", params={"models": "../../etc"}).status_code == 400


def section(html: str, sid: str) -> str:
    m = re.search(rf'<section id="{sid}".*?</section>', html, re.S)
    assert m, f"no section {sid}"
    return m.group(0)
