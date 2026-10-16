#!/usr/bin/env bash
# Fast-forward a ticket branch into the integration branch, then clean up its worktree (spec B retro, finding 4).
#
#   scripts/ff-merge.sh <branch> [integration]   # integration defaults to spec-b
#   scripts/ff-merge.sh --dry-run <branch>       # every check, then says what it would do; changes nothing
#
# Every check runs before anything changes; the first one that fails stops the script with a message and exit 1:
#   1. fetch origin;
#   2. origin/<integration> is an ancestor of origin/<branch> (a fast-forward, nothing on the integration branch lost);
#   3. no conflict-marker line in origin/<branch>'s tree (a fast-forward's merged tree is the branch's tree);
#   4. the local branch(es) about to be deleted hold nothing that isn't in origin/<branch> (no unpushed work);
#   5. this shell isn't inside a worktree that is about to be removed.
# Then: push origin/<branch>'s commit to <integration> (never a force push), fetch, check it landed, and only then
# remove each local worktree on the branch (-f -f only when git says it is locked) and delete the local branch:
# <branch> and any local branch that tracks origin/<branch> (an agent's worktree-... branch). Remote branches are
# never deleted.
# No pipes: a pipe hides the exit code of everything but its last command (the retro's lesson).
set -euo pipefail

MARKERS='^(<<<<<<<|>>>>>>>)( |$)'
DRY_RUN=""
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
  shift
fi
if [ $# -lt 1 ] || [ $# -gt 2 ]; then
  echo "usage: scripts/ff-merge.sh [--dry-run] <branch> [integration=spec-b]" >&2
  exit 2
fi
BRANCH="$1"
INTEGRATION="${2:-spec-b}"

fail() {
  echo "ff-merge: $*" >&2
  exit 1
}
run() {
  if [ -n "$DRY_RUN" ]; then
    echo "would run: $*"
  else
    echo "+ $*"
    "$@"
  fi
}

# 1. Fetch.
git fetch --quiet origin || fail "git fetch origin failed."
TIP="$(git rev-parse --verify --quiet "refs/remotes/origin/$BRANCH^{commit}")" \
  || fail "origin/$BRANCH not found. Push the branch first."
BASE="$(git rev-parse --verify --quiet "refs/remotes/origin/$INTEGRATION^{commit}")" \
  || fail "origin/$INTEGRATION not found."

# 2. A fast-forward only.
if [ "$BASE" = "$TIP" ]; then
  fail "origin/$BRANCH is already origin/$INTEGRATION ($TIP): nothing to merge."
fi
git merge-base --is-ancestor "$BASE" "$TIP" \
  || fail "not a fast-forward: origin/$INTEGRATION has commits origin/$BRANCH lacks. Merge origin/$INTEGRATION into $BRANCH (or rebase), push, run again."

# 3. No conflict markers in the tree that would land. git grep: 0 = found, 1 = none, more = an error.
status=0
git grep -nE "$MARKERS" "$TIP" -- || status=$?
case "$status" in
  0) fail "conflict markers in origin/$BRANCH (lines above). Fix them on the branch, push, run again." ;;
  1) ;;
  *) fail "git grep for conflict markers failed (exit $status)." ;;
esac

# 4. The local branches to delete: <branch>, and any local branch tracking origin/<branch>.
REFS="$(git for-each-ref --format='%(refname:short) %(upstream:short)' refs/heads)"
LOCAL=()
while read -r name upstream; do
  if [ "$name" = "$BRANCH" ] || [ "$upstream" = "origin/$BRANCH" ]; then
    LOCAL+=("$name")
  fi
done <<<"$REFS"
for name in ${LOCAL[@]+"${LOCAL[@]}"}; do
  git merge-base --is-ancestor "refs/heads/$name" "$TIP" \
    || fail "local branch $name has commits not pushed to origin/$BRANCH. Push them (or drop them) first."
done

# 5. The worktrees on those branches; refuse if this shell is inside one of them.
WORKTREES="$(git worktree list --porcelain)"
HERE_TOP="$(git rev-parse --show-toplevel)"
REMOVE=()
LOCKED=()
path=""
locked=""
flush() {
  if [ -n "$path" ] && [ -n "$branch_match" ]; then
    REMOVE+=("$path")
    LOCKED+=("$locked")
  fi
  path=""
  locked=""
  branch_match=""
}
branch_match=""
while IFS= read -r line; do
  case "$line" in
    "worktree "*) flush; path="${line#worktree }" ;;
    "branch refs/heads/"*)
      for name in ${LOCAL[@]+"${LOCAL[@]}"}; do
        if [ "${line#branch refs/heads/}" = "$name" ]; then branch_match=1; fi
      done ;;
    locked | "locked "*) locked=1 ;;
  esac
done <<<"$WORKTREES"
flush
for tree in ${REMOVE[@]+"${REMOVE[@]}"}; do
  if [ "$tree" = "$HERE_TOP" ]; then
    fail "this shell is in $tree, the worktree to remove. Run from another checkout (e.g. the main one)."
  fi
done

# Act: land the commit, check it landed, then clean up.
echo "ff-merge: origin/$BRANCH ($TIP) fast-forwards origin/$INTEGRATION ($BASE)."
run git push origin "$TIP:refs/heads/$INTEGRATION"
if [ -z "$DRY_RUN" ]; then
  git fetch --quiet origin || fail "git fetch origin after the push failed; check origin/$INTEGRATION by hand."
  LANDED="$(git rev-parse --verify --quiet "refs/remotes/origin/$INTEGRATION^{commit}")" || LANDED=""
  [ "$LANDED" = "$TIP" ] \
    || fail "origin/$INTEGRATION is ${LANDED:-missing}, not $TIP, after the push. Nothing was cleaned up."
  echo "ff-merge: origin/$INTEGRATION is now $TIP."
fi

for i in ${REMOVE[@]+"${!REMOVE[@]}"}; do
  if [ -n "${LOCKED[$i]}" ]; then
    run git worktree remove -f -f "${REMOVE[$i]}"
  else
    run git worktree remove "${REMOVE[$i]}"
  fi
done
for name in ${LOCAL[@]+"${LOCAL[@]}"}; do
  run git branch -D "$name"  # -D: step 4 checked it is all in origin/$BRANCH, now on origin/$INTEGRATION
done
if [ -n "$DRY_RUN" ]; then
  echo "Dry run: nothing pushed, removed or deleted."
else
  echo "ff-merge: done. Remote branch origin/$BRANCH kept."
fi
