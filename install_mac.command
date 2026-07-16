#!/bin/bash

set -u
cd "$(dirname "$0")" || exit 1

pause_before_exit() {
    printf '\nPress Enter to close this window...'
    read -r _
}

echo "Tencent Meeting Scheduler - macOS Setup"
echo "========================================="

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 was not found. Install Python 3.11 or newer first."
    pause_before_exit
    exit 1
fi

echo "Python: $(python3 --version 2>&1)"
echo "Creating local virtual environment..."
if ! python3 -m venv .venv; then
    echo "ERROR: Failed to create .venv."
    pause_before_exit
    exit 1
fi

echo "Installing dependencies..."
if ! .venv/bin/python -m pip install -r requirements.txt; then
    echo "ERROR: Dependency installation failed. Check your network and try again."
    pause_before_exit
    exit 1
fi

echo ""
echo "Setup completed successfully."
echo "Next: double-click configure_api.command, then start_service.command."
pause_before_exit
