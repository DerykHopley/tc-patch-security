"""The pre-commit hook (.githooks/pre-commit): no browser, no servers. Check ids: R.n, from the spec B retro.

Each test builds a throwaway git repo, turns the hook on there (core.hooksPath) and commits.
"""
import shutil
import subprocess
import time
from pathlib import Path

from check_waits import HERE

ROOT = HERE.parent.parent
HOOK = ROOT / ".githooks" / "pre-commit"
# Built, so this file never holds a marker line itself.
OURS, THEIRS = "<" * 7, ">" * 7
WAIT = "page.wait_for" + "_timeout(100)"


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check)


def repo_with_hook(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    (repo / ".githooks").mkdir()
    shutil.copy2(HOOK, repo / ".githooks" / "pre-commit")
    (repo / "frontend" / "e2e").mkdir(parents=True)
    shutil.copy2(HERE / "check_waits.py", repo / "frontend" / "e2e" / "check_waits.py")
    git(repo, "config", "core.hooksPath", ".githooks")
    return repo


def commit(repo: Path, name: str, text: str) -> subprocess.CompletedProcess:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    git(repo, "add", "-A")
    return git(repo, "commit", "-q", "-m", f"add {name}", check=False)


def test_r_1_a_clean_commit_passes(tmp_path):
    repo = repo_with_hook(tmp_path)
    result = commit(repo, "README.md", "Hello\n=======\n")  # a Markdown underline is not a marker
    assert result.returncode == 0, result.stderr
    assert git(repo, "log", "--oneline").stdout.count("\n") == 1


def test_r_1_a_commit_with_conflict_markers_is_refused_and_names_the_line(tmp_path):
    repo = repo_with_hook(tmp_path)
    result = commit(repo, "backend/.env.example", f"A=1\n{OURS} HEAD\nB=2\n=======\nB=3\n{THEIRS} b04\n")
    assert result.returncode != 0
    assert "backend/.env.example:2" in result.stdout + result.stderr
    assert git(repo, "log", "--oneline", check=False).stdout == ""  # nothing committed


def test_r_1_the_staged_content_is_checked_not_the_working_tree(tmp_path):
    repo = repo_with_hook(tmp_path)
    (repo / "notes.txt").write_text(f"{OURS} HEAD\n")
    git(repo, "add", "notes.txt")
    (repo / "notes.txt").write_text("fixed, but not staged\n")
    assert git(repo, "commit", "-q", "-m", "x", check=False).returncode != 0
    git(repo, "add", "notes.txt")
    assert git(repo, "commit", "-q", "-m", "x", check=False).returncode == 0


def test_r_1_an_unexplained_fixed_wait_is_refused(tmp_path):
    repo = repo_with_hook(tmp_path)
    result = commit(repo, "frontend/e2e/test_a.py", f"def test_x(page):\n    {WAIT}\n")
    assert result.returncode != 0
    assert "test_a.py:2" in result.stdout + result.stderr


def test_r_1_the_hook_takes_under_a_second_on_this_repo():
    start = time.monotonic()
    result = subprocess.run([str(HOOK)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert time.monotonic() - start < 1.0
