#!/bin/bash
# Remote server deploy: pull registry images and start Docker Compose on target host.
#
# Usage:
#   ./deploy.sh <VERSION> <REGISTRY_URL> <DEPLOY_HOST> <DEPLOY_USER> <ENV_FILE> [STACK] [SSH_KEY]
#
# STACK:
#   app      = tenant-app-service + scheduler-service + gateway-service
#   manager  = tenant-manager-service + gateway-service
#   all      = all services (default)
#
# SSH_KEY:
#   Path to SSH private key (default: ~/.ssh/deploy_key, fallback to SSH agent)
#
# Staging and production use the same compose stack on separate VMs; only .env differs.

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

VERSION=${1}
REGISTRY_URL=${2}
DEPLOY_HOST=${3}
DEPLOY_USER=${4}
ENV_FILE=${5}
STACK=${6:-"all"}
SSH_KEY=${7:-""}

if [[ -z "$VERSION" ]] || [[ -z "$REGISTRY_URL" ]] || [[ -z "$DEPLOY_HOST" ]] || [[ -z "$DEPLOY_USER" ]] || [[ -z "$ENV_FILE" ]]; then
    echo -e "${RED}Error: Required parameters missing${NC}"
    echo "Usage: $0 <VERSION> <REGISTRY_URL> <DEPLOY_HOST> <DEPLOY_USER> <ENV_FILE> [STACK] [SSH_KEY]"
    echo "Example:"
    echo "  $0 v1.0.0 registry.example.com prod.example.com deploy /tmp/.env.prod app"
    exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
    echo -e "${RED}Error: ENV file not found: $ENV_FILE${NC}"
    exit 1
fi

case "$STACK" in
    all|app|manager) ;;
    *)
        echo -e "${RED}Error: Invalid STACK '$STACK'. Allowed: all, app, manager${NC}"
        exit 1
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_STACK="$DEPLOY_ROOT/compose/remote/stack.yml"
DEPLOY_DIR="~/lingqing-deploy"
PROJECT_NAME="lingqing"

SSH_OPTS=""
SCP_OPTS=""
if [[ -n "$SSH_KEY" ]] && [[ -f "$SSH_KEY" ]]; then
    SSH_OPTS="-i $SSH_KEY"
    SCP_OPTS="-i $SSH_KEY"
elif [[ -f ~/.ssh/deploy_key ]]; then
    SSH_OPTS="-i ~/.ssh/deploy_key"
    SCP_OPTS="-i ~/.ssh/deploy_key"
fi

read_env_value() {
    grep -E "^${2}=" "$1" 2>/dev/null | tail -n 1 | cut -d= -f2- | tr -d '[:space:'$'\r'']' || true
}

