#!/usr/bin/env bash

# Local Docker helper: compose/local/infra.yml (dev tier) vs full-stack.yml (e2e tier).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$DEPLOY_ROOT/.." && pwd)"
COMPOSE_FILE_DEV="$DEPLOY_ROOT/compose/local/infra.yml"
COMPOSE_FILE_E2E="$DEPLOY_ROOT/compose/local/full-stack.yml"
ENV_FILE_DEV="$PROJECT_ROOT/.env.local"
ENV_FILE_E2E="$DEPLOY_ROOT/env/.env.e2e"
ENV_TEMPLATE="$DEPLOY_ROOT/env/.env.template"
# Fixed E2E host ports — must match compose/local/full-stack.yml
E2E_POSTGRES_HOST_PORT=5433
E2E_GATEWAY_HOST_PORT=18080
COMPOSE_CMD=""
INFRA_SERVICES=(postgres chroma)
APP_SERVICES=(
    tenant-app-service
    tenant-manager-service
    gateway-service
    scheduler-service
)

print_ok() {
    printf "OK   %s\n" "$1"
}

print_fail() {
    printf "FAIL %s\n" "$1"
}

usage() {
cat <<'EOF'
Usage: deploy/scripts/local-stack.sh <command>

Commands:
    build-infra  Build sandbox runner image for dev tier (compose/local/infra.yml)
    build-e2e    Build local images required by E2E tier (compose/local/full-stack.yml)
    db-init      Initialize dev PostgreSQL (lingqing-postgres)
    infra-up     Start dev infra only (tier: dev — .env.local)
    infra-down   Stop dev infra only
    stack-up     Start full E2E stack (tier: e2e — deploy/env/.env.e2e)
    stack-down   Stop E2E stack
    status       Show container status (dev + e2e)
    logs         Tail logs: optional second arg "e2e" (default: dev)
    smoke        Run smoke checks against E2E stack
    sandbox-tools  Check sandbox-runner tool versions (git/node/npm/python)
    clean        Remove E2E stack containers and volumes
    clean-dev    Remove dev stack containers and volumes

Tiers (local):
    dev  → compose/local/infra.yml + .env.local (+ npm run dev:ta)
    e2e  → compose/local/full-stack.yml + deploy/env/.env.e2e

Clean Options:
    --dangling, -d  Also remove dangling Docker images
    --yes, -y       Skip confirmation prompt
EOF
}

require_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "ERROR: docker command not found"
        exit 1
    fi
}

resolve_compose_cmd() {
    # Prefer BuildKit when available (COPY --chmod, faster builds); classic builder still works.
    export DOCKER_BUILDKIT=1
    export COMPOSE_DOCKER_CLI_BUILD=1

    if docker compose version >/dev/null 2>&1; then
        COMPOSE_CMD="docker compose"
        elif command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_CMD="docker-compose"
    else
        echo "ERROR: docker compose command not found"
        exit 1
    fi
}

run_compose_dev() {
    # shellcheck disable=SC2086
    ${COMPOSE_CMD} --env-file "${ENV_FILE_DEV}" -f "${COMPOSE_FILE_DEV}" "$@"
}

run_compose_e2e() {
    # shellcheck disable=SC2086
    ${COMPOSE_CMD} --env-file "${ENV_FILE_E2E}" -f "${COMPOSE_FILE_E2E}" "$@"
}

ensure_files() {
    if [[ ! -f "$COMPOSE_FILE_DEV" ]]; then
        echo "ERROR: compose file not found: $COMPOSE_FILE_DEV"
        exit 1
    fi
    if [[ ! -f "$ENV_FILE_DEV" ]]; then
        echo "ERROR: env file not found: $ENV_FILE_DEV"
        exit 1
    fi
}

ensure_e2e_env() {
    ensure_files
    if [[ ! -f "$COMPOSE_FILE_E2E" ]]; then
        echo "ERROR: compose file not found: $COMPOSE_FILE_E2E"
        exit 1
    fi
    if [[ ! -f "$ENV_FILE_E2E" ]]; then
        echo "ERROR: E2E env not found: ${ENV_FILE_E2E}"
        echo "Create it from the project env template, e.g.:"
        echo "  cp \"${ENV_TEMPLATE}\" \"${ENV_FILE_E2E}\""
        echo "  # resolve placeholders, then set DB host postgres:5432, DATA_ROOT_HOST_PATH, etc. (see template)."
        echo "Or copy .env.local and override those fields for E2E."
        exit 1
    fi
}

