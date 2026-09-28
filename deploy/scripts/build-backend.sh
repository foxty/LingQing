#!/bin/bash
# Build and push layered backend images (base + app)
# Base images are automatically versioned by uv.lock hash for content-addressable caching
#
# SIMPLE USAGE:
#   ./build-backend.sh <REGISTRY_URL> <VERSION>                # Build with auto base detection
#
# OPTIONS:
#   --skip-push     Build only, don't push
#   --ci            Non-interactive mode for CI/CD
#
# EXAMPLES:
#   ./build-backend.sh myregistry.com/app v1.0.0            # Production build
#   ./build-backend.sh myregistry.com/app main-abc123 --ci  # CI build
#   ./build-backend.sh myregistry.com/app test --skip-push  # Local test

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$DEPLOY_ROOT/.." && pwd)"
DOCKER_DIR="$DEPLOY_ROOT/docker"

# Parse arguments
REGISTRY_URL=""
APP_VERSION=""
SKIP_PUSH=false
CI_MODE=false
TAG_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-push)
            SKIP_PUSH=true
            shift
        ;;
        --ci)
            CI_MODE=true
            shift
        ;;
        --tag-only)
            TAG_ONLY=true
            shift
        ;;
        *)
            if [[ -z "$REGISTRY_URL" ]]; then
                REGISTRY_URL="$1"
                elif [[ -z "$APP_VERSION" ]]; then
                APP_VERSION="$1"
            else
                echo -e "${RED}Error: Unknown argument '$1'${NC}"
                echo "Usage: $0 <REGISTRY_URL> <VERSION> [--ci|--skip-push|--tag-only]"
                exit 1
            fi
            shift
        ;;
    esac
done

# Validate required parameters
if [[ -z "$REGISTRY_URL" ]] || [[ -z "$APP_VERSION" ]]; then
    echo -e "${RED}Error: REGISTRY_URL and VERSION are required${NC}"
    echo ""
    echo "Usage: $0 <REGISTRY_URL> <VERSION> [OPTIONS]"
    echo ""
    echo "Examples:"
    echo "  $0 myregistry.com/app v1.0.0            # Production build"
    echo "  $0 myregistry.com/app main-abc123 --ci  # CI build"
    echo "  $0 myregistry.com/app test --skip-push  # Local test"
    echo ""
    echo "Options:"
    echo "  --skip-push     Build only, don't push"
    echo "  --ci            Non-interactive mode"
    exit 1
fi

# Check if uv.lock exists
if [[ ! -f "$PROJECT_ROOT/uv.lock" ]]; then
    echo -e "${RED}Error: uv.lock not found in $PROJECT_ROOT${NC}"
    exit 1
fi

# Calculate dependency hash from uv.lock AND Dockerfile.backend-base (8 chars for readability)
# This ensures base image rebuilds when either Python deps OR system deps change
DEPS_HASH=$(cat "$PROJECT_ROOT/uv.lock" "$DOCKER_DIR/Dockerfile.backend-base" | md5sum | cut -d' ' -f1 | head -c 8)
BASE_VERSION="${DEPS_HASH}"

echo -e "${BLUE}Dependencies hash: ${DEPS_HASH}${NC}"

# Helper function: Check if image exists with output parsing for error classification
# Returns: 0=exists, 1=not found, 2=network/transient error, 3=auth error
check_image_exists() {
    local image=$1
    local output
    local exit_code
    
    # Capture docker command output (don't let set -e affect this)
    output=$(docker manifest inspect "$image" 2>&1) || exit_code=$?
    
    if [[ ${exit_code:-0} -eq 0 ]]; then
        return 0  # Image exists
    fi
    
    # Parse error output to classify failure type
    if echo "$output" | grep -qiE "manifest unknown|not found|no such manifest|does not exist"; then
        return 1  # Image doesn't exist - rebuild needed
        elif echo "$output" | grep -qiE "timeout|connection refused|network|dial tcp|i/o timeout"; then
        echo -e "${YELLOW}Network error: $output${NC}" >&2
        return 2  # Network error - should retry
        elif echo "$output" | grep -qiE "unauthorized|authentication|forbidden|denied"; then
        echo -e "${RED}Auth error: $output${NC}" >&2
        return 3  # Auth error - should fail
    else
        echo -e "${YELLOW}Unknown error: $output${NC}" >&2
        return 2  # Unknown - treat as transient, retry
    fi
}

