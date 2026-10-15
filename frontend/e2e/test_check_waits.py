"""The fixed-wait check (check_waits.py): no browser, no servers. Check ids: A56.n, from ticket #56."""
from pathlib import Path

from check_waits import HERE, main, unexplained

# Split so this file doesn't trip the check it tests.
WAIT = "page.wait_for" + "_timeout(100)"
SLEEP = "time.sl" + "eep(0.5)"


def write(folder: Path, name: str, *lines: str) -> Path:
    path = folder / name
    path.write_text("\n".join(lines) + "\n")
    return path


def test_a56_2_an_unexplained_wait_or_sleep_is_reported_with_file_and_line(tmp_path):
    write(tmp_path, "test_a.py", "def test_x(page):", f"    {WAIT}", f"    {SLEEP}  # waits a bit")
    found = unexplained(tmp_path)
    assert [(p.name, n) for p, n, _ in found] == [("test_a.py", 2), ("test_a.py", 3)]


def test_a56_2_a_reason_on_the_same_line_allows_it(tmp_path):
    write(tmp_path, "test_a.py", f"    {WAIT}  # allowed: past the 3 s happy spell",
          f"    {SLEEP}  # allowed: poll step")
    assert unexplained(tmp_path) == []


def test_a56_2_an_empty_reason_or_one_on_another_line_does_not_count(tmp_path):
    write(tmp_path, "test_a.py", f"    {WAIT}  # allowed:", "    # allowed: the reason is on the wrong line",
          f"    {SLEEP}")
    assert [n for _, n, _ in unexplained(tmp_path)] == [1, 3]


def test_a56_2_other_spellings_of_a_fixed_wait_count_too(tmp_path):
    write(tmp_path, "test_a.py", "from time import sleep", "    sleep" + "(1)", "    asyncio.sl" + "eep(1)",
          "    page.wait_for_timeout" + " (5)")
    assert [n for _, n, _ in unexplained(tmp_path)] == [2, 3, 4]


def test_a56_2_waits_on_a_real_condition_and_comments_are_fine(tmp_path):
    write(tmp_path, "test_a.py", "    page.wait_for_function('x', timeout=5000)", "    expect(x).to_be_visible(timeout=100)",
          "    page.wait_for_selector('.x')", "    settled(loc)", "# never a fixed sl" + "eep (it races)")
    assert unexplained(tmp_path) == []


def test_a56_2_files_in_hidden_folders_are_skipped(tmp_path):
    (tmp_path / ".venv").mkdir()
    write(tmp_path / ".venv", "lib.py", f"    {SLEEP}")
    assert unexplained(tmp_path) == []


def test_a56_2_the_command_fails_on_an_unexplained_wait_and_says_how_to_fix_it(tmp_path, capsys):
    write(tmp_path, "test_a.py", f"    {WAIT}")
    assert main([str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "test_a.py:1" in out and "# allowed:" in out and "eventually()" in out
    write(tmp_path, "test_a.py", f"    {WAIT}  # allowed: on purpose")
    assert main([str(tmp_path)]) == 0


def test_a56_2_the_browser_check_itself_has_no_unexplained_wait():
    assert unexplained(HERE) == []
