#!/usr/bin/env bash
set -Eeuo pipefail

URL="${1:-http://127.0.0.1/health}"
TIMEOUT="${TIMEOUT:-10}"

curl --fail --silent --show-error --max-time "$TIMEOUT" "$URL" >/dev/null
echo "health check passed: $URL"