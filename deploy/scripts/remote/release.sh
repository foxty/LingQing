#!/bin/bash
# Build locally, push to registry, and deploy to a remote host.
#
# USAGE:
#   ./release.sh <REMOTE_HOST> <REGISTRY_URL> <ENV_FILE> [VERSION] [STACK]
#
# PREREQUISITES:
#   - Docker running locally and on remote host
#   - SSH access to remote host (key-based auth)
#   - Remote user has docker permissions
#   - Registry credentials configured locally
#
# EXAMPLES:
#   ./release.sh prod.example.com myregistry.com/app .env.prod
#   ./release.sh user@192.168.1.100 myregistry.com/app .env.prod v1.2.0
#   ./release.sh prod.example.com myregistry.com/app .env.prod v1.0.0 app

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_ROOT="$(cd "$DEPLOY_ROOT/.." && pwd)"

REMOTE_HOST="${1}"
REGISTRY_URL="${2}"
ENV_FILE="${3}"
VERSION="${4:-$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo 'local')}"
STACK="${5:-all}"

if [[ "$REMOTE_HOST" == *"@"* ]]; then
    DEPLOY_USER="${REMOTE_HOST%%@*}"
    DEPLOY_HOST="${REMOTE_HOST#*@}"
else
    DEPLOY_USER="$(whoami)"
    DEPLOY_HOST="$REMOTE_HOST"
fi

if [[ -z "$REMOTE_HOST" ]] || [[ -z "$REGISTRY_URL" ]] || [[ -z "$ENV_FILE" ]]; then
    echo -e "${RED}Error: REMOTE_HOST, REGISTRY_URL, and ENV_FILE are required${NC}"
    echo ""
    echo "Usage: $0 <REMOTE_HOST> <REGISTRY_URL> <ENV_FILE> [VERSION] [STACK]"
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

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Release (build + deploy)${NC}"
echo -e "${YELLOW}========================================${NC}"
echo "Remote Host:  $DEPLOY_HOST"
echo "Deploy User:  $DEPLOY_USER"
echo "Registry:     $REGISTRY_URL"
echo "Env File:     $ENV_FILE"
echo "Version:      $VERSION"
echo "Stack:        $STACK"
echo ""

echo -e "${YELLOW}[1/2] Building and pushing images...${NC}"
"$DEPLOY_ROOT/scripts/build-backend.sh" "$REGISTRY_URL" "$VERSION" --ci
"$DEPLOY_ROOT/scripts/build-frontend.sh" "$REGISTRY_URL" "$VERSION" --ci
echo -e "${GREEN}✓ Images built and pushed${NC}"
echo ""

echo -e "${YELLOW}[2/2] Deploying to remote host...${NC}"
"$SCRIPT_DIR/deploy.sh" "$VERSION" "$REGISTRY_URL" "$DEPLOY_HOST" "$DEPLOY_USER" "$ENV_FILE" "$STACK"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Release complete${NC}"
echo -e "${GREEN}========================================${NC}"
