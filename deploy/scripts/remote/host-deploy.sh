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
WITH_POSTGRES=false
PROJECT_NAME="lingqing"
BUNDLED_POSTGRES_PROFILE="bundled-postgres"

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
    local raw
    raw="$(grep -E "^${key}=" "$env_file" 2>/dev/null | tail -n 1 | cut -d= -f2- || true)"
    # Trim CR and leading/trailing whitespace only (do not use broken tr '[:space:'… — it deletes "a")
    printf '%s' "$raw" | sed -e 's/\r$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
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

normalize_bundled_postgres_env() {
    local env_file="$1"

    [[ "$WITH_POSTGRES" == "true" ]] || return 0

    echo -e "${YELLOW}Applying bundled Postgres defaults to .env${NC}"
    if [[ -z "$(read_env_value "$env_file" TENANT_APP_DB_HOST)" ]]; then
        set_env_value "$env_file" TENANT_APP_DB_HOST "postgres"
    fi
    if [[ -z "$(read_env_value "$env_file" TENANT_MANAGER_DB_HOST)" ]]; then
        set_env_value "$env_file" TENANT_MANAGER_DB_HOST "postgres"
    fi
    set_env_value "$env_file" TENANT_APP_DB_PORT "5432"
    set_env_value "$env_file" TENANT_MANAGER_DB_PORT "5432"
    if [[ "$(read_env_value "$env_file" TENANT_APP_DB_SSL_MODE)" == "require" ]]; then
        set_env_value "$env_file" TENANT_APP_DB_SSL_MODE "prefer"
    fi
    if [[ "$(read_env_value "$env_file" TENANT_MANAGER_DB_SSL_MODE)" == "require" ]]; then
        set_env_value "$env_file" TENANT_MANAGER_DB_SSL_MODE "prefer"
    fi
    if [[ -z "$(read_env_value "$env_file" POSTGRES_USER)" ]]; then
        set_env_value "$env_file" POSTGRES_USER "postgres"
    fi
}

validate_bundled_postgres_env() {
    local env_file="$1"
    local errors=0

    [[ "$WITH_POSTGRES" == "true" ]] || return 0

    if [[ -z "$(read_env_value "$env_file" POSTGRES_PASSWORD)" ]]; then
        echo "  ✗ POSTGRES_PASSWORD (required for --with-postgres — superuser for bundled Postgres container)"
        errors=$((errors + 1))
    fi
    if [[ "$(read_env_value "$env_file" TENANT_APP_DB_HOST)" != "postgres" ]]; then
        echo -e "${YELLOW}  Note:${NC} TENANT_APP_DB_HOST is not 'postgres' — ensure it resolves on the compose network"
    fi

    if [[ "$errors" -gt 0 ]]; then
        return 1
    fi
    return 0
}

wait_for_bundled_postgres() {
    local container_id attempt=1 max_attempts=60

    container_id="$(compose_cmd -f docker-compose.yml -p "$PROJECT_NAME" ps -q postgres 2>/dev/null | head -n 1)"
    if [[ -z "$container_id" ]]; then
        echo -e "${RED}Error: bundled postgres container not found${NC}" >&2
        return 1
    fi

    while [[ "$attempt" -le "$max_attempts" ]]; do
        local pg_user
        pg_user="$(read_env_value ".env" POSTGRES_USER)"
        pg_user="${pg_user:-postgres}"
        if docker exec "$container_id" pg_isready -U "$pg_user" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done
    echo -e "${RED}Error: bundled postgres did not become ready in time${NC}" >&2
    return 1
}

