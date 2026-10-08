#!/usr/bin/env bash
# Package a versioned deploy bundle for GitHub Releases (no full repo clone on VM).
#
# Usage:
#   ./package-release-bundle.sh <VERSION> <OUTPUT_DIR> [REGISTRY_URL] [GITHUB_REPO]
#
# Produces:
#   <OUTPUT_DIR>/lingqing-deploy-<VERSION>.tar.gz
#
# One bundle per VM: staging and production use the same files on separate hosts;
# only .env values differ (domains, DB, data path).

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
PROJECT_ROOT="$(cd "$DEPLOY_ROOT/.." && pwd)"
REMOTE_DIR="${SCRIPT_DIR}/remote"
STAGING_DIR="$(mktemp -d)"
BUNDLE_NAME="lingqing-deploy-${VERSION}"
BUNDLE_ROOT="${STAGING_DIR}/${BUNDLE_NAME}"

cleanup() {
    rm -rf "$STAGING_DIR"
}
trap cleanup EXIT

mkdir -p "$BUNDLE_ROOT" "$OUTPUT_DIR"

cp "${DEPLOY_ROOT}/compose/remote/stack.yml" "${BUNDLE_ROOT}/docker-compose.yml"
cp "${DEPLOY_ROOT}/env/.env.production.template" "${BUNDLE_ROOT}/.env.template"
cp "${REMOTE_DIR}/host-deploy.sh" "${BUNDLE_ROOT}/bootstrap.sh"
cp "${PROJECT_ROOT}/scripts/init_db.sh" "${BUNDLE_ROOT}/init_db.sh"
chmod +x "${BUNDLE_ROOT}/bootstrap.sh" "${BUNDLE_ROOT}/init_db.sh"

cat > "${BUNDLE_ROOT}/README.md" <<EOF
# LingQing Deploy Bundle ${VERSION}

Deploy LingQing on a Linux VM using pre-built container images. **No repository clone required.**

Production: provision external PostgreSQL (RDS, Cloud SQL, etc.) first.

Optional **bundled Postgres** on the same VM: \`./bootstrap.sh --with-postgres\` (demo/internal; see docs/deploy/reference.md).

**Staging and production:** same bundle on **separate VMs**; only \`.env\` differs. Gateway: \`127.0.0.1:8080\`.

## Quick start

### 1. Initialize PostgreSQL

**External database (production):** run once from laptop or bastion (\`psql\` + network to admin account):

\`\`\`bash
export POSTGRES_HOST=your-db.example.com
export POSTGRES_USER=postgres
export PGPASSWORD=your_admin_password
./init_db.sh 'choose_app_password' 'choose_manager_password'
\`\`\`

**Bundled Postgres:** skip this step — use \`./bootstrap.sh --with-postgres\`; bootstrap runs \`init_db.sh\` after Postgres is healthy. Set \`POSTGRES_PASSWORD\` in \`.env\`.

Use the same app/manager passwords in \`.env\` as passed to \`init_db.sh\`.

### 2. Configure environment

\`\`\`bash
cp .env.template .env
nano .env
\`\`\`

Edit the **FILL BEFORE DEPLOY** section of \`.env.template\`:

| Variable | Example |
| --- | --- |
| \`SECRET_KEY\` | \`openssl rand -hex 32\` |
| \`TENANT_APP_DB_HOST\` | PostgreSQL hostname |
| \`TENANT_APP_DB_PASSWORD\` | App password from \`init_db.sh\` |
| \`TENANT_MANAGER_DB_HOST\` | Same as app host (one PG server) |
| \`TENANT_MANAGER_DB_PASSWORD\` | Manager password from \`init_db.sh\` |
| \`DATA_ROOT_HOST_PATH\` | \`/var/lib/lingqing/data\` |
| \`APP_PUBLIC_URL\` | \`https://app.example.com\` |
| \`MANAGER_PUBLIC_URL\` | \`https://manager.example.com\` |

### 3. Deploy

\`\`\`bash
./bootstrap.sh --version ${VERSION} --registry ${REGISTRY_URL}
\`\`\`

\`bootstrap.sh\` derives \`CORS_ORIGINS\`, \`PORTAL_ORIGIN\`, and \`TENANT_APP_API_ORIGIN\` from the public URLs.

Full reference: https://github.com/${GITHUB_REPO}/blob/main/docs/deploy/reference.md

## Download

\`\`\`bash
curl -fsSL https://github.com/${GITHUB_REPO}/releases/download/${VERSION}/lingqing-deploy-${VERSION}.tar.gz | tar -xz
cd lingqing-deploy-${VERSION}
\`\`\`

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

Full docs: https://github.com/${GITHUB_REPO}/blob/main/docs/deploy/guide.md
EOF

echo "$VERSION" > "${BUNDLE_ROOT}/VERSION"

ARCHIVE_PATH="${OUTPUT_DIR}/${BUNDLE_NAME}.tar.gz"
tar -czf "$ARCHIVE_PATH" -C "$STAGING_DIR" "$BUNDLE_NAME"

echo "Created ${ARCHIVE_PATH}"