gateway_port() {
    echo "${E2E_GATEWAY_HOST_PORT}"
}

status_code() {
    local base_url="$1"
    local host="$2"
    local path="$3"
    curl -sS -o /tmp/iv_smoke_body.txt -w "%{http_code}" -H "Host: ${host}" "${base_url}${path}" || echo "000"
}

resolve_infra_services() {
    local env_file="${1:-$ENV_FILE_DEV}"
    INFRA_SERVICES=(postgres chroma)
    local parser enabled
    parser="$(read_env_or_default DOCUMENT_PARSER default "$env_file")"
    enabled="$(read_env_or_default DOCLING_ENABLED false "$env_file")"
    if [[ "$parser" == "docling" || "$enabled" == "true" ]]; then
        INFRA_SERVICES+=(docling-serve)
    fi
}

infra_up() {
    (cd "$PROJECT_ROOT" && npm run -s link-dev-skills)
    resolve_infra_services "$ENV_FILE_DEV"
    run_compose_dev build sandbox-runner-image
    ensure_sandbox_runner_image
    run_compose_dev up -d "${INFRA_SERVICES[@]}"
    POSTGRES_CONTAINER=lingqing-postgres db_init
    run_compose_dev ps "${INFRA_SERVICES[@]}"
    local pg_port
    pg_port="$(grep -E '^TENANT_APP_DB_PORT=' "$ENV_FILE_DEV" | tail -n 1 | cut -d '=' -f2- || true)"
    pg_port="${pg_port:-5432}"
    echo
    echo "Dev infra started. Local connection info:"
    echo "  PostgreSQL: host=localhost port=${pg_port}"
    echo "  Chroma:     host=localhost port=8002"
    if [[ " ${INFRA_SERVICES[*]} " == *" docling-serve "* ]]; then
        local docling_port
        docling_port="$(read_env_or_default DOCLING_HOST_PORT 5001 "$ENV_FILE_DEV")"
        echo "  Docling:    http://127.0.0.1:${docling_port}/ui"
    fi
    echo "  Sandbox:    run 'npm run dev:ta' to start sandbox-controller locally (port 8090)"
}

ensure_sandbox_runner_image() {
    local built_image configured_image
    built_image="lingqing-dev-sandbox-runner:local"
    configured_image="$(read_env_or_default SANDBOX_RUNNER_IMAGE "sandbox-runner:dev" "$ENV_FILE_DEV")"

    if ! docker image inspect "$built_image" >/dev/null 2>&1; then
        echo "ERROR: expected local sandbox runner image not found: ${built_image}"
        echo "Run './deploy/scripts/local-stack.sh build-infra' and retry."
        return 1
    fi

    if [[ "$configured_image" == "$built_image" ]]; then
        print_ok "sandbox runner image ready: ${configured_image}"
        return 0
    fi

    docker tag "$built_image" "$configured_image"
    print_ok "sandbox runner image tagged: ${configured_image} (from ${built_image})"
}

infra_down() {
    resolve_infra_services "$ENV_FILE_DEV"
    run_compose_dev stop "${INFRA_SERVICES[@]}"
    run_compose_dev ps "${INFRA_SERVICES[@]}"
}

stack_up() {
    ensure_e2e_env
    resolve_infra_services "$ENV_FILE_E2E"
    run_compose_e2e build backend-base backend-app-image
    run_compose_e2e build sandbox-runner-image sandbox-controller
    run_compose_e2e up -d "${INFRA_SERVICES[@]}"
    POSTGRES_CONTAINER=lingqing-e2e-postgres db_init
    run_compose_e2e build gateway-service
    run_compose_e2e up -d "${APP_SERVICES[@]}"
    run_compose_e2e ps
    echo
    echo "E2E stack started. Host access:"
    echo "  Gateway:  http://app-test.example.com:${E2E_GATEWAY_HOST_PORT}  (/etc/hosts → 127.0.0.1)"
    echo "  Postgres: host=localhost port=${E2E_POSTGRES_HOST_PORT}  (migrate/tenant-cli from laptop)"
}

