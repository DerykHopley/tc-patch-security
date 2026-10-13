"""Browser check of the UI against SPEC.md (U1–U10). Saved so it can be rerun (first-run finding 8).

Needs a backend with a fresh STATE_PATH (it marks CVEs fixed and resets data, so never point it at
your real state) and Vite pointing at it. Defaults: Vite on :5173. Then:
    uv run --with playwright python e2e/check_ui.py
or, for a second pair of servers: UI_URL=http://localhost:5174 uv run --with playwright python e2e/check_ui.py
Uses Firefox (installed with `uv run --with playwright playwright install firefox`). Screenshots go to screenshots/.
"""
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

URL = os.environ.get("UI_URL", "http://localhost:5173")
SHOTS = Path(__file__).resolve().parent.parent / "screenshots"
failures: list[str] = []


def check(name: str, fn) -> None:
    try:
        fn()
        print(f"PASS {name}")
    except Exception as e:  # noqa: BLE001 - report every check, then exit non-zero
        failures.append(name)
        print(f"FAIL {name}: {(str(e) or repr(e)).splitlines()[0][:200]}")


def ask(page, question: str):
    chat = page.locator(".chat-surface")
    button = chat.get_by_role("button", name=question, exact=True).first  # may be a suggestion and an example
    if not button.is_visible():
        chat.locator(".more-examples summary").click()
    button.click()
    reply = page.locator(".message.assistant").last
    expect(page.locator(".thinking")).to_have_count(0, timeout=10_000)
    return reply


def details(page, tab: str = "Sources"):
    """Open the last answer's inline details on one tab."""
    page.locator(".details-toggle").last.click()
    page.locator(".chat-details").last.get_by_role("tab", name=re.compile(f"^{tab}")).click()
    return page.locator(".chat-details").last