# Helper function: Pull image with retry logic
pull_with_retry() {
    local image=$1
    local max_attempts=3
    
    for attempt in $(seq 1 $max_attempts); do
        if docker pull "$image" 2>&1; then
            return 0
        fi
        
        if [[ $attempt -lt $max_attempts ]]; then
            echo -e "${YELLOW}Pull failed (attempt $attempt/$max_attempts), retrying in ${attempt}s...${NC}"
            sleep "$attempt"
        fi
    done
    
    echo -e "${RED}✗ Failed to pull image after $max_attempts attempts${NC}"
    return 1
}

# Image names
BASE_IMAGE="${REGISTRY_URL}/backend-base:${BASE_VERSION}"
APP_IMAGE="${REGISTRY_URL}/backend-app:${APP_VERSION}"
APP_IMAGE_LATEST="${REGISTRY_URL}/backend-app:latest"
SANDBOX_RUNNER_IMAGE="${REGISTRY_URL}/sandbox-runner:${APP_VERSION}"
SANDBOX_RUNNER_IMAGE_LATEST="${REGISTRY_URL}/sandbox-runner:latest"
SANDBOX_CONTROLLER_IMAGE="${REGISTRY_URL}/sandbox-controller:${APP_VERSION}"
SANDBOX_CONTROLLER_IMAGE_LATEST="${REGISTRY_URL}/sandbox-controller:latest"

echo ""
echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Backend Build${NC}"
echo -e "${YELLOW}========================================${NC}"
echo "Registry:    $REGISTRY_URL"
echo "App Version: $APP_VERSION"
echo "Base Hash:   $BASE_VERSION"
echo ""

# Check if base image exists, with retry logic
echo -e "${BLUE}Checking for base image (hash: ${BASE_VERSION})...${NC}"

BUILD_BASE=false
MAX_CHECK_ATTEMPTS=3

for attempt in $(seq 1 $MAX_CHECK_ATTEMPTS); do
    set +e # Temporarily disable exit on error
    check_image_exists "$BASE_IMAGE"
    result=$?
    set -e # Re-enable exit on error
    
    case $result in
        0)
            # Image exists, try to pull it
            echo -e "${GREEN}✓ Base image found in registry${NC}"
            if pull_with_retry "$BASE_IMAGE"; then
                echo -e "${GREEN}✓ Base image pulled successfully${NC}"
                BUILD_BASE=false
                break
            else
                echo -e "${RED}✗ Failed to pull base image${NC}"
                exit 1
            fi
        ;;
        1)
            # Image doesn't exist - need to build
            echo -e "${YELLOW}Base image not found, will build from scratch${NC}"
            BUILD_BASE=true
            break
        ;;
        2)
            # Network/transient error - retry
            if [[ $attempt -lt $MAX_CHECK_ATTEMPTS ]]; then
                echo -e "${YELLOW}Retrying image check ($attempt/$MAX_CHECK_ATTEMPTS)...${NC}"
                sleep "$attempt"
            else
                echo -e "${RED}✗ Persistent issues checking image, assuming rebuild needed${NC}"
                BUILD_BASE=true
                break
            fi
        ;;
        3)
            # Auth error - fail immediately
            echo -e "${RED}✗ Authentication error - cannot proceed${NC}"
            exit 1
        ;;
    esac
done

# Build base image if needed
if [[ "$BUILD_BASE" == true ]]; then
    echo ""
    echo -e "${BLUE}Building base image (hash: ${BASE_VERSION})...${NC}"
    
    if docker build \
    -f "${DOCKER_DIR}/Dockerfile.backend-base" \
    -t "$BASE_IMAGE" \
    "$PROJECT_ROOT"; then
        echo -e "${GREEN}✓ Base image built successfully${NC}"
        
        # Push base image
        if [[ "$SKIP_PUSH" != true ]]; then
            if [[ "$CI_MODE" == true ]]; then
                echo -e "${BLUE}Pushing base image...${NC}"
                if docker push "$BASE_IMAGE"; then
                    echo -e "${GREEN}✓ Base image pushed${NC}"
                else
                    echo -e "${RED}✗ Failed to push base image${NC}"
                    exit 1
                fi
            else
                read -p "Push base image to registry? (y/n) " -n 1 -r
                echo ""
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    echo -e "${BLUE}Pushing base image...${NC}"
                    docker push "$BASE_IMAGE"
                    echo -e "${GREEN}✓ Base image pushed${NC}"
                fi
            fi
        fi
    else
        echo -e "${RED}✗ Base image build failed${NC}"
        exit 1
    fi
fi

# Build app image
echo ""
echo -e "${BLUE}Building app image...${NC}"