read_env_or_default() {
    local key="$1"
    local default_value="$2"
    local env_file="${3:-$ENV_FILE_DEV}"
    local value
    value="$(grep -E "^${key}=" "$env_file" | tail -n 1 | cut -d '=' -f2- || true)"
    if [[ -n "$value" ]]; then
        echo "$value"
    else
        echo "$default_value"
    fi
}

wait_for_postgres() {
    local container="${POSTGRES_CONTAINER:-lingqing-postgres}"
    local max_retries=30
    local i
    for i in $(seq 1 "$max_retries"); do
        if docker exec "$container" pg_isready -U postgres >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    echo "ERROR: postgres did not become ready in time (container=${container})"
    return 1
}

db_init() {
    local app_db_password manager_db_password init_script
    local env_file="${ENV_FILE_DEV}"
    if [[ "${POSTGRES_CONTAINER:-}" == lingqing-e2e-postgres ]]; then
        env_file="${ENV_FILE_E2E}"
    fi
    
    app_db_password="$(read_env_or_default TENANT_APP_DB_PASSWORD '' "$env_file")"
    
    manager_db_password="$(read_env_or_default TENANT_MANAGER_DB_PASSWORD '' "$env_file")"
    
    if [[ -z "$app_db_password" || -z "$manager_db_password" ]]; then
        echo "ERROR: TENANT_APP_DB_PASSWORD and TENANT_MANAGER_DB_PASSWORD must be set in ${env_file}"
        return 1
    fi
    
    echo "Initializing PostgreSQL roles/databases (container=${POSTGRES_CONTAINER:-lingqing-postgres})..."
    wait_for_postgres
    init_script="$PROJECT_ROOT/scripts/init_db.sh"
    
    POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-lingqing-postgres}" POSTGRES_USER=postgres \
    bash "$init_script" "$app_db_password" "$manager_db_password"
    
    print_ok "PostgreSQL initialized"
}

build_infra_images() {
    echo "Building dev infra images (sandbox runner)..."
    run_compose_dev build sandbox-runner-image
    ensure_sandbox_runner_image
    print_ok "dev infra images built"
}

build_e2e_images() {
    ensure_e2e_env
    echo "Building local E2E images..."
    echo "Step 1/3: build backend images"
    run_compose_e2e build backend-base backend-app-image
    echo "Step 2/3: build sandbox images"
    run_compose_e2e build sandbox-runner-image sandbox-controller
    echo "Step 3/3: build gateway image"
    run_compose_e2e build gateway-service
    print_ok "local E2E images built"
}

stack_down() {
    ensure_e2e_env
    run_compose_e2e down
}

show_status() {
    echo "=== dev (infra.yml) ==="
    run_compose_dev ps 2>/dev/null || true
    echo ""
    if [[ -f "$ENV_FILE_E2E" ]]; then
        echo "=== e2e (full-stack.yml) ==="
        run_compose_e2e ps 2>/dev/null || true
    else
        echo "=== e2e (full-stack.yml) === (no deploy/env/.env.e2e yet)"
    fi
}

show_logs() {
    local target="${1:-dev}"
    if [[ "$target" == "e2e" ]]; then
        ensure_e2e_env
        run_compose_e2e logs -f
    else
        run_compose_dev logs -f
    fi
}

cleanup_dangling_images() {
    echo "Cleaning dangling Docker images..."
    local dangling_images
    dangling_images="$(docker images -f "dangling=true" -q)"
    
    if [[ -z "$dangling_images" ]]; then
        print_ok "no dangling images found"
        return 0
    fi
    
    docker rmi $dangling_images
    print_ok "dangling images removed"
}