def run(scheme: str) -> None:
    with sync_playwright() as p:
        browser = p.firefox.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1000}, color_scheme=scheme)
        page.goto(URL)
        tag = f"[{scheme}]"

        check(f"{tag} U1 header and view switch", lambda: (
            expect(page.locator(".brand-name")).to_contain_text("LLM Security"),
            expect(page.get_by_role("button", name="Dashboard")).to_be_visible(),
            expect(page.locator(".side-card")).to_contain_text("Data as of 2026-10-13"),
        ))

        if scheme == "light":
            page.keyboard.press("Control+k")  # the side panel, over the dashboard

            def q1():
                r = ask(page, "Which critical Langflow vulnerabilities were published in 2026?")
                expect(r).to_contain_text("critical Langflow CVEs")
                d = details(page)
                expect(d.locator(".sources .sev-critical").first).to_be_visible()
                d.get_by_role("tab", name="Query plan").click()
                expect(d.locator(".chip", has_text="product: langflow")).to_be_visible()
            check("U2/U3/U5 Q1 answer, CVE sources, filters", q1)

            def q2():
                ask(page, "Explain CVE-2024-8309 and how to prevent that kind of bug")
                d = details(page, "Tool calls")
                expect(d.locator(".tool-card", has_text="lookup_cve")).to_contain_text("LangChain")
                expect(d.locator(".tool-card .result-card").first).to_contain_text("A05:2025 Injection")
            check("U4 Q2 CVE card", q2)

            def q4():
                ask(page, "What is AML.T0051 and which mitigations apply?")
                d = details(page, "Tool calls")
                expect(d.locator(".tool-card", has_text="explain_weakness")).to_contain_text("LLM01:2025 Prompt Injection")
            check("U4 Q4 weakness card", q4)

            def q6():
                r = ask(page, 'What does an "ignore previous instructions" attack look like?')
                expect(r.locator(".flag-note")).to_contain_text("looks like an injection attempt")
            check("U6 Q6 flagged, answered", q6)

            def q11():
                ask(page, "Look up CVE-1999-0001")
                expect(details(page, "Tool calls").locator(".tool-card.error")).to_contain_text("cve_not_in_snapshot")
            check("U4 Q11 tool error in red", q11)
            page.screenshot(path=SHOTS / "sec-chat.png")
            page.keyboard.press("Escape")

        page.get_by_role("button", name="Dashboard").click()

        def tiles():
            expect(page.locator(".tile").first).to_contain_text("Open CVEs")
            expect(page.locator(".tile.alert")).to_contain_text("Overdue since")
        check(f"{tag} U7 tiles", tiles)

        def charts():
            expect(page.locator(".chart svg")).to_have_count(3)
            expect(page.locator(".chart .fill.sev-critical").first).to_be_visible()
            page.locator(".chart .fill.sev-high").first.hover()
            expect(page.locator(".tooltip")).to_contain_text("High:")
        check(f"{tag} U8 charts and hover", charts)

        check(f"{tag} U9 side panels", lambda: (
            expect(page.locator(".incidents li")).to_have_count(5),
            expect(page.locator(".freshness li")).to_have_count(5),
            expect(page.locator("#watch-langflow")).to_be_checked(),
        ))
        page.mouse.move(0, 0)
        page.screenshot(path=SHOTS / f"sec-dashboard-{scheme}.png", full_page=True)

        if scheme == "light":
            def mark_fixed():
                before = int(page.locator(".tile-value").first.inner_text())
                first = page.locator("table.cves tbody tr").first
                cve = first.locator("a").first.inner_text()
                first.get_by_role("button", name="Mark fixed").click()
                expect(page.locator(".tile-value").first).to_have_text(str(before - 1))
                page.locator("#f-status").select_option("fixed")
                expect(page.locator("table.cves tbody tr").first).to_contain_text(cve)
                page.locator("#f-status").select_option("open")
            check("U7 mark fixed updates tiles and table", mark_fixed)

            def filters():
                page.locator("#f-product").select_option("ollama")
                page.locator("#f-severity").select_option("HIGH")
                expect(page.locator(".filters .meta")).to_contain_text("CVEs")
                rows = page.locator("table.cves tbody tr")
                expect(rows.first).to_contain_text("Ollama")
                page.locator("#f-product").select_option("")
                page.locator("#f-severity").select_option("")
            check("U7 table filters", filters)

            def ask_about():
                row = page.locator("table.cves tbody tr").first
                cve = row.locator("a").first.inner_text()
                row.get_by_role("button", name="Ask about this").click()
                expect(page.locator(".message.user").last).to_have_text(f"Explain {cve} and how to defend against it.")
                expect(page.locator(".thinking")).to_have_count(0, timeout=10_000)
                expect(page.locator(".message.assistant").last).to_contain_text("How to prevent this kind of bug")
                page.keyboard.press("Escape")
            check("U10 ask about this", ask_about)

            def watchlist():
                page.get_by_role("button", name="Dashboard").click()
                page.locator("#watch-vllm").check()
                page.get_by_role("button", name="Save watchlist").click()
                expect(page.locator(".dashboard > .meta")).to_contain_text("vLLM")
                page.locator("#watch-vllm").uncheck()
                page.get_by_role("button", name="Save watchlist").click()
                expect(page.locator(".dashboard > .meta")).not_to_contain_text("vLLM")
            check("U9 watchlist editor", watchlist)

            def settings_page():
                page.get_by_role("button", name="Settings", exact=True).click()
                expect(page.locator(".status-chip.saved").first).to_be_visible()
                page.locator("#al-min-sev").select_option("CRITICAL")
                expect(page.locator(".save-bar")).to_contain_text("Unsaved changes")
                page.get_by_role("button", name="Save changes").click()
                expect(page.locator(".save-bar")).to_contain_text("Saved")
                page.reload()
                page.get_by_role("button", name="Settings", exact=True).click()
                expect(page.locator("#al-min-sev")).to_have_value("CRITICAL")
            check("G2 settings save and persist", settings_page)

            def test_alert():
                expect(page.locator(".channels li")).to_have_count(3)
                page.get_by_role("button", name="Preview an alert (send nothing)").click()
                expect(page.locator(".push-preview")).to_contain_text("Test · In CISA KEV")
                expect(page.locator(".push-preview")).to_contain_text("nothing was sent")
                expect(page.locator(".alert-log li").first).to_contain_text("recorded only")
                email = page.locator(".channels li", has_text="Email")
                expect(email).to_contain_text("not set up")
                expect(email.get_by_role("button", name="Send test")).to_be_disabled()
            check("N1/N2 channels listed, preview recorded, unconfigured email can't send", test_alert)

            def reset_guard():
                btn = page.locator(".danger-btn")
                expect(btn).to_be_disabled()
                page.locator("#reset-confirm").fill("reset")
                expect(btn).to_be_enabled()
                page.locator("#reset-confirm").fill("")
            check("G4 reset needs the word", reset_guard)
            page.screenshot(path=SHOTS / "sec-settings.png", full_page=True)

            def dev_panel():
                page.get_by_role("button", name="Dev", exact=True).click()
                expect(page.locator(".panel:has(h3:text-is(\"Index\"))")).to_contain_text("1,680")
                page.locator("#dev-topn").fill("3")
                expect(page.locator("output[for=dev-topn]")).to_have_text("3")
                page.get_by_role("button", name="Save changes").click()
                expect(page.locator(".save-bar")).to_contain_text("Saved")
                page.get_by_role("button", name="How do I protect a RAG app from indirect prompt injection?").click()
                expect(page.locator(".play-col")).to_have_count(6)  # 4 queries + fused + final
                expect(page.locator(".play-col.final li")).to_have_count(3)
            check("X2/X3 dev panel changes search, playground shows each step", dev_panel)

            def embedding_map():
                expect(page.locator(".emap .qmark")).to_have_count(4)  # semantic query + 3 rewrites
                expect(page.locator(".emap .hit")).to_have_count(3)
                expect(page.locator(".emap .emap-link")).to_have_count(3)
                assert page.locator(".emap .pts > g").count() > 1600
                page.get_by_role("button", name="Show all").click()
                expect(page.get_by_role("button", name="Zoom to query")).to_be_visible()
                page.get_by_role("button", name=re.compile("^CVEs")).click()
                expect(page.locator(".emap .grp-cve.pts")).to_have_count(0)
                page.get_by_role("button", name=re.compile("^CVEs")).click()
            check("X5 embedding map with query overlay, zoom and group toggles", embedding_map)
            page.screenshot(path=SHOTS / "sec-dev.png", full_page=True)

            def model_check():
                page.get_by_role("button", name="Dev", exact=True).click()
                page.locator("#prov-local").check()
                page.get_by_role("button", name="LM Studio").click()
                expect(page.locator("#dev-local-url")).to_have_value("http://localhost:1234/v1")
                page.get_by_role("button", name="Discard").click()
                expect(page.locator("#prov-fake")).to_be_checked()
                page.get_by_role("button", name="Run model check").click()
                expect(page.locator(".eval-summary")).to_contain_text("11/11", timeout=20_000)
                expect(page.locator(".eval-table .verdict.pass")).to_have_count(11)
            check("M1/M2 provider choice, model check with FakeLLM passes 11/11", model_check)
            page.screenshot(path=SHOTS / "sec-model-check.png", full_page=True)

            def dev_applies_to_chat():
                page.keyboard.press("Control+k")
                new_chat = page.get_by_role("button", name="New chat")
                if new_chat.is_enabled():  # the settings check reloaded the page, which already cleared the chat
                    new_chat.click()
                ask(page, "How do I protect a RAG app from indirect prompt injection?")  # a suggestion on the dev page
                expect(details(page).locator(".sources li")).to_have_count(3)
                page.keyboard.press("Escape")
                page.get_by_role("button", name="Dev", exact=True).click()
                page.get_by_role("button", name="Reset to the SPEC's values").click()
                page.get_by_role("button", name="Save changes").click()
                expect(page.locator(".save-bar")).to_contain_text("Saved")
            check("X2 chat uses the saved search settings", dev_applies_to_chat)

            def narrow():
                page.set_viewport_size({"width": 420, "height": 900})
                for view in ("Dashboard", "Settings", "Dev", "Chat"):
                    if view == "Chat":
                        page.keyboard.press("Control+k")
                    else:
                        page.get_by_role("button", name=view, exact=True).click()
                    page.wait_for_timeout(500)
                    width = page.evaluate("document.documentElement.scrollWidth")
                    assert width <= 420, f"{view} is {width}px wide at a 420px viewport"
                    page.screenshot(path=SHOTS / f"sec-{view.lower()}-mobile.png", full_page=view == "Dashboard")
            check("All three pages and the chat fit a 420px viewport", narrow)
        browser.close()


