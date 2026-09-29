#!/usr/bin/env bash
# On-host deploy from pre-built registry images (no repo clone).
# In release bundles this file is named bootstrap.sh.
#
# Usage (run from the extracted bundle directory):
#   cp .env.template .env && $EDITOR .env
#   ./host-deploy.sh --version v2.0.0 --registry ghcr.io/ORG/lingqing
#
# Staging vs production: use the same bundle on separate VMs; only .env differs
# (domains, DB host, DATA_ROOT_HOST_PATH).

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

VERSION="${VERSION:-}"
REGISTRY_URL="${REGISTRY_URL:-}"
GITHUB_REPO="${GITHUB_REPO:-}"
DEPLOY_DIR="${DEPLOY_DIR:-}"
SKIP_PULL=false
ENV_FILE=""
PROJECT_NAME="lingqing"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo ".")"
SCRIPT_NAME="$(basename "$0")"

infer_github_repo() {
    if [[ -n "$GITHUB_REPO" ]]; then
        echo "$GITHUB_REPO"
        return
    fi
    if [[ "$REGISTRY_URL" =~ ^ghcr\.io/([^/]+)/lingqing$ ]]; then
        echo "${BASH_REMATCH[1]}/LingQing"
        return
    fi
    echo ""
}

read_env_value() {
    local env_file="$1"
    local key="$2"
    grep -E "^${key}=" "$env_file" 2>/dev/null | tail -n 1 | cut -d= -f2- | tr -d '[:space:'$'\r'']' || true
}

set_env_value() {
    local env_file="$1"
    local key="$2"
    local value="$3"
    if grep -q "^${key}=" "$env_file"; then
        local escaped
        escaped="$(printf '%s' "$value" | sed -e 's/[\/&]/\\&/g')"
        sed -i.bak "s|^${key}=.*|${key}=${escaped}|" "$env_file"
        rm -f "${env_file}.bak"
    else
        echo "${key}=${value}" >> "$env_file"
    fi
}

host_from_url() {
    echo "$1" | sed -E 's#^https?://##' | cut -d/ -f1
}

expand_public_urls() {
    local env_file="$1"
    local app_url manager_url

    app_url="$(read_env_value "$env_file" APP_PUBLIC_URL)"
    manager_url="$(read_env_value "$env_file" MANAGER_PUBLIC_URL)"
    if [[ -z "$app_url" || -z "$manager_url" ]]; then
        return 0
    fi

    set_env_value "$env_file" CORS_ORIGINS "${app_url},${manager_url}"
    set_env_value "$env_file" PORTAL_ORIGIN "$app_url"
    set_env_value "$env_file" TENANT_APP_API_ORIGIN "$app_url"
}

normalize_env_file() {
    local env_file="$1"
    local app_db_host manager_db_host

    app_db_host="$(read_env_value "$env_file" TENANT_APP_DB_HOST)"
    manager_db_host="$(read_env_value "$env_file" TENANT_MANAGER_DB_HOST)"
    if [[ -n "$app_db_host" && -z "$manager_db_host" ]]; then
        set_env_value "$env_file" TENANT_MANAGER_DB_HOST "$app_db_host"
    fi
}

validate_env_file() {
    local env_file="$1"
    local errors=0
    local key value

    echo "Validating ${env_file}..."
    for key in SECRET_KEY TENANT_APP_DB_HOST TENANT_APP_DB_PASSWORD TENANT_MANAGER_DB_PASSWORD \
        DATA_ROOT_HOST_PATH APP_PUBLIC_URL MANAGER_PUBLIC_URL; do
        value="$(read_env_value "$env_file" "$key")"
        if [[ -z "$value" ]]; then
            echo "  ✗ ${key} (empty)"
            errors=$((errors + 1))
        fi
    done

    for key in APP_PUBLIC_URL MANAGER_PUBLIC_URL; do
        value="$(read_env_value "$env_file" "$key")"
        if [[ "$value" == *example.com* ]]; then
            echo "  ✗ ${key} still uses example.com — set your domains"
            errors=$((errors + 1))
        fi
    done

    if [[ "$errors" -gt 0 ]]; then
        echo ""
        echo "Fix the items above, then re-run deploy."
        return 1
    fi

    echo "  ✓ Required config present"
    return 0
}

usage() {
    cat <<EOF
Usage: ${SCRIPT_NAME} --version VERSION [OPTIONS]

Run from the extracted release bundle directory (contains docker-compose.yml).

Required:
  --version VERSION       Image tag to deploy (e.g. v2.0.0)

Options:
  --registry URL          Registry prefix (default: ghcr.io/<owner>/lingqing)
  --repo OWNER/REPO       GitHub repo to download bundle if compose files missing
  --dir PATH              Working directory (default: directory containing this script)
  --env-file PATH         Copy an existing env file to .env before deploy
  --skip-pull             Skip docker pull (images already present)
  -h, --help              Show this help

Setup (before deploy):
  cp .env.template .env
  Edit .env: SECRET_KEY, DB creds, APP_PUBLIC_URL, MANAGER_PUBLIC_URL, DATA_ROOT_HOST_PATH

Example:
  ${SCRIPT_NAME} --version v2.0.0 --registry ghcr.io/foxty/lingqing
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) VERSION="$2"; shift 2 ;;
        --registry) REGISTRY_URL="$2"; shift 2 ;;
        --repo) GITHUB_REPO="$2"; shift 2 ;;
        --dir) DEPLOY_DIR="$2"; shift 2 ;;
        --env-file) ENV_FILE="$2"; shift 2 ;;
        --skip-pull) SKIP_PULL=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *)
            echo -e "${RED}Error: Unknown argument '$1'${NC}" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [[ -z "$VERSION" ]]; then
    echo -e "${RED}Error: --version is required${NC}" >&2
    usage >&2
    exit 1