clean_env() {
    local clean_dangling=false
    local skip_confirm=false
    
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dangling|-d)
                clean_dangling=true
            ;;
            --yes|-y)
                skip_confirm=true
            ;;
            --help|-h)
                echo "Usage: deploy/scripts/local-stack.sh clean [--dangling|-d] [--yes|-y]"
                return 0
            ;;
            *)
                echo "ERROR: unknown clean option: $1"
                echo "Usage: deploy/scripts/local-stack.sh clean [--dangling|-d] [--yes|-y]"
                return 1
            ;;
        esac
        shift
    done
    
    if [[ "$skip_confirm" != "true" ]]; then
        read -r -p "This will stop and remove E2E stack containers and volumes. Continue? (y/n) " reply
        if [[ ! "$reply" =~ ^[Yy]$ ]]; then
            echo "Cleanup cancelled"
            return 0
        fi
    fi
    
    echo "Stopping and removing E2E stack containers + volumes (full-stack.yml)..."
    ensure_e2e_env
    run_compose_e2e down -v
    print_ok "E2E stack resources cleaned"
    
    echo "Removing local E2E images if present..."
    docker rmi lingqing-e2e-backend-base:local 2>/dev/null || true
    docker rmi lingqing-e2e-backend-app:local 2>/dev/null || true
    docker rmi lingqing-e2e-sandbox-controller:local 2>/dev/null || true
    docker rmi lingqing-e2e-sandbox-runner:local 2>/dev/null || true
    docker rmi lingqing-e2e-gateway-service:local 2>/dev/null || true
    print_ok "E2E images cleanup completed"
    
    if [[ "$clean_dangling" == "true" ]]; then
        cleanup_dangling_images
    fi
    
    echo "Cleanup complete"
    echo "Run './deploy/scripts/local-stack.sh stack-up' to set up the E2E stack again"
}

clean_dev_env() {
    local clean_dangling=false
    local skip_confirm=false
    
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dangling|-d)
                clean_dangling=true
            ;;
            --yes|-y)
                skip_confirm=true
            ;;
            --help|-h)
                echo "Usage: deploy/scripts/local-stack.sh clean-dev [--dangling|-d] [--yes|-y]"
                return 0
            ;;
            *)
                echo "ERROR: unknown clean-dev option: $1"
                return 1
            ;;
        esac
        shift
    done
    
    if [[ "$skip_confirm" != "true" ]]; then
        read -r -p "This will stop and remove dev stack containers + volumes (infra.yml). Continue? (y/n) " reply
        if [[ ! "$reply" =~ ^[Yy]$ ]]; then
            echo "Cleanup cancelled"
            return 0
        fi
    fi
    
    echo "Stopping and removing dev stack containers + volumes..."
    run_compose_dev down -v
    print_ok "dev stack resources cleaned"
    
    if [[ "$clean_dangling" == "true" ]]; then
        cleanup_dangling_images
    fi
}