def run_layouts() -> None:
    """L3: the bubble over the pages; enlarged, it pins beside the page. One conversation throughout."""
    with sync_playwright() as p:
        browser = p.firefox.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        def bubble():
            page.goto(URL)
            expect(page.locator(".tile").first).to_be_visible()
            expect(page.locator("#layout")).to_have_count(0)  # one layout, no picker
            expect(page.locator(".bubble-window")).to_have_count(0)
            expect(page.locator(".fab .robot")).to_be_visible()
            page.keyboard.press("Control+k")
            expect(page.locator(".bubble-window .context-chip")).to_have_text("on Dashboard")
            expect(page.locator(".fab .robot")).to_have_count(0)  # Patch steps off the button while it's open
            page.keyboard.press("Escape")
            expect(page.locator(".bubble-window")).to_have_count(0)
            page.locator("table.cves tbody tr").first.get_by_role("button", name="Ask about this").click()
            expect(page.locator(".bubble-window .message.assistant").last).to_contain_text("How to prevent", timeout=15_000)
            expect(page.locator(".tile").first).to_be_visible()  # the dashboard is still underneath
            page.locator(".bubble-window .details-toggle").last.click()
            expect(page.locator(".bubble-window .chat-details .source").first).to_be_visible()
        check("L3 bubble: Ctrl+K, Esc, Ask about this opens it over the dashboard, inline sources", bubble)

        def pin():
            expect(page.locator(".bubble-window .pin-btn")).to_have_count(0)  # only when enlarged
            page.get_by_role("button", name="Make larger").click()
            expect(page.locator(".bubble-window.expanded")).to_be_visible()
            page.get_by_role("button", name="Pin: dock the chat beside the page").click()
            expect(page.locator(".split-chat")).to_be_visible()
            expect(page.locator(".split-chat .pin-btn")).to_have_attribute("aria-pressed", "true")
            expect(page.locator(".split-chat .message.assistant")).to_have_count(1)  # same conversation
            expect(page.locator(".fab")).to_have_count(0)
            page.keyboard.press("Escape")  # pinned: Esc leaves it open
            expect(page.locator(".split-chat")).to_be_visible()
            before = page.locator(".split-chat").bounding_box()["width"]
            page.locator(".divider").focus()
            page.keyboard.press("ArrowLeft")
            page.keyboard.press("ArrowLeft")
            assert page.locator(".split-chat").bounding_box()["width"] > before + 30
            page.get_by_role("button", name="Settings", exact=True).click()
            expect(page.locator(".split-chat .context-chip")).to_have_text("on Settings")
        check("L3 enlarged bubble pins beside the page: Esc keeps it, resizable, follows the page", pin)

        def remembered():
            page.reload()
            expect(page.locator(".split-chat")).to_be_visible()  # pinned is remembered, and opens the chat
            page.get_by_role("button", name="Unpin: float the chat over the page").click()
            expect(page.locator(".bubble-window.expanded")).to_be_visible()  # back to the enlarged bubble
            expect(page.locator(".split-chat")).to_have_count(0)
            page.goto(URL + "/?layout=split")  # the old name still pins it
            expect(page.locator(".split-chat")).to_be_visible()
            page.goto(URL + "/?layout=drawer")  # and the other old names open the plain bubble
            expect(page.locator(".split-chat")).to_have_count(0)
            expect(page.locator(".fab")).to_be_visible()
        check("L3 pin is remembered; unpin floats it back enlarged; old ?layout= links still work", remembered)

        def phone():
            page.set_viewport_size({"width": 400, "height": 820})
            page.keyboard.press("Control+k")
            page.wait_for_timeout(300)  # let the pop-in animation finish
            box = page.locator(".bubble-window").bounding_box()
            assert box["width"] >= 399, box
            assert page.evaluate("document.documentElement.scrollWidth") <= 400
        check("L3 phone: the bubble is a full-screen sheet", phone)
        page.screenshot(path=SHOTS / "sec-layout-phone.png")
        browser.close()


