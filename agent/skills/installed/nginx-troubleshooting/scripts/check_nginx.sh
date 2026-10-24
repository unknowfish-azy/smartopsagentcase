#!/usr/bin/env bash

set -u

echo "======================================"
echo " SmartOps Nginx Diagnostic"
echo " Read-only mode"
echo "======================================"

echo
echo "[1] Nginx binary"

if command -v nginx >/dev/null 2>&1; then
    nginx -v
else
    echo "nginx not found"
fi

echo
echo "[2] Nginx configuration"

if command -v nginx >/dev/null 2>&1; then
    nginx -t
else
    echo "nginx not found"
fi

echo
echo "[3] Nginx service"

if command -v systemctl >/dev/null 2>&1; then
    systemctl status nginx --no-pager --plain
else
    echo "systemctl not available"
fi

echo
echo "[4] Listening ports"

if command -v ss >/dev/null 2>&1; then
    ss -lntp
else
    echo "ss not available"
fi

echo
echo "======================================"
echo " Diagnostic finished"
echo "======================================"