#!/bin/bash
# Launch Inventor under Wine with its required services, in order:
#   Identity Manager (SSO) -> Licensing Service -> Inventor.exe
# Works from a terminal or from the app-launcher entry (logs go to logs/).

set -uo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

export WINEDEBUG="${WINEDEBUG:-err+all,fixme-all}"
export DXVK_LOG_LEVEL="${DXVK_LOG_LEVEL:-info}"
export WINE_LARGE_ADDRESS_AWARE=1
[ -n "$INV_GPU" ] && export DXVK_FILTER_DEVICE_NAME="$INV_GPU"
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

# The adskidmgr:// login callback (adskidmgr-callback.sh, started by the
# browser) must reach THIS prefix - tell it which one is running.
ACTIVE_PREFIX_FILE="${XDG_RUNTIME_DIR:-/tmp}/inventor-on-linux.prefix"
echo "$WINEPREFIX" > "$ACTIVE_PREFIX_FILE"

cleanup() { info "shutting down Wine prefix"; wineserver -k 2>/dev/null; rm -f "$ACTIVE_PREFIX_FILE"; }
trap cleanup EXIT
trap 'exit 130' INT TERM

echo "=== Inventor $INV_YEAR | prefix $WINEPREFIX | logs $LOGDIR/*-$TS.log ==="

# 0. Stale Boost.Interprocess state deadlocks Identity Manager. Wipe ALL
#    session dirs, not only 01000000 (README, Open Problem #4).
info "[0/4] cleaning IDSDK IPC state"
rm -rf -- "$IDSDK_IPC_ROOT"
mkdir -p "$IDSDK_IPC_ROOT/01000000"

migrate_disabled_addins

info "[1/4] starting wineserver"
# Drives first: Wine records font paths in the registry when it starts, and a
# font folder without a drive letter gets a "\\??\\unix\\..." path that WPF
# cannot handle. So the font drives must exist before ANY wine process runs.
sandbox_fs
fix_font_registry
# Update the prefix only when the Wine version changed (auto-update is disabled
# by the isolation setup), then re-apply isolation in case the update re-created
# Z: or the $HOME links.
WINE_NOW="$(wine --version 2>/dev/null)"
if [ "$(cat "$WINEPREFIX/.inventor-wine-version" 2>/dev/null)" != "$WINE_NOW" ]; then
    info "    Wine changed ($WINE_NOW) - updating the prefix (once, up to a minute;
          a Wine window about updating the configuration shows meanwhile - that is normal)"
    wineboot -u >>"$LOGDIR/inventor-$TS.log" 2>&1
    wineserver -w
    sandbox_reg
    echo "$WINE_NOW" > "$WINEPREFIX/.inventor-wine-version"
fi
wineboot >>"$LOGDIR/inventor-$TS.log" 2>&1
sandbox_fs   # again after wineboot, so nothing it does can bring Z: or the $HOME links back

# Inventor registers its file type icons per user (HKCU\Software\Classes);
# Wine's shell reads the machine classes, which still hold the installer's
# old "I" icons - copy them over (from the previous run's registration).
ICONREG="$P_C/windows/temp/inventor-class-icons.reg"
N="$(python3 -I "$COMMON_DIR/sync-class-icons.py" "$WINEPREFIX" "$ICONREG" 2>/dev/null || echo 0)"
if [ "${N:-0}" -gt 0 ] 2>/dev/null; then
    import_reg_file "$ICONREG" && info "    $N file type entries updated"
fi
rm -f "$ICONREG"

info "[2/4] starting Identity Manager"
# Only look at log lines written after this point, not a previous session's "ready".
LOG_OFFSET=$(stat -c %s "$IDSERVICES_LOG" 2>/dev/null || echo 0)
wine "$IDMGR_EXE" >"$LOGDIR/idmgr-$TS.log" 2>&1 &
READY=0
for i in $(seq 1 45); do
    sleep 1
    if tail -c +"$((LOG_OFFSET + 1))" "$IDSERVICES_LOG" 2>/dev/null | grep -c "SSO Server is ready" >/dev/null; then
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
# Not "wine ... | tee": processes Inventor starts (WebView2, licensing agent)
# inherit the pipe, so tee - and this script - would wait for them after
# Inventor itself has exited or crashed. Write to the log and follow it instead.
LOG="$LOGDIR/inventor-$TS.log"
if [ -n "$INV_VDESKTOP" ]; then
    info "    inside Wine virtual desktop $INV_VDESKTOP"
    wine explorer "/desktop=Inventor,$INV_VDESKTOP" Inventor.exe "$@" >>"$LOG" 2>&1 &
else
    wine Inventor.exe "$@" >>"$LOG" 2>&1 &
fi
INV_PID=$!
# Inventor writes the old icons to HKCR (= HKLM in Wine) again while it
# starts: put the per-user icons back once it is up (live registry, the .reg
# files on disk lag behind).
(
    sleep "${INV_ICON_SYNC_DELAY:-40}"
    kill -0 "$INV_PID" 2>/dev/null || exit 0
    python3 -I "$COMMON_DIR/sync-class-icons.py" --list "$WINEPREFIX" 2>/dev/null |
    while IFS=$'\t' read -r SUBKEY VALUE; do
        K="HKLM\\Software\\Classes\\$SUBKEY"
        CUR="$(wine reg query "$K" /ve </dev/null 2>/dev/null | sed -n 's/.*REG_[A-Z_]*[[:space:]]*//p' | tr -d '\r')"
        [ "$CUR" = "$VALUE" ] || wine reg add "$K" /ve /d "$VALUE" /f </dev/null >/dev/null 2>&1
    done
) >/dev/null 2>&1 &
tail -n +1 -f --pid="$INV_PID" "$LOG" &
wait "$INV_PID"
RC=$?
sleep 1
info "Inventor exited (code $RC)"
