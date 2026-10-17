"""How the shared reduced-motion check collects its scenes (reduced_motion.py). No browser, no servers.

Check ids: R.n, from the spec B retro (finding 3): each test file registers its own scenes with `@scene`, so no
ticket edits a shared list. The scenes themselves run in their own files, as `test_reduced_motion_nothing_moves`.
"""
import subprocess
import sys
from pathlib import Path

from check_waits import HERE

TEST = "test_reduced_motion_nothing_moves"
# Every scene there was when the list moved into the test files (2026-10-16). New scenes add to the run, not here.
BEFORE_THE_MOVE = {
    "a02_10_shell", "a04_9_dashboard", "a04b_9_cves_page", "a05_8_charts_and_banner", "a06_8_chat",
    "a06b_7_patch_variants", "a07_8_chat_layout", "a11_7_dev_page", "a13_7_settings", "a14_12_snapshot_additions",
    "a15_9_verdict", "a15b_8_watchlist", "a16_12_priority", "a16b_13_decisions", "a18_6_fix_first",
    "a19_6_explain_levels", "b02_9_check_now", "b08_13_research_web", "b10_15_sign_in_screen",
    "b19_9_runs_and_paused", "b20_14_partial_and_try_again", "b21_9_proposal_card", "b22_9_proposed_decision",
    "b24_11_card_actions",
}


def collect(folder: Path, *args: str) -> list[str]:
    """Test ids pytest collects in `folder` (reduced_motion.py importable from the browser check's folder)."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "--rootdir", str(folder),
         *args], cwd=folder, capture_output=True, text=True, env={"PYTHONPATH": str(HERE), "PATH": "/usr/bin:/bin"})
    assert result.returncode == 0, result.stdout + result.stderr
    return [line for line in result.stdout.splitlines() if "::" in line]


def test_r_3_a_test_file_registers_its_scenes_and_each_runs_as_its_own_test(tmp_path):
    (tmp_path / "test_one.py").write_text(
        "from reduced_motion import scene\n\n"
        "@scene\ndef x01_1_first(fx):\n    pass\n\n"
        "@scene\ndef x01_2_second(fx):\n    pass\n")
    (tmp_path / "test_two.py").write_text(
        "from reduced_motion import scene\n\n@scene\ndef x02_1_other(fx):\n    pass\n")
    (tmp_path / "test_none.py").write_text("def test_plain():\n    pass\n")
    ids = collect(tmp_path, "-p", "no:playwright")
    assert sorted(ids) == sorted([
        f"test_none.py::test_plain",
        f"test_one.py::{TEST}[x01_1_first]", f"test_one.py::{TEST}[x01_2_second]",
        f"test_two.py::{TEST}[x02_1_other]"])


def test_r_3_every_scene_from_before_the_move_still_runs_once_per_browser():
    ids = collect(HERE, "--browser", "chromium", "-k", TEST)
    scenes = [i.split("[chromium-", 1)[1].rstrip("]") for i in ids]
    assert BEFORE_THE_MOVE <= set(scenes)
    assert len(scenes) == len(set(scenes))  # no scene registered twice
