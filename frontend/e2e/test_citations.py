"""Browser check (seam 3) for the citation check and the cost under each answer. Check ids: A08.6, from ticket #10.

FakeLLM never cites a missing source, so the answers with bad citations are served by a Playwright route.
Expected values come from the ticket and docs/design/DESIGN.md (quiet = muted text, 4.5:1 in both themes).
"""
import pytest
from playwright.sync_api import Page, expect

from test_chat import Q3, ask, last_answer, open_chat, send, window
from test_shell import DESKTOP, PHONE, SHOTS, contrast, no_sideways_scroll, open_app  # noqa: F401 (fixture)

SOURCE = {"n": 1, "chunk_id": "LLM01#0", "doc_id": "LLM01", "doc_type": "owasp_llm", "title": "LLM01 Prompt Injection",
          "section": None, "date": None, "url": "https://genai.owasp.org/llmrisk/llm01-prompt-injection/",
          "snippet": "Prompt injection…", "score": 0.5, "product": None, "severity": None, "cvss": None, "kev": None}


def reply(answer: str, bad: list[int], no_citations: bool, cost: float) -> dict:
    return {"answer": answer, "sources": [SOURCE], "tool_calls": [], "query": None, "steps": 2, "flags": [],
            "usage": {"input_tokens": 1234, "output_tokens": 56, "llm_calls": 3, "estimated": False, "cost": cost},
            "bad_citations": bad, "no_citations": no_citations}


def serve(page: Page, body: dict) -> None:
    page.route("**/chat", lambda route: route.fulfill(status=200, headers={"Access-Control-Allow-Origin": "*"}, json=body))


def colour(loc, prop: str = "color") -> str:
    return loc.evaluate(f"el => getComputedStyle(el).{prop}")


def test_a08_6_fakellm_answer_shows_its_cost_and_no_citation_note(open_app):
    page = open_app()
    open_chat(page)
    answer = ask(page, Q3)
    expect(answer.locator(".usage")).to_contain_text("$0")
    expect(answer.locator(".cite-note")).to_have_count(0)


def test_a08_6_cost_shown_with_the_token_counts(open_app):
    page = open_app()
    open_chat(page)
    serve(page, reply("Treat retrieved text as data [1].", [], False, 0.000612))
    send(page, "hi")
    expect(last_answer(page).locator(".usage")).to_have_text("1,234 in · 56 out · 3 LLM calls · 2 steps · $0.00061")


def test_a08_6_removed_citations_are_listed_quietly(open_app):
    page = open_app()
    open_chat(page)
    serve(page, reply("Treat retrieved text as data [1].", [42, 77], False, 0.0))
    send(page, "hi")
    note = last_answer(page).locator(".cite-note")
    expect(note).to_have_text("Removed citations [42] [77]: no matching source.")
    expect(last_answer(page).locator("a.cite")).to_have_count(1)


def test_a08_6_no_sources_cited_note(open_app):
    page = open_app()
    open_chat(page)
    serve(page, reply("Treat retrieved text as data.", [], True, 0.0))
    send(page, "hi")
    expect(last_answer(page).locator(".cite-note")).to_have_text("No sources cited.")


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a08_6_notes_are_quiet_and_readable_in_light_and_dark(open_app, browser_name, width, scheme):
    page = open_app(width=width, scheme=scheme, reduced=True)
    open_chat(page)
    serve(page, reply("Treat retrieved text as data.", [9], True, 0.0012))
    send(page, "hi")
    answer = last_answer(page)
    note = answer.locator(".cite-note")
    expect(note).to_have_text("No sources cited. Removed citation [9]: no matching source.")
    muted = page.evaluate("(() => { const d = document.createElement('div'); d.style.color = 'var(--muted)'; "
                          "document.body.append(d); const c = getComputedStyle(d).color; d.remove(); return c })()")
    assert colour(note) == muted  # quiet: muted text, not the warning colours of the flag note
    assert colour(note, "backgroundColor") in ("rgba(0, 0, 0, 0)", "transparent")
    assert contrast(colour(note), colour(answer, "backgroundColor")) >= 4.5
    assert contrast(colour(answer.locator(".usage")), colour(answer, "backgroundColor")) >= 4.5
    assert no_sideways_scroll(page)
    expect(window(page)).to_be_visible()
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"a08-{browser_name}-{width}-{scheme}-citations.png")