host_from_url() {
    echo "$1" | sed -E 's#^https?://##' | cut -d/ -f1
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

DEPLOY_ENV_FILE="$(mktemp)"
cp "$ENV_FILE" "$DEPLOY_ENV_FILE"
normalize_env_file "$DEPLOY_ENV_FILE"
expand_public_urls "$DEPLOY_ENV_FILE"
trap 'rm -f "$DEPLOY_ENV_FILE"' EXIT

GATEWAY_PORT="$(read_env_value "$DEPLOY_ENV_FILE" GATEWAY_SERVICE_PORT)"
GATEWAY_PORT="${GATEWAY_PORT:-8080}"
APP_HOST="$(host_from_url "$(read_env_value "$DEPLOY_ENV_FILE" APP_PUBLIC_URL)")"
MANAGER_HOST="$(host_from_url "$(read_env_value "$DEPLOY_ENV_FILE" MANAGER_PUBLIC_URL)")"
APP_HOST="${APP_HOST:-app.example.com}"
MANAGER_HOST="${MANAGER_HOST:-manager.example.com}"

echo -e "${YELLOW}Remote deployment${NC}"
echo "Version: $VERSION"
echo "Registry URL: $REGISTRY_URL"
echo "Target Host: $DEPLOY_USER@$DEPLOY_HOST"
echo "Stack: $STACK"
echo "Project: $PROJECT_NAME"
echo "Env File: $ENV_FILE"
echo ""

echo -e "${YELLOW}[1/3] Copying configuration to target server...${NC}"
ssh-keyscan -H "$DEPLOY_HOST" >> ~/.ssh/known_hosts 2>/dev/null || true

ssh $SSH_OPTS "$DEPLOY_USER@$DEPLOY_HOST" "mkdir -p $DEPLOY_DIR" || {
    echo -e "${RED}Error: Failed to create deployment directory on remote server${NC}"
    exit 1
}

scp $SCP_OPTS "$DEPLOY_ENV_FILE" "$DEPLOY_USER@$DEPLOY_HOST:$DEPLOY_DIR/.env"
scp $SCP_OPTS "$COMPOSE_STACK" "$DEPLOY_USER@$DEPLOY_HOST:$DEPLOY_DIR/docker-compose.yml"

echo -e "${GREEN}Files copied${NC}"
echo ""

echo -e "${YELLOW}[2/3] Deploying on target server...${NC}"
ssh $SSH_OPTS "$DEPLOY_USER@$DEPLOY_HOST" "bash -s" << REMOTE_SCRIPT
  set -e

  DEPLOY_DIR=$DEPLOY_DIR
  PROJECT_NAME=$PROJECT_NAME

  export VERSION=$VERSION
  export REGISTRY_URL=$REGISTRY_URL
  STACK="$STACK"

  IMAGES_TO_PULL=""
  COMPOSE_SERVICES=""

  if [[ "\$STACK" == "app" ]]; then
    IMAGES_TO_PULL="backend-app frontend sandbox-controller sandbox-runner"
    COMPOSE_SERVICES="tenant-app-service scheduler-service gateway-service"
  elif [[ "\$STACK" == "manager" ]]; then
    IMAGES_TO_PULL="backend-app frontend sandbox-controller sandbox-runner"
    COMPOSE_SERVICES="tenant-manager-service gateway-service"
  else
    IMAGES_TO_PULL="backend-app frontend sandbox-controller sandbox-runner"
    COMPOSE_SERVICES=""
  fi

  echo "Pulling images for stack: \$STACK"
  for image in \$IMAGES_TO_PULL; do
    echo "Pulling \$REGISTRY_URL/\$image:\$VERSION"
    docker pull \$REGISTRY_URL/\$image:\$VERSION || { echo "Failed to pull \$image"; exit 1; }
  done

  cd \$DEPLOY_DIR
  COMPOSE_FILES="-f docker-compose.yml"

  echo "Validating compose files..."
  docker-compose \$COMPOSE_FILES -p \$PROJECT_NAME config -q

  if [[ -z "\$COMPOSE_SERVICES" ]]; then
    echo "Starting/updating all services for \$PROJECT_NAME"
    docker-compose \$COMPOSE_FILES -p \$PROJECT_NAME up -d
  else
    echo "Starting/updating services: \$COMPOSE_SERVICES"
    docker-compose \$COMPOSE_FILES -p \$PROJECT_NAME up -d --no-deps \$COMPOSE_SERVICES
  fi

  echo "Deployment completed"
REMOTE_SCRIPT

echo ""
echo -e "${YELLOW}[3/3] Running smoke checks...${NC}"
if [[ "$STACK" == "manager" ]]; then
    ssh $SSH_OPTS "$DEPLOY_USER@$DEPLOY_HOST" "curl -fsS -H 'Host: $MANAGER_HOST' http://127.0.0.1:$GATEWAY_PORT/health >/dev/null"
elif [[ "$STACK" == "app" ]]; then
    ssh $SSH_OPTS "$DEPLOY_USER@$DEPLOY_HOST" "curl -fsS -H 'Host: $APP_HOST' http://127.0.0.1:$GATEWAY_PORT/health >/dev/null"
else
    ssh $SSH_OPTS "$DEPLOY_USER@$DEPLOY_HOST" "curl -fsS -H 'Host: $APP_HOST' http://127.0.0.1:$GATEWAY_PORT/health >/dev/null"
    ssh $SSH_OPTS "$DEPLOY_USER@$DEPLOY_HOST" "curl -fsS -H 'Host: $MANAGER_HOST' http://127.0.0.1:$GATEWAY_PORT/health >/dev/null"
fi

echo -e "${GREEN}Smoke checks passed${NC}"
echo ""
echo -e "${GREEN}Deployment Summary:${NC}"
echo "  Version: $VERSION"
echo "  Registry: $REGISTRY_URL"
echo "  Target: $DEPLOY_USER@$DEPLOY_HOST"
echo "  Stack: $STACK"
echo ""
echo "To check logs on remote server:"
echo "  ssh $DEPLOY_USER@$DEPLOY_HOST 'cd $DEPLOY_DIR && docker-compose -p $PROJECT_NAME logs -f'"
