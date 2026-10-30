#!/usr/bin/env bash
# Reload Squid after egress/domains.custom.txt is updated (future UI sync).
#
# Usage:
#   ./deploy/scripts/egress-proxy-reload.sh [COMPOSE_PROJECT_NAME]
#
# Default project name matches remote stack: lingqing

set -euo pipefail

PROJECT_NAME="${1:-lingqing}"
CONTAINER_ID="$(docker compose -p "$PROJECT_NAME" ps -q egress-proxy 2>/dev/null | head -n 1 || true)"

if [[ -z "$CONTAINER_ID" ]]; then
    echo "egress-proxy container not found for project: ${PROJECT_NAME}" >&2
    exit 1
fi

docker exec "$CONTAINER_ID" squid -k reconfigure
echo "egress-proxy reloaded (project=${PROJECT_NAME})"
