"""The shared reduced-motion check (DESIGN.md §7.2): with `prefers-reduced-motion: reduce` nothing moves, anywhere.

Each ticket that adds motion adds a *scene* in its own test file: a function that drives its part of the app into the
states that would animate with normal motion and calls `still()`, which checks that no CSS animation or transition
runs. Mark it `@scene`: the file then gets one `test_reduced_motion_nothing_moves[<scene>]` per scene, in each browser
of the run, from the defaults (state, settings, decision history, dev settings) and back to them afterwards. No
shared list to edit, so parallel tickets don't conflict (spec B retro, finding 3). A scene's name is its check id.

    from reduced_motion import scene, still

    @scene
    def b99_4_my_card(fx):  # fx(name) is request.getfixturevalue: this file's fixtures, and conftest's
        page = fx("open_app")(reduced=True)
        still(page, "my card")

The "normal motion does move" checks stay ordinary tests in their ticket's file.
"""
import sys
from collections.abc import Callable

import pytest
from playwright.sync_api import Page

RUNNING = "document.getAnimations().map(a => a.animationName || a.transitionProperty || 'script animation')"
TEST = "test_reduced_motion_nothing_moves"


def still(page: Page, where: str = "") -> None:
    """The shared check: no CSS animation or transition is running on the page."""
    running = page.evaluate(RUNNING)
    assert running == [], f"{where}: {running}"


def _new_test(scenes: dict[str, Callable]) -> Callable:
    # The dict fills as the module's @scene functions are defined; pytest reads it once the module is imported.
    @pytest.mark.parametrize("scene", scenes)
    def test_reduced_motion_nothing_moves(request, browser, reduced_motion_defaults, scene):
        # browser: run in each browser of the run. reduced_motion_defaults (conftest.py): reset around the scene.
        scenes[scene](request.getfixturevalue)

    test_reduced_motion_nothing_moves.scenes = scenes
    return test_reduced_motion_nothing_moves


def scene(fn: Callable) -> Callable:
    """Registers a reduced-motion scene in the test file that defines it."""
    module = sys.modules[fn.__module__]
    test = module.__dict__.get(TEST)
    if test is None:
        test = _new_test({})
        setattr(module, TEST, test)
    test.scenes[fn.__name__] = fn
    return fn
