#!/bin/bash
# Launch Inventor 2026 under WINE with all required services
# Services must start in order: Identity Manager -> Licensing Service -> Inventor

export WINEPREFIX="$HOME/.wine-inventor2026"
export WINEARCH=win64
export WINEDEBUG=err+all,fixme-all
export DXVK_LOG_LEVEL=info
export DXVK_ASYNC=1
export WINE_LARGE_ADDRESS_AWARE=1

LOGDIR="$HOME/Projects/Inventor on linux/logs"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
IDSDK_USER=$(printf '%s' "$USER" | od -An -tx1 | tr -d ' \n' | tr '[:lower:]' '[:upper:]')
IDSDK_IPC="$WINEPREFIX/drive_c/ProgramData/Autodesk/IDSDK/$IDSDK_USER/interprocess/01000000"

# Graceful shutdown: kill WINE prefix when systemd stops this process at shutdown
cleanup() {
    echo "=== Shutting down Inventor WINE prefix ==="
    wineserver -k 2>/dev/null
}
trap cleanup SIGTERM SIGINT EXIT

echo "=== Starting Inventor 2026 on WINE ==="
echo "Timestamp: $TIMESTAMP"
echo "Log directory: $LOGDIR"

# Step 0: Clean stale IPC state
echo "[0/4] Cleaning IDSDK IPC state..."
rm -rf "$IDSDK_IPC"
mkdir -p "$IDSDK_IPC"
echo "    IPC directory cleaned"

# Step 1: Initialize wineserver
echo "[1/4] Initializing wineserver..."
wineboot -u 2>/dev/null
sleep 2

# Step 2: Start Identity Manager (SSO service)
echo "[2/4] Starting AdskIdentityManager..."
wine "C:\\Program Files\\Autodesk\\AdskIdentityManager\\Current\\AdskIdentityManager.exe" \
    2>&1 | tee "$LOGDIR/idmgr-$TIMESTAMP.log" &
IDMGR_PID=$!

# Wait for Identity Manager to be ready (check its own log file)
IDSERVICES_LOG="$WINEPREFIX/drive_c/users/$USER/AppData/Local/Autodesk/Identity Services/Log/IdServices.log"
echo "    Waiting for Identity Manager to initialize..."
IDMGR_READY=0
for i in $(seq 1 30); do
    sleep 1
    if grep -q "SSO Server is ready" "$IDSERVICES_LOG" 2>/dev/null; then
        IDMGR_READY=1
        echo "    Identity Manager: READY (SSO Server started in ${i}s)"
        break
    fi
    # Check if process died
    if ! pgrep -f "AdskIdentityManager.exe" > /dev/null; then
        echo "    Identity Manager: PROCESS DIED"
        echo "    Last lines from Wine log:"
        tail -5 "$LOGDIR/idmgr-$TIMESTAMP.log" 2>/dev/null | sed 's/^/      /'
        break
    fi
    # Show progress
    if [ $((i % 5)) -eq 0 ]; then
        echo "    ... waiting ${i}s"
    fi
done

if [ $IDMGR_READY -eq 0 ]; then
    echo "    Identity Manager: DID NOT REACH READY STATE (30s timeout)"
    echo "    Last 10 lines of IdServices log:"
    tail -10 "$IDSERVICES_LOG" 2>/dev/null | sed 's/^/      /'
    echo ""
    echo "    Continuing anyway (licensing may use cached tokens)..."
fi

# Check IPC state
echo "    IPC files after IdMgr start:"
ls -la "$IDSDK_IPC/" 2>/dev/null | sed 's/^/      /'

# Step 3: Start Licensing Service
echo "[3/4] Starting AdskLicensingService..."
wine "C:\\Program Files (x86)\\Common Files\\Autodesk Shared\\AdskLicensing\\15.4.2.4\\AdskLicensingService\\AdskLicensingService.exe" \
    2>&1 | tee "$LOGDIR/licensing-$TIMESTAMP.log" &
sleep 5

# Verify it's running
if pgrep -f "AdskLicensingService.exe" > /dev/null; then
    echo "    Licensing Service: RUNNING"
else
    echo "    Licensing Service: FAILED TO START"
fi

# Step 4: Launch Inventor
echo "[4/4] Launching Inventor 2026..."
cd "$WINEPREFIX/drive_c/Program Files/Autodesk/Inventor 2026/Bin"
wine Inventor.exe "$@" 2>&1 | tee "$LOGDIR/inventor-$TIMESTAMP.log"
