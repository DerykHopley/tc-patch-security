"""The merge script (scripts/ff-merge.sh) against a throwaway bare repo: no network. Check ids: R.n (spec B retro).

Each test makes an `origin` (bare), a clone with `spec-b` and a ticket branch `b99` on its own worktree, then runs
the script in the clone.
"""
import subprocess
from pathlib import Path

from check_waits import HERE

SCRIPT = HERE.parent.parent / "scripts" / "ff-merge.sh"
OURS = "<" * 7  # built, so this file never holds a marker line itself


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def commit(repo: Path, name: str, text: str) -> str:
    (repo / name).write_text(text)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", f"add {name}")
    return git(repo, "rev-parse", "HEAD")


def setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    """origin (bare), clone (on spec-b), and the b99 worktree with one commit pushed."""
    origin, clone, tree = tmp_path / "origin.git", tmp_path / "clone", tmp_path / "b99-tree"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "spec-b", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True, capture_output=True)
    for key, value in (("user.email", "test@example.com"), ("user.name", "Test")):
        git(clone, "config", key, value)
    git(clone, "checkout", "-q", "-b", "spec-b")
    commit(clone, "base.txt", "base\n")
    git(clone, "push", "-q", "origin", "spec-b")
    git(clone, "worktree", "add", "-q", "-b", "b99", str(tree), "origin/spec-b")
    commit(tree, "feature.txt", "feature\n")
    git(tree, "push", "-q", "-u", "origin", "b99")
    return origin, clone, tree


def merge(clone: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(SCRIPT), *args], cwd=clone, capture_output=True, text=True)


def branches(repo: Path) -> list[str]:
    return git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()


def test_r_2_a_fast_forward_lands_then_cleans_up_the_worktree_and_local_branch(tmp_path):
    origin, clone, tree = setup(tmp_path)
    tip = git(tree, "rev-parse", "HEAD")
    result = merge(clone, "b99")
    assert result.returncode == 0, result.stdout + result.stderr
    assert git(origin, "rev-parse", "spec-b") == tip
    assert not tree.exists()
    assert "b99" not in branches(clone)
    assert "b99" in branches(origin)  # never deletes a remote branch


def test_r_2_the_integration_branch_can_be_named(tmp_path):
    origin, clone, tree = setup(tmp_path)
    git(clone, "push", "-q", "origin", "spec-b:spec-c")
    tip = git(tree, "rev-parse", "HEAD")
    assert merge(clone, "b99", "spec-c").returncode == 0
    assert git(origin, "rev-parse", "spec-c") == tip


def test_r_2_not_a_fast_forward_is_refused_and_nothing_changes(tmp_path):
    origin, clone, tree = setup(tmp_path)
    moved = commit(clone, "other.txt", "another ticket\n")
    git(clone, "push", "-q", "origin", "spec-b")
    result = merge(clone, "b99")
    assert result.returncode != 0
    assert "not a fast-forward" in result.stderr
    assert git(origin, "rev-parse", "spec-b") == moved
    assert tree.exists() and "b99" in branches(clone)


def test_r_2_conflict_markers_on_the_branch_are_refused_before_the_push(tmp_path):
    origin, clone, tree = setup(tmp_path)
    before = git(origin, "rev-parse", "spec-b")
    commit(tree, "settings.env", f"A=1\n{OURS} HEAD\n")
    git(tree, "push", "-q", "origin", "b99")
    result = merge(clone, "b99")
    assert result.returncode != 0
    assert "settings.env:2" in result.stdout + result.stderr
    assert git(origin, "rev-parse", "spec-b") == before
    assert tree.exists()


def test_r_2_dry_run_says_what_it_would_do_and_changes_nothing(tmp_path):
    origin, clone, tree = setup(tmp_path)
    before = git(origin, "rev-parse", "spec-b")
    result = merge(clone, "--dry-run", "b99")
    assert result.returncode == 0, result.stderr
    assert "would" in result.stdout.lower()
    assert git(origin, "rev-parse", "spec-b") == before
    assert tree.exists() and "b99" in branches(clone)


def test_r_2_a_locked_worktree_is_removed_after_success(tmp_path):
    origin, clone, tree = setup(tmp_path)
    git(clone, "worktree", "lock", str(tree))
    assert merge(clone, "b99").returncode == 0
    assert not tree.exists()


def test_r_2_unpushed_commits_on_the_local_branch_are_refused_before_the_push(tmp_path):
    origin, clone, tree = setup(tmp_path)
    before = git(origin, "rev-parse", "spec-b")
    commit(tree, "later.txt", "not pushed yet\n")
    result = merge(clone, "b99")
    assert result.returncode != 0
    assert "not pushed" in result.stderr
    assert git(origin, "rev-parse", "spec-b") == before
    assert tree.exists() and "b99" in branches(clone)
