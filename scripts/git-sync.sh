#!/usr/bin/env bash
# Push or pull the current branch via a repo URL (same branch name). Does not add remotes or upstream.
#
# Usage:
#   ./scripts/git-sync.sh push [--force|-f] <repo-url>
#   ./scripts/git-sync.sh pull [--force|-f] <repo-url>
#
# --force  push: git push --force-with-lease
#          pull: fetch then git reset --hard to the remote branch (discards local branch divergence)

set -euo pipefail

usage() {
    echo "Usage: $0 push|pull [--force|-f] <repo-url>" >&2
    exit 1
}

[[ $# -ge 2 ]] || usage

ACTION="$1"
shift

case "$ACTION" in
    push | pull) ;;
    *) usage ;;
esac

FORCE=false
if [[ "${1:-}" == --force || "${1:-}" == -f ]]; then
    FORCE=true
    shift
fi

[[ $# -eq 1 ]] || usage
REPO="$1"

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    echo "Error: not inside a git repository" >&2
    exit 1
}
cd "$ROOT"

BRANCH="$(git branch --show-current)"
if [[ -z "$BRANCH" ]]; then
    echo "Error: detached HEAD; checkout a branch first" >&2
    exit 1
fi

if [[ "$ACTION" == "push" ]]; then
    if [[ "$FORCE" == true ]]; then
        git push --force-with-lease "$REPO" "HEAD:refs/heads/${BRANCH}"
    else
        git push "$REPO" "HEAD:refs/heads/${BRANCH}"
    fi
else
    git fetch "$REPO" "refs/heads/${BRANCH}"
    if [[ "$FORCE" == true ]]; then
        git reset --hard FETCH_HEAD
    else
        git merge --no-edit FETCH_HEAD
    fi
fi
