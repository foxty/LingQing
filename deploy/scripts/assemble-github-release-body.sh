#!/usr/bin/env bash
# Assemble GitHub Release markdown: product notes + deploy/images footer.
#
# Usage:
#   ./assemble-github-release-body.sh <VERSION> <OUTPUT_FILE> <GITHUB_REPO> <REGISTRY_URL>
#
# Product notes: docs/release-notes/<VERSION>.md
#
# STRICT_RELEASE_NOTES=1 (set in CI):
#   - File must exist (path must match tag, e.g. v0.2.0.md for tag v0.2.0).
#   - Tag string must appear in the first 40 lines (catches wrong draft merged).

set -euo pipefail

VERSION="${1:-}"
OUTPUT_FILE="${2:-}"
GITHUB_REPO="${3:-}"
REGISTRY_URL="${4:-}"

if [[ -z "$VERSION" || -z "$OUTPUT_FILE" || -z "$GITHUB_REPO" || -z "$REGISTRY_URL" ]]; then
    echo "Usage: $0 <VERSION> <OUTPUT_FILE> <GITHUB_REPO> <REGISTRY_URL>" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
NOTES_FILE="${PROJECT_ROOT}/docs/release-notes/${VERSION}.md"
STRICT_RELEASE_NOTES="${STRICT_RELEASE_NOTES:-0}"
NOTES_HEAD_LINES="${NOTES_HEAD_LINES:-40}"

validate_release_notes_for_version() {
    local version="$1"
    local notes_file="$2"
    if [[ ! -f "$notes_file" ]]; then
        echo "Release notes missing: ${notes_file} (expected for tag ${version})" >&2
        return 1
    fi
    if ! head -n "$NOTES_HEAD_LINES" "$notes_file" | grep -Fq "$version"; then
        echo "Release notes do not reference ${version} in the first ${NOTES_HEAD_LINES} lines of ${notes_file}" >&2
        echo "Add the tag to the title (e.g. # LingQing ${version}) so the doc matches the release." >&2
        return 1
    fi
}

mkdir -p "$(dirname "$OUTPUT_FILE")"

DEPLOY_FOOTER="$(mktemp)"
{
    echo "## Deploy on your VM (no repo clone)"
    echo ""
    echo "Same bundle for prod or staging — use on **separate VMs**; only \`.env\` differs."
    echo ""
    echo '```bash'
    echo "VERSION=${VERSION}"
    echo "curl -fsSL \"https://github.com/${GITHUB_REPO}/releases/download/\${VERSION}/lingqing-deploy-\${VERSION}.tar.gz\" | tar -xz"
    echo "cd \"lingqing-deploy-\${VERSION}\""
    echo "cp .env.template .env && \$EDITOR .env"
    echo "./bootstrap.sh --version \"\${VERSION}\" --registry ${REGISTRY_URL}"
    echo '```'
    echo ""
    echo "Full guide: [docs/deploy/guide.md](https://github.com/${GITHUB_REPO}/blob/main/docs/deploy/guide.md)"
    echo ""
    echo "## Images"
    echo ""
    echo "| Image | Tag |"
    echo "| --- | --- |"
    echo "| \`${REGISTRY_URL}/backend-app\` | \`${VERSION}\` |"
    echo "| \`${REGISTRY_URL}/frontend\` | \`${VERSION}\` |"
    echo "| \`${REGISTRY_URL}/sandbox-controller\` | \`${VERSION}\` |"
    echo "| \`${REGISTRY_URL}/sandbox-runner\` | \`${VERSION}\` |"
    echo "| \`${REGISTRY_URL}/egress-proxy\` | \`${VERSION}\` |"
    echo ""
    echo "## Daily staging builds"
    echo ""
    echo "For bleeding-edge staging between releases, use \`daily\` or pin \`daily-YYYY-MM-DD\` — see [deploy guide → Daily staging images](https://github.com/${GITHUB_REPO}/blob/main/docs/deploy/guide.md#daily-staging-images)."
} >"$DEPLOY_FOOTER"

if [[ -f "$NOTES_FILE" ]]; then
    validate_release_notes_for_version "$VERSION" "$NOTES_FILE"
    cat "$NOTES_FILE" >"$OUTPUT_FILE"
    {
        echo ""
        echo "---"
        echo ""
        cat "$DEPLOY_FOOTER"
    } >>"$OUTPUT_FILE"
elif [[ "$STRICT_RELEASE_NOTES" == "1" ]]; then
    echo "STRICT_RELEASE_NOTES=1 requires ${NOTES_FILE}" >&2
    exit 1
else
    cat "$DEPLOY_FOOTER" >"$OUTPUT_FILE"
fi
rm -f "$DEPLOY_FOOTER"
