#!/usr/bin/env bash
# Package a versioned deploy bundle for GitHub Releases (no full repo clone on VM).
#
# Usage:
#   ./package-release-bundle.sh <VERSION> <OUTPUT_DIR> [REGISTRY_URL] [GITHUB_REPO]
#
# Produces:
#   <OUTPUT_DIR>/lingqing-deploy-<VERSION>.tar.gz

set -euo pipefail

VERSION="${1:-}"
OUTPUT_DIR="${2:-}"
REGISTRY_URL="${3:-ghcr.io/foxty/lingqing}"
GITHUB_REPO="${4:-foxty/LingQing}"

if [[ -z "$VERSION" || -z "$OUTPUT_DIR" ]]; then
    echo "Usage: $0 <VERSION> <OUTPUT_DIR> [REGISTRY_URL] [GITHUB_REPO]" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STAGING_DIR="$(mktemp -d)"
BUNDLE_NAME="lingqing-deploy-${VERSION}"
BUNDLE_ROOT="${STAGING_DIR}/${BUNDLE_NAME}"

cleanup() {
    rm -rf "$STAGING_DIR"
}
trap cleanup EXIT

mkdir -p "$BUNDLE_ROOT" "$OUTPUT_DIR"

cp "${DEPLOY_ROOT}/compose/remote/stack.yml" "${BUNDLE_ROOT}/docker-compose.yml"
cp "${DEPLOY_ROOT}/compose/remote/overrides/staging.yml" "${BUNDLE_ROOT}/docker-compose.staging.yml"
cp "${DEPLOY_ROOT}/env/.env.template" "${BUNDLE_ROOT}/.env.template"
cp "${SCRIPT_DIR}/remote/host-deploy.sh" "${BUNDLE_ROOT}/bootstrap.sh"
chmod +x "${BUNDLE_ROOT}/bootstrap.sh"

cat > "${BUNDLE_ROOT}/README.md" <<EOF
# LingQing Deploy Bundle ${VERSION}

Deploy LingQing on a Linux VM using pre-built container images. No repository clone required.

## Prerequisites

- Docker Engine + Compose plugin
- Managed PostgreSQL reachable from the VM
- DNS for \`app.example.com\` and \`manager.example.com\`
- Outer Nginx (or similar) for TLS, proxying to \`127.0.0.1:8080\`

## Quick start (production)

\`\`\`bash
tar -xzf lingqing-deploy-${VERSION}.tar.gz
cd lingqing-deploy-${VERSION}
cp .env.template .env
# Edit .env: SECRET_KEY, DB credentials, DATA_ROOT_HOST_PATH, public URLs
./bootstrap.sh --version ${VERSION} --registry ${REGISTRY_URL}
\`\`\`

## One-liner (download bundle on VM)

\`\`\`bash
curl -fsSL https://github.com/${GITHUB_REPO}/releases/download/${VERSION}/lingqing-deploy-${VERSION}.tar.gz | tar -xz
cd lingqing-deploy-${VERSION}
cp .env.template .env && \$EDITOR .env
./bootstrap.sh --version ${VERSION} --registry ${REGISTRY_URL}
\`\`\`

## Staging tier

\`\`\`bash
./bootstrap.sh --version ${VERSION} --registry ${REGISTRY_URL} --tier staging --dir ~/lingqing-deploy/staging
\`\`\`

Gateway listens on \`127.0.0.1:18080\` for staging.

## Images

| Image | Tag |
| --- | --- |
| \`${REGISTRY_URL}/backend-app\` | \`${VERSION}\` |
| \`${REGISTRY_URL}/frontend\` | \`${VERSION}\` |
| \`${REGISTRY_URL}/sandbox-controller\` | \`${VERSION}\` |
| \`${REGISTRY_URL}/sandbox-runner\` | \`${VERSION}\` |

## First tenant

\`\`\`bash
APP_CONTAINER=\$(docker ps --format '{{.Names}}' | grep tenant-app-service | head -n 1)
docker exec -it "\$APP_CONTAINER" uv run --no-dev scripts/tenant_cli.py create --name "Demo" --slug demo
\`\`\`

Login: \`admin@demo\` / \`admin\` — change immediately in production.

## Upgrade

Re-run \`bootstrap.sh\` with a new \`--version\` in the same deploy directory.

Full docs: https://github.com/${GITHUB_REPO}/blob/main/docs/deploy/vm-bootstrap.md
EOF

echo "$VERSION" > "${BUNDLE_ROOT}/VERSION"

ARCHIVE_PATH="${OUTPUT_DIR}/${BUNDLE_NAME}.tar.gz"
tar -czf "$ARCHIVE_PATH" -C "$STAGING_DIR" "$BUNDLE_NAME"

echo "Created ${ARCHIVE_PATH}"
