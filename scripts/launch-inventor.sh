#!/bin/bash
# Launch Inventor under Wine with its required services, in order:
#   Identity Manager (SSO) -> Licensing Service -> Inventor.exe
# Works from a terminal or from the app-launcher entry (logs go to logs/).

set -uo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

export WINEDEBUG="${WINEDEBUG:-err+all,fixme-all}"
export DXVK_LOG_LEVEL="${DXVK_LOG_LEVEL:-info}"
export DXVK_LOG_PATH="$LOGDIR"
export DXVK_ASYNC=1
export WINE_LARGE_ADDRESS_AWARE=1
# msquic= : stops .NET 8 crashing in its QUIC networking stack (README, Key Discovery #6)
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:+$WINEDLLOVERRIDES;}msquic="

TS=$(date +%Y%m%d-%H%M%S)
IDSERVICES_LOG="$P_USER/AppData/Local/Autodesk/Identity Services/Log/IdServices.log"
detect_prefix_versions
LIC_EXE="C:\\Program Files (x86)\\Common Files\\Autodesk Shared\\AdskLicensing\\$LIC_VER\\AdskLicensingService\\AdskLicensingService.exe"
IDMGR_EXE='C:\Program Files\Autodesk\AdskIdentityManager\Current\AdskIdentityManager.exe'

notify() { command -v notify-send >/dev/null && notify-send -a "Inventor" "Autodesk Inventor" "$*" || true; }

[ -f "$P_INV/Bin/Inventor.exe" ] || { err "prefix not built: $P_INV"; notify "Prefix not built - run rebuild-prefix.sh"; exit 1; }
[ -n "$LIC_VER" ] || { err "AdskLicensing not found in prefix"; exit 1; }

if pgrep -if '(^|[\\/])inventor\.exe( |$)' >/dev/null; then
    warn "Inventor is already running"
    notify "Inventor is already running"
    exit 0
fi

cleanup() { info "shutting down Wine prefix"; wineserver -k 2>/dev/null; }
trap cleanup EXIT
trap 'exit 130' INT TERM

echo "=== Inventor $INV_YEAR | prefix $WINEPREFIX | logs $LOGDIR/*-$TS.log ==="

# 0. Stale Boost.Interprocess state deadlocks Identity Manager. Wipe ALL
#    session dirs, not only 01000000 (README, Open Problem #4).
info "[0/4] cleaning IDSDK IPC state"
rm -rf -- "$IDSDK_IPC_ROOT"
mkdir -p "$IDSDK_IPC_ROOT/01000000"

info "[1/4] starting wineserver"
wineboot -u >>"$LOGDIR/inventor-$TS.log" 2>&1

info "[2/4] starting Identity Manager"
# Only look at log lines written after this point, not a previous session's "ready".
LOG_OFFSET=$(stat -c %s "$IDSERVICES_LOG" 2>/dev/null || echo 0)
wine "$IDMGR_EXE" >"$LOGDIR/idmgr-$TS.log" 2>&1 &
READY=0
for i in $(seq 1 45); do
    sleep 1
    if tail -c +"$((LOG_OFFSET + 1))" "$IDSERVICES_LOG" 2>/dev/null | grep -q "SSO Server is ready"; then
        READY=1; ok "Identity Manager ready after ${i}s"; break
    fi
    if ! pgrep -if '(^|[\\/])adskidentitymanager\.exe( |$)' >/dev/null; then
        err "Identity Manager died:"; tail -5 "$LOGDIR/idmgr-$TS.log" | sed 's/^/      /'; break
    fi
done
[ "$READY" -eq 1 ] || warn "Identity Manager not ready after 45s - continuing (cached token may still work)"

info "[3/4] starting Licensing Service $LIC_VER"
wine "$LIC_EXE" >"$LOGDIR/licensing-$TS.log" 2>&1 &
sleep 5
pgrep -if '(^|[\\/])adsklicensingservice\.exe( |$)' >/dev/null && ok "Licensing Service running" || err "Licensing Service failed to start"

info "[4/4] launching Inventor"
cd "$P_INV/Bin" || exit 1
wine Inventor.exe "$@" 2>&1 | tee -a "$LOGDIR/inventor-$TS.log"