fi

if [[ -z "$DEPLOY_DIR" ]]; then
    DEPLOY_DIR="$SCRIPT_DIR"
fi

GITHUB_REPO="$(infer_github_repo)"
if [[ -z "$REGISTRY_URL" && -n "$GITHUB_REPO" ]]; then
    REGISTRY_URL="ghcr.io/${GITHUB_REPO%%/*}/lingqing"
fi
if [[ -z "$REGISTRY_URL" ]]; then
    echo -e "${RED}Error: Set --registry or GITHUB_REPO so REGISTRY_URL can be inferred${NC}" >&2
    exit 1
fi

compose_cmd() {
    if docker compose version >/dev/null 2>&1; then
        docker compose "$@"
    elif command -v docker-compose >/dev/null 2>&1; then
        docker-compose "$@"
    else
        echo -e "${RED}Error: docker compose or docker-compose is required${NC}" >&2
        exit 1
    fi
}

ensure_compose_files() {
    if [[ -f "${DEPLOY_DIR}/docker-compose.yml" ]]; then
        return
    fi
    if [[ -z "$GITHUB_REPO" ]]; then
        echo -e "${RED}Error: docker-compose.yml not found in ${DEPLOY_DIR}${NC}" >&2
        echo "Run this script from the extracted bundle directory." >&2
        exit 1
    fi
    local bundle_url="https://github.com/${GITHUB_REPO}/releases/download/${VERSION}/lingqing-deploy-${VERSION}.tar.gz"
    echo -e "${YELLOW}Downloading deploy bundle from release...${NC}"
    mkdir -p "$DEPLOY_DIR"
    curl -fsSL "$bundle_url" | tar -xz -C "$DEPLOY_DIR" --strip-components=1
}

mkdir -p "$DEPLOY_DIR"
ensure_compose_files
cd "$DEPLOY_DIR"

if [[ -n "$ENV_FILE" ]]; then
    [[ -f "$ENV_FILE" ]] || { echo -e "${RED}Error: env file not found: $ENV_FILE${NC}" >&2; exit 1; }
    cp "$ENV_FILE" .env
fi

if [[ ! -f .env ]]; then
    echo -e "${YELLOW}No .env found in ${DEPLOY_DIR}.${NC}"
    echo "Copy the template, edit it, then re-run:"
    echo "  cp .env.template .env"
    exit 1
fi

normalize_env_file ".env"
expand_public_urls ".env"
validate_env_file ".env" || exit 1

DATA_ROOT_HOST_PATH="$(read_env_value ".env" DATA_ROOT_HOST_PATH)"
[[ -n "$DATA_ROOT_HOST_PATH" ]] && mkdir -p "$DATA_ROOT_HOST_PATH"

export VERSION REGISTRY_URL

GATEWAY_PORT="$(read_env_value ".env" GATEWAY_SERVICE_PORT)"
GATEWAY_PORT="${GATEWAY_PORT:-8080}"
APP_HOST="$(host_from_url "$(read_env_value ".env" APP_PUBLIC_URL)")"
MANAGER_HOST="$(host_from_url "$(read_env_value ".env" MANAGER_PUBLIC_URL)")"

echo -e "${YELLOW}LingQing deploy${NC}"
echo "Version:     $VERSION"
echo "Registry:    $REGISTRY_URL"
echo "Gateway:     127.0.0.1:${GATEWAY_PORT}"
echo "App URL:     $(read_env_value ".env" APP_PUBLIC_URL)"
echo "Manager URL: $(read_env_value ".env" MANAGER_PUBLIC_URL)"
echo "Deploy dir:  $DEPLOY_DIR"
echo ""

if [[ "$SKIP_PULL" != "true" ]]; then
    echo -e "${YELLOW}Pulling images...${NC}"
    for image in backend-app frontend sandbox-controller sandbox-runner; do
        echo "  ${REGISTRY_URL}/${image}:${VERSION}"
        docker pull "${REGISTRY_URL}/${image}:${VERSION}"
    done
    echo ""
fi

echo -e "${YELLOW}Validating compose configuration...${NC}"
compose_cmd -f docker-compose.yml -p "$PROJECT_NAME" config -q

echo -e "${YELLOW}Starting services...${NC}"
compose_cmd -f docker-compose.yml -p "$PROJECT_NAME" up -d

echo ""
echo -e "${YELLOW}Running smoke checks...${NC}"
curl -fsS -H "Host: ${APP_HOST}" "http://127.0.0.1:${GATEWAY_PORT}/health" >/dev/null
curl -fsS -H "Host: ${MANAGER_HOST}" "http://127.0.0.1:${GATEWAY_PORT}/health" >/dev/null

echo -e "${GREEN}Deployment completed successfully.${NC}"
echo ""
echo "Configure outer Nginx/TLS to proxy ${APP_HOST} and ${MANAGER_HOST} to 127.0.0.1:${GATEWAY_PORT}"
echo ""
echo "Create the first tenant:"
echo "  APP_CONTAINER=\$(docker ps --format '{{.Names}}' | grep tenant-app-service | head -n 1)"
echo "  docker exec -it \"\$APP_CONTAINER\" uv run --no-dev scripts/tenant_cli.py create --name \"Demo\" --slug demo"
echo ""
echo "Logs: cd ${DEPLOY_DIR} && docker compose -p ${PROJECT_NAME} logs -f"
