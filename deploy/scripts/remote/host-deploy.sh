#!/usr/bin/env bash
# Deploy LingQing on this host using pre-built registry images (no repo clone).
# Release bundles ship this script as bootstrap.sh for end users.
#
# Usage:
#   ./host-deploy.sh --version v2.0.0 [OPTIONS]
#
# Environment (alternatives to flags):
#   VERSION, REGISTRY_URL, GITHUB_REPO, DEPLOY_DIR, TIER
#
# Examples:
#   # From release tarball (files already extracted):
#   cp .env.template .env && $EDITOR .env
#   ./bootstrap.sh --version v2.0.0
#
#   # One-liner on host (downloads bundle from GitHub Release):
#   curl -fsSL https://github.com/ORG/REPO/releases/download/v2.0.0/bootstrap.sh \
#     | VERSION=v2.0.0 REGISTRY_URL=ghcr.io/ORG/lingqing GITHUB_REPO=ORG/REPO bash

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

VERSION="${VERSION:-}"
REGISTRY_URL="${REGISTRY_URL:-}"
GITHUB_REPO="${GITHUB_REPO:-}"
DEPLOY_DIR="${DEPLOY_DIR:-}"
TIER="${TIER:-production}"
SKIP_PULL=false
ENV_FILE=""

normalize_tier() {
    case "$1" in
        staging|test) echo "staging" ;;
        production|prod) echo "production" ;;
        *) echo "$1" ;;
    esac
}

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

usage() {
    cat <<EOF
Usage: $0 --version VERSION [OPTIONS]

Required:
  --version VERSION       Image tag to deploy (e.g. v2.0.0)

Options:
  --registry URL          Registry prefix (default: ghcr.io/<owner>/lingqing)
  --repo OWNER/REPO       GitHub repo for release bundle download
  --dir PATH              Deploy directory (default: ~/lingqing-deploy/<tier>)
  --tier TIER             production | staging (default: production)
  --env-file PATH         Copy an existing env file to .env before deploy
  --skip-pull             Skip docker pull (images already present)
  -h, --help              Show this help

Environment variables: VERSION, REGISTRY_URL, GITHUB_REPO, DEPLOY_DIR, TIER
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            VERSION="$2"
            shift 2
            ;;
        --registry)
            REGISTRY_URL="$2"
            shift 2
            ;;
        --repo)
            GITHUB_REPO="$2"
            shift 2
            ;;
        --dir)
            DEPLOY_DIR="$2"
            shift 2
            ;;
        --tier)
            TIER="$2"
            shift 2
            ;;
        --env-file)
            ENV_FILE="$2"
            shift 2
            ;;
        --skip-pull)
            SKIP_PULL=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}Error: Unknown argument '$1'${NC}" >&2
            usage >&2
            exit 1
            ;;
    esac
done

TIER="$(normalize_tier "$TIER")"

if [[ -z "$VERSION" ]]; then
    echo -e "${RED}Error: --version is required${NC}" >&2
    usage >&2
    exit 1
fi

if [[ "$TIER" != "staging" && "$TIER" != "production" ]]; then
    echo -e "${RED}Error: Invalid tier '$TIER'. Allowed: staging, production${NC}" >&2
    exit 1
fi

GITHUB_REPO="$(infer_github_repo)"
if [[ -z "$REGISTRY_URL" && -n "$GITHUB_REPO" ]]; then
    REGISTRY_URL="ghcr.io/${GITHUB_REPO%%/*}/lingqing"
fi

if [[ -z "$REGISTRY_URL" ]]; then
    echo -e "${RED}Error: Set --registry or GITHUB_REPO so REGISTRY_URL can be inferred${NC}" >&2
    exit 1
fi

if [[ -z "$DEPLOY_DIR" ]]; then
    DEPLOY_DIR="${HOME}/lingqing-deploy/${TIER}"
fi

PROJECT_NAME="lingqing-${TIER}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo ".")"

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

ensure_bundle_files() {
    if [[ -f "${SCRIPT_DIR}/docker-compose.yml" ]]; then
        mkdir -p "$DEPLOY_DIR"
        if [[ "$(cd "$SCRIPT_DIR" && pwd)" != "$(cd "$DEPLOY_DIR" && pwd)" ]]; then
            cp "${SCRIPT_DIR}/docker-compose.yml" "$DEPLOY_DIR/docker-compose.yml"
            [[ -f "${SCRIPT_DIR}/docker-compose.staging.yml" ]] && \
                cp "${SCRIPT_DIR}/docker-compose.staging.yml" "$DEPLOY_DIR/docker-compose.staging.yml"
            [[ -f "${SCRIPT_DIR}/.env.template" ]] && \
                cp "${SCRIPT_DIR}/.env.template" "$DEPLOY_DIR/.env.template"
        fi
        return
    fi

    if [[ -f "${DEPLOY_DIR}/docker-compose.yml" ]]; then
        return
    fi

    if [[ -z "$GITHUB_REPO" ]]; then
        echo -e "${RED}Error: docker-compose.yml not found and GITHUB_REPO is unset${NC}" >&2
        echo "Download the release bundle first, or set --repo OWNER/REPO." >&2
        exit 1
    fi

    local bundle_url="https://github.com/${GITHUB_REPO}/releases/download/${VERSION}/lingqing-deploy-${VERSION}.tar.gz"
    echo -e "${YELLOW}Downloading deploy bundle from release...${NC}"
    mkdir -p "$DEPLOY_DIR"
    curl -fsSL "$bundle_url" | tar -xz -C "$DEPLOY_DIR" --strip-components=1
}

