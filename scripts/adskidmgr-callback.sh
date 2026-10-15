#!/bin/bash
# xdg-mime handler for adskidmgr:// - the browser calls this after Autodesk SSO login.
# Passes the OAuth2 code to the RUNNING Identity Manager by starting a short-lived
# client instance. Never kill wineserver here: that would end the Inventor session.

source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"
echo "$(date '+%F %T') callback: ${1%%\?*}?..." >>"$LOGDIR/adskidmgr-callback.log"

# Make sure the AdOAuth2Code event file exists for every running server instance
shopt -s nullglob
for f in "$IDSDK_IPC_ROOT"/*/IDSDKQuit-v2-*; do
    dir="$(dirname "$f")"
    pid="${f##*IDSDKQuit-v2-}"
    [[ "$pid" =~ ^[0-9]+$ ]] || continue
    [ -f "$dir/AdOAuth2Code-$pid" ] || head -c 24 /dev/zero | { printf '\x01'; tail -c 23; } > "$dir/AdOAuth2Code-$pid"
done

wine 'C:\Program Files\Autodesk\AdskIdentityManager\Current\AdskIdentityManager.exe' "$1" \
    >>"$LOGDIR/adskidmgr-callback.log" 2>&1 &
