#!/bin/bash

set -u
cd "$(dirname "$0")" || exit 1

APP_NAME="tencent-meeting-scheduler"
ENV_FILE="$HOME/.tencent-meeting-scheduler.env"

if [ -f "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
fi

if [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
else
    echo "ERROR: python3 was not found. Run install_mac.command first."
    printf '\nPress Enter to close this window...'
    read -r _
    exit 1
fi

echo "Tencent Meeting Scheduler"
echo "Checking ports..."

selected_port=""
for port in $(seq 8080 8099); do
    health="$(curl -fsS --max-time 1 "http://127.0.0.1:$port/api/health" 2>/dev/null || true)"
    if [[ "$health" == *"$APP_NAME"* ]]; then
        echo "Service is already running on port $port."
        open "http://localhost:$port"
        exit 0
    fi
    if ! lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
        selected_port="$port"
        break
    fi
done

if [ -z "$selected_port" ]; then
    echo "ERROR: Ports 8080-8099 are all in use."
    printf '\nPress Enter to close this window...'
    read -r _
    exit 1
fi

if [ "$selected_port" != "8080" ]; then
    echo "Port 8080 is in use. Using port $selected_port instead."
fi

missing_credentials=0
for name in TENCENT_MEETING_APP_ID TENCENT_MEETING_SDK_ID TENCENT_MEETING_SECRET_ID TENCENT_MEETING_SECRET_KEY; do
    if [ -z "$(printenv "$name" 2>/dev/null)" ]; then
        missing_credentials=1
    fi
done
if [ "$missing_credentials" -eq 1 ]; then
    echo "WARNING: Tencent Meeting API variables are incomplete."
    echo "Run configure_api.command before using synchronization."
fi

export SCHEDULE_PORT="$selected_port"
export SCHEDULE_BIND_HOST="127.0.0.1"
export SCHEDULE_OPEN_BROWSER="1"

echo "Starting http://localhost:$selected_port"
exec "$PYTHON" server.py
