#!/bin/bash

set -u
ENV_FILE="$HOME/.tencent-meeting-scheduler.env"

pause_before_exit() {
    printf '\nPress Enter to close this window...'
    read -r _
}

echo "Tencent Meeting API Configuration for macOS"
echo "Values will be stored in: $ENV_FILE"
echo ""

read -r -p "AppId: " app_id
read -r -p "SdkId: " sdk_id
read -r -p "SecretId: " secret_id
read -r -s -p "SecretKey (input is hidden): " secret_key
echo ""

if [[ ! "$app_id" =~ ^[0-9]+$ ]] || [[ ! "$sdk_id" =~ ^[0-9]+$ ]]; then
    echo "ERROR: AppId and SdkId must contain digits only."
    pause_before_exit
    exit 1
fi

if [ "${#app_id}" -gt "${#sdk_id}" ]; then
    echo "ERROR: AppId and SdkId appear to be reversed. AppId is normally shorter."
    pause_before_exit
    exit 1
fi

if [ -z "$secret_id" ] || [ -z "$secret_key" ]; then
    echo "ERROR: SecretId and SecretKey cannot be empty."
    pause_before_exit
    exit 1
fi

umask 077
{
    printf 'export TENCENT_MEETING_APP_ID=%q\n' "$app_id"
    printf 'export TENCENT_MEETING_SDK_ID=%q\n' "$sdk_id"
    printf 'export TENCENT_MEETING_SECRET_ID=%q\n' "$secret_id"
    printf 'export TENCENT_MEETING_SECRET_KEY=%q\n' "$secret_key"
} > "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo ""
echo "Configuration saved successfully."
echo "Stop the old service and start it again."
pause_before_exit
