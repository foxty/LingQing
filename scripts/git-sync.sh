#!/usr/bin/env bash
# Push or pull the current branch via a repo URL (same branch name). Does not add remotes or upstream.
#
# Usage:
#   ./scripts/git-sync.sh push [options] <repo-url>
#   ./scripts/git-sync.sh pull [options] <repo-url>
#
# Push options:
#   -f, --force, --force-push   git push --force-with-lease (default when any force flag is set)
#   --hard-force                git push --force (overwrites remote; no lease check)
#
# Pull options:
#   -f, --force                 fetch then git reset --hard to the remote branch

set -euo pipefail

usage() {
    cat >&2 <<EOF
Usage: $0 push|pull [options] <repo-url>

  push options:
    -f, --force, --force-push   force-with-lease
    --hard-force                plain --force (destructive)

  pull options:
    -f, --force                 reset --hard to remote branch
EOF
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
HARD_FORCE=false
REPO=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f | --force | --force-push)
            FORCE=true
            shift
            ;;
        --hard-force)
            if [[ "$ACTION" != "push" ]]; then
                echo "Error: --hard-force is only valid for push" >&2
                exit 1
            fi
            HARD_FORCE=true
            FORCE=true
            shift
            ;;
        -h | --help)
            usage
            ;;
        -*)
            echo "Error: unknown option: $1" >&2
            usage
            ;;
        *)
            if [[ -n "$REPO" ]]; then
                echo "Error: unexpected argument: $1" >&2
                usage
            fi
            REPO="$1"
            shift
            ;;
    esac
done

[[ -n "$REPO" ]] || usage

if [[ "$HARD_FORCE" == true && "$ACTION" != "push" ]]; then
    echo "Error: --hard-force is only valid for push" >&2
    exit 1
fi

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

REF="HEAD:refs/heads/${BRANCH}"

if [[ "$ACTION" == "push" ]]; then
    if [[ "$HARD_FORCE" == true ]]; then
        git push --force "$REPO" "$REF"
    elif [[ "$FORCE" == true ]]; then
        git push --force-with-lease "$REPO" "$REF"
    else
        git push "$REPO" "$REF"
    fi
else
    git fetch "$REPO" "refs/heads/${BRANCH}"
    if [[ "$FORCE" == true ]]; then
        git reset --hard FETCH_HEAD
    else
        git merge --no-edit FETCH_HEAD
    fi
fi
