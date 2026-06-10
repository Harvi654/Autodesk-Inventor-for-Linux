#!/bin/bash
# Handle adskidmgr:// protocol callback from browser
# DON'T kill anything - just pass the auth code to the running Identity Manager
export WINEPREFIX="$HOME/.wine-inventor2026"
IPCDIR="$WINEPREFIX/drive_c/ProgramData/Autodesk/IDSDK/6C6163686C616E/interprocess/01000000"

# Ensure the AdOAuth2Code event file exists for the running server
for f in "$IPCDIR"/IDSDKQuit-v2-*; do
    PID=$(basename "$f" | grep -oP 'v2-\K[0-9]+')
    if [ -n "$PID" ] && [ ! -f "$IPCDIR/AdOAuth2Code-$PID" ]; then
        printf '\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00' > "$IPCDIR/AdOAuth2Code-$PID"
    fi
done

# Launch client instance to pass the auth code to the running server
wine "C:\\Program Files\\Autodesk\\AdskIdentityManager\\Current\\AdskIdentityManager.exe" "$1" &>/dev/null &
