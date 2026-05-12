#!/bin/bash
# Remote server deploy: pull registry images and start Docker Compose on target host.
#
# Usage:
#   ./deploy.sh <VERSION> <REGISTRY_URL> <DEPLOY_HOST> <DEPLOY_USER> <ENV_FILE> [STACK] [TIER] [SSH_KEY]
#
# STACK:
#   app      = tenant-app-service + scheduler-service + gateway-service
#   manager  = tenant-manager-service + gateway-service
#   all      = all services (default)
#
# TIER:
#   staging | production  (aliases: test | prod)
#
# SSH_KEY:
#   Path to SSH private key (default: ~/.ssh/deploy_key, fallback to SSH agent)

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
TIER_INPUT=${7:-"production"}
SSH_KEY=${8:-""}

normalize_tier() {
    case "$1" in
        staging|test)
            echo "staging"
        ;;
        production|prod)
            echo "production"
        ;;
        *)
            echo "$1"
        ;;
    esac
}

TIER="$(normalize_tier "$TIER_INPUT")"

if [[ -z "$VERSION" ]] || [[ -z "$REGISTRY_URL" ]] || [[ -z "$DEPLOY_HOST" ]] || [[ -z "$DEPLOY_USER" ]] || [[ -z "$ENV_FILE" ]]; then
    echo -e "${RED}Error: Required parameters missing${NC}"
    echo "Usage: $0 <VERSION> <REGISTRY_URL> <DEPLOY_HOST> <DEPLOY_USER> <ENV_FILE> [STACK] [TIER] [SSH_KEY]"
    echo "Examples:"
    echo "  $0 v1.0.0 registry.example.com prod.example.com deploy /tmp/.env.prod app production"
    echo "  $0 v1.0.0 registry.example.com staging.example.com deploy /tmp/.env.staging manager staging"
    exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
    echo -e "${RED}Error: ENV file not found: $ENV_FILE${NC}"
    exit 1
fi

case "$STACK" in
    all|app|manager)
    ;;
    *)
        echo -e "${RED}Error: Invalid STACK '$STACK'. Allowed: all, app, manager${NC}"
        exit 1
    ;;
esac

case "$TIER" in
    staging|production)
    ;;
    *)
        echo -e "${RED}Error: Invalid TIER '$TIER_INPUT'. Allowed: staging, production (aliases: test, prod)${NC}"
        exit 1
    ;;
esac

if [[ "$TIER_INPUT" != "$TIER" ]]; then
    echo -e "${YELLOW}Note: tier alias '$TIER_INPUT' mapped to '$TIER'${NC}"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_STACK="$DEPLOY_ROOT/compose/remote/stack.yml"
COMPOSE_STAGING_OVERRIDE="$DEPLOY_ROOT/compose/remote/overrides/staging.yml"
DEPLOY_DIR="~/lingqing-deploy/${TIER}"
PROJECT_NAME="lingqing-${TIER}"
OVERRIDE_FILE=""

if [[ "$TIER" == "staging" ]]; then
    OVERRIDE_FILE="docker-compose.override.yml"
fi

SSH_OPTS=""
SCP_OPTS=""
if [[ -n "$SSH_KEY" ]] && [[ -f "$SSH_KEY" ]]; then
    SSH_OPTS="-i $SSH_KEY"
    SCP_OPTS="-i $SSH_KEY"
elif [[ -f ~/.ssh/deploy_key ]]; then
    SSH_OPTS="-i ~/.ssh/deploy_key"
    SCP_OPTS="-i ~/.ssh/deploy_key"
fi

echo -e "${YELLOW}Remote deployment${NC}"
echo "Version: $VERSION"
echo "Registry URL: $REGISTRY_URL"
echo "Target Host: $DEPLOY_USER@$DEPLOY_HOST"
echo "Tier: $TIER"
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

scp $SCP_OPTS "$ENV_FILE" "$DEPLOY_USER@$DEPLOY_HOST:$DEPLOY_DIR/.env"
scp $SCP_OPTS "$COMPOSE_STACK" "$DEPLOY_USER@$DEPLOY_HOST:$DEPLOY_DIR/docker-compose.yml"
if [[ "$TIER" == "staging" ]]; then
    scp $SCP_OPTS "$COMPOSE_STAGING_OVERRIDE" "$DEPLOY_USER@$DEPLOY_HOST:$DEPLOY_DIR/docker-compose.override.yml"
fi

echo -e "${GREEN}Files copied${NC}"
echo ""

echo -e "${YELLOW}[2/3] Deploying on target server...${NC}"
ssh $SSH_OPTS "$DEPLOY_USER@$DEPLOY_HOST" "bash -s" << REMOTE_SCRIPT
  set -e

  DEPLOY_DIR=$DEPLOY_DIR
  PROJECT_NAME=$PROJECT_NAME
  OVERRIDE_FILE=$OVERRIDE_FILE

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
  if [[ -n "\$OVERRIDE_FILE" ]] && [[ -f "\$OVERRIDE_FILE" ]]; then
    COMPOSE_FILES="\$COMPOSE_FILES -f \$OVERRIDE_FILE"
  fi

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
if [[ "$TIER" == "staging" ]]; then
    GATEWAY_PORT=18080
    APP_HOST="app-test.example.com"
    MANAGER_HOST="manager-test.example.com"
else
    GATEWAY_PORT=$(grep -E '^GATEWAY_SERVICE_PORT=' "$ENV_FILE" | tail -n 1 | cut -d '=' -f2 | tr -d '[:space:]')
    if [[ -z "$GATEWAY_PORT" ]]; then
        GATEWAY_PORT=8080
    fi
    APP_HOST="app.example.com"
    MANAGER_HOST="manager.example.com"
fi

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
echo "  Tier: $TIER"
echo "  Stack: $STACK"
echo ""
echo "To check logs on remote server:"
echo "  ssh $DEPLOY_USER@$DEPLOY_HOST 'cd $DEPLOY_DIR && docker-compose -p $PROJECT_NAME logs -f'"
