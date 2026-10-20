"""The wait helper settled() (test_shell.py) on pages of its own: no servers. Check ids: B100.n, from issue #100.

An element can be replaced while it animates: the signed-out front door remounts `.landing` just after its heading
shows (#100). settled() must then wait for the new element, not pass at once on the detached old one.
"""
import pytest
from playwright.sync_api import Error, Page

from test_shell import settled

# One box fading in. `swap` replaces it with a new box, which fades in from the start.
PAGE = """<!doctype html>
<style>
  @keyframes up { from { opacity: 0 } }
  .box { width: 100px; height: 100px; background: purple; animation: up var(--d) linear both }
  .spin { animation: up 1s linear infinite }
</style>
<div id="root"><div class="box" style="--d: 1s">old</div></div>
<script>
  function swap(ms) { document.getElementById('root').innerHTML = `<div class="box" style="--d: ${ms}ms">new</div>` }
</script>"""


def finished(page: Page) -> bool:
    return page.locator(".box").evaluate(
        "el => el.getAnimations().every(a => a.playState === 'finished') && getComputedStyle(el).opacity === '1'")


# --- B100.1: an element replaced mid-animation: settled() waits for the new one ----------------------------------

def test_b100_1_settled_waits_for_the_element_that_replaced_the_one_it_found(page: Page):
    page.set_content(PAGE)
    page.evaluate("setTimeout(() => swap(600), 200)")  # mid-way through the old box's 1 s fade
    settled(page.locator(".box"))
    assert page.locator(".box").inner_text() == "new"
    assert finished(page)  # before the fix: the detached old box had no animations, so it passed at ~200 ms


# --- B100.2: an element that stays: settled() as before; endless animations don't count -------------------------

def test_b100_2_an_element_that_stays_settles_and_endless_animations_are_ignored(page: Page):
    page.set_content(PAGE)
    page.evaluate("document.querySelector('.box').insertAdjacentHTML('beforeend', '<i class=\"spin\">.</i>')")
    settled(page.locator(".box"))
    assert page.locator(".box").inner_text().startswith("old")
    assert page.locator(".box").evaluate("el => getComputedStyle(el).opacity") == "1"


# --- B100.3: an element that leaves and never comes back: a timeout, never a pass --------------------------------

def test_b100_3_an_element_that_leaves_for_good_times_out(page: Page):
    page.set_content(PAGE)
    page.evaluate("setTimeout(() => document.getElementById('root').replaceChildren(), 100)")
    with pytest.raises(Error):  # Playwright's TimeoutError is an Error
        settled(page.locator(".box"), timeout=1000)