mkdir -p "$DEPLOY_DIR"
ensure_bundle_files
cd "$DEPLOY_DIR"

if [[ -n "$ENV_FILE" ]]; then
    if [[ ! -f "$ENV_FILE" ]]; then
        echo -e "${RED}Error: env file not found: $ENV_FILE${NC}" >&2
        exit 1
    fi
    cp "$ENV_FILE" .env
fi

if [[ ! -f .env ]]; then
    if [[ -f .env.template ]]; then
        cp .env.template .env
        echo -e "${YELLOW}Created .env from .env.template.${NC}"
        echo "Edit ${DEPLOY_DIR}/.env, then re-run:"
        echo "  $0 --version ${VERSION} --registry ${REGISTRY_URL} --dir ${DEPLOY_DIR} --tier ${TIER}"
        exit 0
    fi
    echo -e "${RED}Error: .env not found in ${DEPLOY_DIR}${NC}" >&2
    exit 1
fi

DATA_ROOT_HOST_PATH="$(grep -E '^DATA_ROOT_HOST_PATH=' .env | tail -n 1 | cut -d= -f2- | tr -d '[:space:]' || true)"
if [[ -n "$DATA_ROOT_HOST_PATH" ]]; then
    mkdir -p "$DATA_ROOT_HOST_PATH"
fi

export VERSION
export REGISTRY_URL

COMPOSE_FILES=(-f docker-compose.yml)
if [[ "$TIER" == "staging" ]]; then
    if [[ ! -f docker-compose.staging.yml ]]; then
        echo -e "${RED}Error: docker-compose.staging.yml required for staging tier${NC}" >&2
        exit 1
    fi
    COMPOSE_FILES+=(-f docker-compose.staging.yml)
fi

echo -e "${YELLOW}LingQing host deploy${NC}"
echo "Version:      $VERSION"
echo "Registry:     $REGISTRY_URL"
echo "Tier:         $TIER"
echo "Project:      $PROJECT_NAME"
echo "Deploy dir:   $DEPLOY_DIR"
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
compose_cmd "${COMPOSE_FILES[@]}" -p "$PROJECT_NAME" config -q

echo -e "${YELLOW}Starting services...${NC}"
compose_cmd "${COMPOSE_FILES[@]}" -p "$PROJECT_NAME" up -d

if [[ "$TIER" == "staging" ]]; then
    GATEWAY_PORT=18080
    APP_HOST="app-test.example.com"
    MANAGER_HOST="manager-test.example.com"
else
    GATEWAY_PORT="$(grep -E '^GATEWAY_SERVICE_PORT=' .env | tail -n 1 | cut -d= -f2- | tr -d '[:space:]')"
    GATEWAY_PORT="${GATEWAY_PORT:-8080}"
    APP_HOST="app.example.com"
    MANAGER_HOST="manager.example.com"
fi

echo ""
echo -e "${YELLOW}Running smoke checks...${NC}"
curl -fsS -H "Host: ${APP_HOST}" "http://127.0.0.1:${GATEWAY_PORT}/health" >/dev/null
curl -fsS -H "Host: ${MANAGER_HOST}" "http://127.0.0.1:${GATEWAY_PORT}/health" >/dev/null

echo -e "${GREEN}Deployment completed successfully.${NC}"
echo ""
echo "Gateway (localhost): http://127.0.0.1:${GATEWAY_PORT}"
echo "Configure outer Nginx/TLS to proxy public domains to this port."
echo ""
echo "Create the first tenant (no repo clone required):"
echo "  APP_CONTAINER=\$(docker ps --format '{{.Names}}' | grep tenant-app-service | head -n 1)"
echo "  docker exec -it \"\$APP_CONTAINER\" uv run --no-dev scripts/tenant_cli.py create --name \"Demo\" --slug demo"
echo ""
echo "Logs:"
echo "  cd ${DEPLOY_DIR} && docker compose -p ${PROJECT_NAME} logs -f"