run_bundled_postgres_init() {
    local env_file="$1"
    local app_pass manager_pass container_id init_script

    app_pass="$(read_env_value "$env_file" TENANT_APP_DB_PASSWORD)"
    manager_pass="$(read_env_value "$env_file" TENANT_MANAGER_DB_PASSWORD)"
    init_script="${DEPLOY_DIR}/init_db.sh"
    if [[ ! -x "$init_script" ]]; then
        init_script="${SCRIPT_DIR}/init_db.sh"
    fi
    if [[ ! -f "$init_script" ]]; then
        echo -e "${RED}Error: init_db.sh not found in bundle${NC}" >&2
        return 1
    fi

    container_id="$(compose_cmd -f docker-compose.yml -p "$PROJECT_NAME" ps -q postgres | head -n 1)"
    echo -e "${YELLOW}Initializing application databases (init_db.sh)...${NC}"
    POSTGRES_CONTAINER="$container_id" POSTGRES_USER="$(read_env_value "$env_file" POSTGRES_USER)" \
        bash "$init_script" "$app_pass" "$manager_pass"
}

wait_for_gateway_health() {
    local host="$1"
    local port="$2"
    local attempt=1
    local max_attempts=30

    while [[ "$attempt" -le "$max_attempts" ]]; do
        if curl -fsS -H "Host: ${host}" "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done
    return 1
}

validate_env_file() {
    local env_file="$1"
    local template="${2:-.env.template}"
    local errors=0
    local line key template_value value

    echo "Validating ${env_file} against ${template}..."
    if [[ ! -f "$template" ]]; then
        echo -e "  ${RED}✗${NC} template not found: ${template}"
        return 1
    fi

    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || continue

        key="${line%%=*}"
        template_value="${line#*=}"
        template_value="$(printf '%s' "$template_value" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

        # Dev/repo templates use generate-env placeholders; release .env.template uses literal values.
        if [[ "$template_value" =~ ^\<(env|secret): ]]; then
            continue
        fi

        if ! grep -q "^${key}=" "$env_file" 2>/dev/null; then
            echo "  ✗ ${key} (missing from .env — copy from ${template})"
            errors=$((errors + 1))
            continue
        fi

        value="$(read_env_value "$env_file" "$key")"

        if [[ -z "$template_value" && -z "$value" ]]; then
            if [[ "$key" == "TENANT_MANAGER_DB_HOST" && -n "$(read_env_value "$env_file" TENANT_APP_DB_HOST)" ]]; then
                continue
            fi
            echo "  ✗ ${key} (empty — set in FILL BEFORE DEPLOY section of ${template})"
            errors=$((errors + 1))
        fi

        if [[ "$key" == "APP_PUBLIC_URL" || "$key" == "MANAGER_PUBLIC_URL" ]]; then
            if [[ "$value" == *example.com* ]]; then
                echo "  ✗ ${key} still uses example.com — set your domains"
                errors=$((errors + 1))
            fi
        fi
    done < "$template"

    if [[ "$errors" -gt 0 ]]; then
        echo ""
        echo "Fix the items above, then re-run deploy."
        return 1
    fi

    echo "  ✓ .env matches ${template}"
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
  --with-postgres         Start Postgres in compose (demo/internal VM; not for prod HA)
  -h, --help              Show this help

Setup (before deploy):
  cp .env.template .env
  Edit empty variables in .env (bootstrap validates .env against .env.template)

Examples:
  ${SCRIPT_NAME} --version v2.0.0 --registry ghcr.io/foxty/lingqing
  ${SCRIPT_NAME} --version v2.0.0 --registry ghcr.io/foxty/lingqing --with-postgres
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
        --with-postgres) WITH_POSTGRES=true; shift ;;
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
normalize_bundled_postgres_env ".env"
expand_public_urls ".env"
validate_env_file ".env" ".env.template" || exit 1
validate_bundled_postgres_env ".env" || exit 1

export COMPOSE_PROJECT_NAME="$PROJECT_NAME"
if [[ "$WITH_POSTGRES" == "true" ]]; then
    export COMPOSE_PROFILES="$BUNDLED_POSTGRES_PROFILE"
fi

