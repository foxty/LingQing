#!/bin/bash
# Build and push shared frontend gateway image (tenant app + tenant manager portals)
#
# USAGE:
#   ./build-frontend.sh <REGISTRY> <VERSION>
#   ./build-frontend.sh <REGISTRY> <VERSION> --ci
#
# EXAMPLES:
#   ./build-frontend.sh myregistry.com/app v1.0.0
#   ./build-frontend.sh myregistry.com/app v1.0.1 --ci

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$DEPLOY_ROOT/.." && pwd)"
DOCKER_DIR="$DEPLOY_ROOT/docker"

# Parse arguments
REGISTRY_URL=""
VERSION=""
CI_MODE=false
TAG_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --ci|--auto-push)
            CI_MODE=true
            shift
        ;;
        --skip-push)
            SKIP_PUSH=true
            shift
        ;;
        --tag-only)
            TAG_ONLY=true
            shift
        ;;
        *)
            if [[ -z "$REGISTRY_URL" ]]; then
                REGISTRY_URL="$1"
                elif [[ -z "$VERSION" ]]; then
                VERSION="$1"
            else
                echo -e "${RED}Error: Unknown argument '$1'${NC}"
                exit 1
            fi
            shift
        ;;
    esac
done

# Validate parameters
if [[ -z "$REGISTRY_URL" ]] || [[ -z "$VERSION" ]]; then
    echo -e "${RED}Error: REGISTRY and VERSION are required${NC}"
    echo ""
    echo "Usage: $0 <REGISTRY> <VERSION> [--ci]"
    echo ""
    echo "Examples:"
    echo "  $0 myregistry.com/app v1.0.0"
    echo "  $0 myregistry.com/app v1.0.1 --ci"
    exit 1
fi

echo ""
echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Frontend Build${NC}"
echo -e "${YELLOW}========================================${NC}"
echo "Registry: $REGISTRY_URL"
echo "Version:  $VERSION"
echo ""

# Build frontend image
echo -e "${BLUE}Building frontend image...${NC}"
docker build \
-f "${DOCKER_DIR}/Dockerfile.frontend" \
-t "${REGISTRY_URL}/frontend:${VERSION}" \
-t "${REGISTRY_URL}/frontend:latest" \
"$PROJECT_ROOT"

if [[ $? -eq 0 ]]; then
    echo -e "${GREEN}✓ Frontend image built successfully${NC}"
    
    # Push image
    if [[ "$SKIP_PUSH" != true ]]; then
        if [[ "$CI_MODE" == true ]]; then
            echo -e "${BLUE}Pushing frontend images...${NC}"
            docker push "${REGISTRY_URL}/frontend:${VERSION}"
            if [[ "$TAG_ONLY" != true ]]; then
                docker push "${REGISTRY_URL}/frontend:latest"
            fi
            echo -e "${GREEN}✓ Frontend images pushed${NC}"
        else
            read -p "Push frontend image to registry? (y/n) " -n 1 -r
            echo ""
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo -e "${BLUE}Pushing frontend images...${NC}"
                docker push "${REGISTRY_URL}/frontend:${VERSION}"
                if [[ "$TAG_ONLY" != true ]]; then
                    docker push "${REGISTRY_URL}/frontend:latest"
                fi
                echo -e "${GREEN}✓ Frontend images pushed${NC}"
            fi
        fi
    fi
else
    echo -e "${RED}✗ Frontend image build failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Frontend Build Complete! 🎉${NC}"
echo -e "${GREEN}========================================${NC}"
echo "Image:  ${REGISTRY_URL}/frontend:${VERSION}"
echo "Latest: ${REGISTRY_URL}/frontend:latest"
echo ""
