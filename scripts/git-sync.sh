#!/usr/bin/env bash
# Push or pull the current branch via a repo URL (same branch name). Does not add remotes or upstream.
#
# Usage:
#   ./scripts/git-sync.sh push <repo-url>
#   ./scripts/git-sync.sh pull <repo-url>

set -euo pipefail

usage() {
    echo "Usage: $0 push|pull <repo-url>" >&2
    exit 1
}

[[ $# -eq 2 ]] || usage

ACTION="$1"
REPO="$2"

case "$ACTION" in
    push | pull) ;;
    *) usage ;;
esac

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
    git push "$REPO" "HEAD:refs/heads/${BRANCH}"
else
    git fetch "$REPO" "refs/heads/${BRANCH}"
    git merge --no-edit FETCH_HEAD
fi
