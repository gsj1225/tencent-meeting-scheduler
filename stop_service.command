#!/bin/bash

set -u
APP_NAME="tencent-meeting-scheduler"
found=0

for port in $(seq 8080 8099); do
    health="$(curl -fsS --max-time 1 "http://127.0.0.1:$port/api/health" 2>/dev/null || true)"
    if [[ "$health" != *"$APP_NAME"* ]]; then
        continue
    fi

    pid="$(printf '%s' "$health" | sed -E 's/.*"pid"[[:space:]]*:[[:space:]]*([0-9]+).*/\1/')"
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill "$pid" 2>/dev/null; then
        echo "Stopped scheduler on port $port (PID $pid)."
        found=1
    fi
done

if [ "$found" -eq 0 ]; then
    echo "No running scheduler service was found."
fi

printf '\nPress Enter to close this window...'
read -r _