if docker build \
-f "${DOCKER_DIR}/Dockerfile.backend-app" \
--build-arg BASE_IMAGE="$BASE_IMAGE" \
-t "$APP_IMAGE" \
-t "$APP_IMAGE_LATEST" \
"$PROJECT_ROOT"; then
    echo -e "${GREEN}✓ App image built successfully${NC}"
    
    # Push app image
    if [[ "$SKIP_PUSH" != true ]]; then
        if [[ "$CI_MODE" == true ]]; then
            echo -e "${BLUE}Pushing app images...${NC}"
            docker push "$APP_IMAGE"
            if [[ "$TAG_ONLY" != true ]]; then
                docker push "$APP_IMAGE_LATEST"
            fi
            echo -e "${GREEN}✓ App images pushed${NC}"
        else
            read -p "Push app image to registry? (y/n) " -n 1 -r
            echo ""
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo -e "${BLUE}Pushing app images...${NC}"
                docker push "$APP_IMAGE"
                if [[ "$TAG_ONLY" != true ]]; then
                    docker push "$APP_IMAGE_LATEST"
                fi
                echo -e "${GREEN}✓ App images pushed${NC}"
            fi
        fi
    fi
else
    echo -e "${RED}✗ App image build failed${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}Building sandbox-runner image...${NC}"

if docker build \
-f "${DOCKER_DIR}/Dockerfile.sandbox-runner" \
-t "$SANDBOX_RUNNER_IMAGE" \
-t "$SANDBOX_RUNNER_IMAGE_LATEST" \
"$PROJECT_ROOT"; then
    echo -e "${GREEN}✓ Sandbox runner image built successfully${NC}"

    if [[ "$SKIP_PUSH" != true ]]; then
        if [[ "$CI_MODE" == true ]]; then
            echo -e "${BLUE}Pushing sandbox-runner images...${NC}"
            docker push "$SANDBOX_RUNNER_IMAGE"
            if [[ "$TAG_ONLY" != true ]]; then
                docker push "$SANDBOX_RUNNER_IMAGE_LATEST"
            fi
            echo -e "${GREEN}✓ Sandbox runner images pushed${NC}"
        else
            read -p "Push sandbox-runner image to registry? (y/n) " -n 1 -r
            echo ""
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo -e "${BLUE}Pushing sandbox-runner images...${NC}"
                docker push "$SANDBOX_RUNNER_IMAGE"
                if [[ "$TAG_ONLY" != true ]]; then
                    docker push "$SANDBOX_RUNNER_IMAGE_LATEST"
                fi
                echo -e "${GREEN}✓ Sandbox runner images pushed${NC}"
            fi
        fi
    fi
else
    echo -e "${RED}✗ Sandbox runner image build failed${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}Building sandbox-controller image...${NC}"

if docker build \
-f "${DOCKER_DIR}/Dockerfile.sandbox-controller" \
-t "$SANDBOX_CONTROLLER_IMAGE" \
-t "$SANDBOX_CONTROLLER_IMAGE_LATEST" \
"$PROJECT_ROOT"; then
    echo -e "${GREEN}✓ Sandbox controller image built successfully${NC}"

    if [[ "$SKIP_PUSH" != true ]]; then
        if [[ "$CI_MODE" == true ]]; then
            echo -e "${BLUE}Pushing sandbox-controller images...${NC}"
            docker push "$SANDBOX_CONTROLLER_IMAGE"
            if [[ "$TAG_ONLY" != true ]]; then
                docker push "$SANDBOX_CONTROLLER_IMAGE_LATEST"
            fi
            echo -e "${GREEN}✓ Sandbox controller images pushed${NC}"
        else
            read -p "Push sandbox-controller image to registry? (y/n) " -n 1 -r
            echo ""
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo -e "${BLUE}Pushing sandbox-controller images...${NC}"
                docker push "$SANDBOX_CONTROLLER_IMAGE"
                if [[ "$TAG_ONLY" != true ]]; then
                    docker push "$SANDBOX_CONTROLLER_IMAGE_LATEST"
                fi
                echo -e "${GREEN}✓ Sandbox controller images pushed${NC}"
            fi
        fi
    fi
else
    echo -e "${RED}✗ Sandbox controller image build failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Build Complete! 🎉${NC}"
echo -e "${GREEN}========================================${NC}"
echo "Base:   $BASE_IMAGE"
echo "App:    $APP_IMAGE"
echo "Latest: $APP_IMAGE_LATEST"
echo "Runner: $SANDBOX_RUNNER_IMAGE"
echo "Ctrl:   $SANDBOX_CONTROLLER_IMAGE"
echo ""