run_smoke() {
    ensure_e2e_env
    local port
    port="$(gateway_port)"
    local base_url="http://127.0.0.1:${port}"
    local failed=0
    local running
    
    echo "Running E2E stack smoke checks (full-stack.yml)"
    echo "Compose: ${COMPOSE_FILE_E2E}"
    echo "Compose command: ${COMPOSE_CMD}"
    echo "Gateway: ${base_url}"
    echo
    
    local required
    required=(
        "lingqing-e2e-postgres"
        "lingqing-e2e-chroma"
        "lingqing-e2e-sandbox-controller"
        "lingqing-e2e-tenant-app-service"
        "lingqing-e2e-tenant-manager-service"
        "lingqing-e2e-scheduler-service"
        "lingqing-e2e-gateway-service"
    )
    
    for name in "${required[@]}"; do
        running="$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null || true)"
        if [[ "$running" == "true" ]]; then
            print_ok "container running: ${name}"
        else
            print_fail "container not running: ${name}"
            failed=1
        fi
    done
    
    echo
    
    if docker exec lingqing-e2e-postgres pg_isready -U postgres >/dev/null 2>&1; then
        print_ok "postgres readiness check"
    else
        print_fail "postgres readiness check"
        failed=1
    fi
    
    if docker exec lingqing-e2e-chroma python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/heartbeat')" \
    >/dev/null 2>&1; then
        print_ok "chroma /api/v1/heartbeat -> ok (in-container)"
    else
        print_fail "chroma /api/v1/heartbeat (in-container)"
        failed=1
    fi
    
    if docker exec lingqing-e2e-sandbox-controller curl -sf http://localhost:8090/health >/dev/null 2>&1; then
        print_ok "sandbox-controller /health -> ok (in-container)"
    else
        print_fail "sandbox-controller /health (in-container)"
        failed=1
    fi
    
    echo
    
    app_health="$(status_code "$base_url" app-test.example.com /health)"
    manager_health="$(status_code "$base_url" manager-test.example.com /health)"
    default_health="$(status_code "$base_url" localhost /health)"
    
    if [[ "$app_health" == "200" ]]; then
        print_ok "app vhost /health -> 200"
    else
        print_fail "app vhost /health -> ${app_health}"
        failed=1
    fi
    
    if [[ "$manager_health" == "200" ]]; then
        print_ok "manager vhost /health -> 200"
    else
        print_fail "manager vhost /health -> ${manager_health}"
        failed=1
    fi
    
    if [[ "$default_health" == "200" ]]; then
        print_ok "default vhost /health -> 200"
    else
        print_fail "default vhost /health -> ${default_health}"
        failed=1
    fi
    
    echo
    
    app_api="$(status_code "$base_url" app-test.example.com /api/health)"
    manager_api="$(status_code "$base_url" manager-test.example.com /api/health)"
    
    if [[ "$app_api" =~ ^2[0-9][0-9]$ ]]; then
        print_ok "app stack /api/health -> ${app_api}"
    else
        print_fail "app stack /api/health -> ${app_api}"
        failed=1
    fi
    
    if [[ "$manager_api" =~ ^2[0-9][0-9]$ ]]; then
        print_ok "manager stack /api/health -> ${manager_api}"
    else
        print_fail "manager stack /api/health -> ${manager_api}"
        failed=1
    fi
    
    echo
    if [[ "$failed" -eq 0 ]]; then
        echo "All smoke checks passed"
        return 0
    fi
    
    echo "One or more checks failed"
    echo "Debug tips:"
    echo "  ${COMPOSE_CMD} --env-file ${ENV_FILE_E2E} -f ${COMPOSE_FILE_E2E} logs --tail=100 postgres"
    echo "  ${COMPOSE_CMD} --env-file ${ENV_FILE_E2E} -f ${COMPOSE_FILE_E2E} logs --tail=100 chroma"
    echo "  ${COMPOSE_CMD} --env-file ${ENV_FILE_E2E} -f ${COMPOSE_FILE_E2E} logs --tail=100 sandbox-controller"
    echo "  ${COMPOSE_CMD} --env-file ${ENV_FILE_E2E} -f ${COMPOSE_FILE_E2E} logs --tail=100 scheduler-service"
    echo "  ${COMPOSE_CMD} --env-file ${ENV_FILE_E2E} -f ${COMPOSE_FILE_E2E} logs --tail=100 gateway-service"
    echo "  ${COMPOSE_CMD} --env-file ${ENV_FILE_E2E} -f ${COMPOSE_FILE_E2E} logs --tail=100 tenant-app-service"
    echo "  ${COMPOSE_CMD} --env-file ${ENV_FILE_E2E} -f ${COMPOSE_FILE_E2E} logs --tail=100 tenant-manager-service"
    return 2
}

sandbox_tools_check() {
    local runner_image
    runner_image="$(read_env_or_default SANDBOX_RUNNER_IMAGE "sandbox-runner:dev")"
    
    echo "Checking sandbox runner tools in image: ${runner_image}"
    docker run --rm "${runner_image}" /bin/bash -lc \
    'set -e; git --version; node --version; npm --version; python --version'
    print_ok "sandbox runner tools check passed"
}

main() {
    if [[ $# -eq 0 ]]; then
        usage
        exit 0
    fi
    
    local command="$1"
    shift
    
    require_docker
    resolve_compose_cmd
    ensure_files
    
    case "$command" in
        build-infra)
            build_infra_images
        ;;
        build-e2e)
            build_e2e_images
        ;;
        db-init)
            POSTGRES_CONTAINER=lingqing-postgres db_init
        ;;
        infra-up)
            infra_up
        ;;
        infra-down)
            infra_down
        ;;
        stack-up)
            stack_up
        ;;
        stack-down)
            stack_down
        ;;
        status)
            show_status
        ;;
        logs)
            show_logs "$@"
        ;;
        smoke)
            run_smoke
        ;;
        sandbox-tools)
            sandbox_tools_check
        ;;
        clean)
            clean_env "$@"
        ;;
        clean-dev)
            clean_dev_env "$@"
        ;;
        -h|--help|help)
            usage
        ;;
        *)
            echo "ERROR: unknown command: $command"
            usage
            exit 1
        ;;
    esac
}

main "$@"