DATA_ROOT_HOST_PATH="$(read_env_value ".env" DATA_ROOT_HOST_PATH)"
if [[ -n "$DATA_ROOT_HOST_PATH" ]]; then
    mkdir -p "$DATA_ROOT_HOST_PATH"
    # backend-app runs as uid 1000 (appuser); bind mount must be writable in-container
    if ! chown 1000:1000 "$DATA_ROOT_HOST_PATH" 2>/dev/null; then
        if sudo -n chown 1000:1000 "$DATA_ROOT_HOST_PATH" 2>/dev/null; then
            :
        else
            echo -e "${YELLOW}Warning:${NC} could not chown ${DATA_ROOT_HOST_PATH} to 1000:1000."
            echo "  Run: sudo chown -R 1000:1000 ${DATA_ROOT_HOST_PATH}"
        fi
    fi
fi

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
echo "Postgres:    $([[ "$WITH_POSTGRES" == "true" ]] && echo "bundled (profile ${BUNDLED_POSTGRES_PROFILE})" || echo "external (TENANT_*_DB_HOST)")"
echo ""

if [[ "$SKIP_PULL" != "true" ]]; then
    echo -e "${YELLOW}Pulling images...${NC}"
    for image in backend-app frontend sandbox-controller sandbox-runner; do
        echo "  ${REGISTRY_URL}/${image}:${VERSION}"
        docker pull "${REGISTRY_URL}/${image}:${VERSION}"
    done
    if [[ "$WITH_POSTGRES" == "true" ]]; then
        echo "  postgres:16-alpine"
        docker pull postgres:16-alpine
    fi
    echo ""
fi

COMPOSE_PROFILE_FLAGS=( )
if [[ "$WITH_POSTGRES" == "true" ]]; then
    COMPOSE_PROFILE_FLAGS=(--profile "$BUNDLED_POSTGRES_PROFILE")
fi

echo -e "${YELLOW}Validating compose configuration...${NC}"
compose_cmd -f docker-compose.yml -p "$PROJECT_NAME" "${COMPOSE_PROFILE_FLAGS[@]}" config -q

if [[ "$WITH_POSTGRES" == "true" ]]; then
    echo -e "${YELLOW}Starting bundled Postgres...${NC}"
    compose_cmd -f docker-compose.yml -p "$PROJECT_NAME" "${COMPOSE_PROFILE_FLAGS[@]}" up -d postgres
    wait_for_bundled_postgres
    run_bundled_postgres_init ".env"
fi

echo -e "${YELLOW}Starting services...${NC}"
compose_cmd -f docker-compose.yml -p "$PROJECT_NAME" "${COMPOSE_PROFILE_FLAGS[@]}" up -d

echo ""
echo -e "${YELLOW}Running smoke checks (waiting for gateway)...${NC}"
if ! wait_for_gateway_health "$APP_HOST" "$GATEWAY_PORT"; then
    echo -e "${RED}Gateway health check failed for Host: ${APP_HOST}${NC}" >&2
    echo "Check: docker compose -p ${PROJECT_NAME} logs gateway-service tenant-app-service" >&2
    exit 1
fi
if ! wait_for_gateway_health "$MANAGER_HOST" "$GATEWAY_PORT"; then
    echo -e "${RED}Gateway health check failed for Host: ${MANAGER_HOST}${NC}" >&2
    exit 1
fi

echo -e "${GREEN}Deployment completed successfully.${NC}"
echo ""
echo "Configure outer Nginx/TLS to proxy ${APP_HOST} and ${MANAGER_HOST} to 127.0.0.1:${GATEWAY_PORT}"
echo ""
echo "Create the first tenant:"
echo "  APP_CONTAINER=\$(docker ps --format '{{.Names}}' | grep tenant-app-service | head -n 1)"
echo "  docker exec -it \"\$APP_CONTAINER\" uv run --no-dev scripts/tenant_cli.py create --name \"Demo\" --slug demo"
echo ""
echo "Logs: cd ${DEPLOY_DIR} && docker compose -p ${PROJECT_NAME} logs -f"
