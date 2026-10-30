#!/bin/bash
set -euo pipefail

EGRESS_DATA="/var/lib/lingqing-egress"
LOG_DIR="${EGRESS_DATA}/logs"
CUSTOM_FILE="${EGRESS_DATA}/domains.custom.txt"

mkdir -p "$LOG_DIR"

if [[ -d "$CUSTOM_FILE" ]]; then
    echo "egress-proxy: remove host directory ${CUSTOM_FILE} and recreate as a file under egress/" >&2
    exit 1
fi

if [[ ! -f "$CUSTOM_FILE" ]]; then
    : >"$CUSTOM_FILE"
fi

touch "${LOG_DIR}/access.log" "${LOG_DIR}/cache.log"
if id proxy >/dev/null 2>&1; then
    chown -R proxy:proxy "$EGRESS_DATA"
fi

rm -f /run/squid.pid /var/run/squid.pid

tail -F -n +0 "${LOG_DIR}/access.log" 2>/dev/null | sed -u 's/^/[squid-access] /' >&2 &
tail -F -n +0 "${LOG_DIR}/cache.log" 2>/dev/null | sed -u 's/^/[squid-cache] /' >&2 &

echo "egress-proxy: squid starting (host ${EGRESS_DATA}; defaults in domains.default.txt)" >&2

exec squid -NYC -f /etc/squid/squid.conf