def run_designs() -> None:
    """D5 Playful (the one design): pages and chat at desktop and phone widths, in light and dark; the theme toggle,
    the sidebar rail, Patch."""
    with sync_playwright() as p:
        browser = p.firefox.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        for theme in ("light", "dark"):
            def one(theme=theme):
                page.set_viewport_size({"width": 1400, "height": 900})
                page.goto(f"{URL}/?theme={theme}")
                expect(page.locator(".app.design-playful")).to_be_visible()
                expect(page.locator("html")).to_have_attribute("data-theme", theme)
                expect(page.locator(".tile").first).to_be_visible()
                expect(page.locator("#design")).to_have_count(0)  # one design, no picker
                page.get_by_role("button", name="Settings", exact=True).click()
                expect(page.locator(".status-chip").first).to_be_visible()
                page.keyboard.press("Control+k")
                expect(page.locator(".bubble-window .context-chip")).to_have_text("on Settings")
                assert page.evaluate("document.documentElement.scrollWidth") <= 1400, "wider than the window"
                page.keyboard.press("Escape")
                page.set_viewport_size({"width": 400, "height": 820})
                page.get_by_role("button", name="Dashboard", exact=True).click()
                expect(page.locator(".tile").first).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth") <= 400, "wider than a phone"
                page.screenshot(path=SHOTS / f"sec-playful-{theme}-phone.png")
            check(f"D playful, {theme}: pages, chat, desktop and phone widths", one)

        def collapse():
            page.set_viewport_size({"width": 1400, "height": 900})
            page.goto(URL + "/?design=clean")  # an old design link still opens the app (in Playful)
            expect(page.locator(".app.design-playful")).to_be_visible()
            page.get_by_role("button", name="Collapse the sidebar").click()
            page.wait_for_timeout(400)  # the width animates
            assert page.locator(".sidenav").bounding_box()["width"] < 100, page.locator(".sidenav").bounding_box()
            page.get_by_role("button", name="Dev", exact=True).click()  # labels hidden, names kept
            page.goto(URL)
            expect(page.locator(".topbar h1")).to_have_text("Dashboard")  # the blinking cursor is CSS, not text
            expect(page.get_by_role("button", name="Expand the sidebar")).to_be_visible()  # remembered
            page.get_by_role("button", name="Expand the sidebar").click()
        check("D collapse the sidebar rail (remembered); old ?design= links still open the app", collapse)

        def theme_toggle():
            page.goto(URL)
            start = page.evaluate("document.documentElement.dataset.theme")
            assert start in ("light", "dark"), start
            bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
            page.locator(".theme-btn").click()
            other = "dark" if start == "light" else "light"
            expect(page.locator("html")).to_have_attribute("data-theme", other)
            assert page.evaluate("getComputedStyle(document.body).backgroundColor") != bg, "the page didn't change colour"
            page.reload()
            expect(page.locator("html")).to_have_attribute("data-theme", other)  # remembered
            page.locator(".theme-btn").click()
            expect(page.locator("html")).to_have_attribute("data-theme", start)
        check("T light/dark toggle: switches, recolours the page, is remembered", theme_toggle)

        def patch_button():
            page.goto(URL)
            btn = page.locator(".fab")
            expect(btn).to_have_attribute("aria-label", "Ask Patch")
            expect(btn.locator(".robot")).to_be_visible()
            btn.click()
            expect(page.locator(".bubble-window .surface-title")).to_contain_text("Patch")
            expect(page.locator(".bubble-window .bot-greeting")).to_be_visible()
            expect(btn).to_have_attribute("aria-label", "Close the chat")
            btn.click()
            expect(page.locator(".bubble-window")).to_have_count(0)
        check("P Patch is the bubble button and fronts the chat", patch_button)

        def hello_close():
            page.goto(URL)
            expect(page.locator(".bot-hero")).to_be_visible()
            page.get_by_role("button", name="Close Patch's welcome").click()
            expect(page.locator(".bot-hero")).to_have_count(0)
            page.reload()
            expect(page.locator(".tile").first).to_be_visible()
            expect(page.locator(".bot-hero")).to_have_count(0)  # stays closed
        check("P Patch's welcome banner closes and stays closed", hello_close)
        browser.close()


if __name__ == "__main__":
    SHOTS.mkdir(exist_ok=True)
    if os.environ.get("ONLY") is None:  # ONLY=layouts or ONLY=designs runs just those checks
        run("light")
        run("dark")
    if os.environ.get("ONLY") in (None, "layouts"):
        run_layouts()
    if os.environ.get("ONLY") in (None, "designs"):
        run_designs()
    print(f"\n{len(failures)} failed" if failures else "\nAll UI checks passed")
    sys.exit(1 if failures else 0)
