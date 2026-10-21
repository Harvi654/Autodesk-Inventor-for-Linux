#!/bin/bash
# Launch Inventor under Wine with its required services, in order:
#   Identity Manager (SSO) -> Licensing Service -> Inventor.exe
# Works from a terminal or from the app-launcher entry (logs go to logs/).

set -uo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

export WINEDEBUG="${WINEDEBUG:-err+all,fixme-all}"
export DXVK_LOG_LEVEL="${DXVK_LOG_LEVEL:-info}"
export WINE_LARGE_ADDRESS_AWARE=1
# DXVK (Direct3D 9-11) and vkd3d-proton (Direct3D 12) on the same GPU
[ -n "$INV_GPU" ] && export DXVK_FILTER_DEVICE_NAME="$INV_GPU" VKD3D_FILTER_DEVICE_NAME="$INV_GPU"
# msquic= : stops .NET 8 crashing in its QUIC networking stack (README, Key Discovery #6)
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:+$WINEDLLOVERRIDES;}msquic="

TS=$(date +%Y%m%d-%H%M%S)
IDSERVICES_LOG="$P_USER/AppData/Local/Autodesk/Identity Services/Log/IdServices.log"
detect_prefix_versions
LIC_EXE="C:\\Program Files (x86)\\Common Files\\Autodesk Shared\\AdskLicensing\\$LIC_VER\\AdskLicensingService\\AdskLicensingService.exe"
IDMGR_EXE='C:\Program Files\Autodesk\AdskIdentityManager\Current\AdskIdentityManager.exe'

notify() { command -v notify-send >/dev/null && notify-send -a "$APP_TITLE" "Autodesk $APP_TITLE" "$*" || true; }

[ -f "$P_APP_BIN/$APP_EXE" ] || { err "no $APP_TITLE in $P_APP"; notify "$APP_TITLE is not installed in $WINEPREFIX"; exit 1; }
[ -n "$LIC_VER" ] || { err "AdskLicensing not found in prefix"; exit 1; }

# Files to open (from the file manager or the command line): Linux paths ->
# the Windows paths the prefix sees. With isolation that is only D: (your
# Inventor folder) and C: (the prefix itself).
WIN_ARGS=()
for a in "$@"; do
    # options and Windows paths pass through unchanged
    case "$a" in -*) WIN_ARGS+=("$a"); continue ;; esac
    if [ ! -e "$a" ]; then WIN_ARGS+=("$a"); continue; fi
    p="$(realpath "$a")" w=""
    dd="$(realpath -m "${INV_DATA_DIR:-/nonexistent}")" cd_="$(realpath -m "$WINEPREFIX/drive_c")"
    if [ -n "$INV_DATA_DIR" ] && [ "${p#"$dd"/}" != "$p" ]; then w="D:/${p#"$dd"/}"
    elif [ "${p#"$cd_"/}" != "$p" ]; then w="C:/${p#"$cd_"/}"
    elif [ "$INV_SANDBOX" != 1 ]; then w="$(winepath -w "$p" 2>/dev/null)"
    fi
    if [ -z "$w" ]; then
        err "$p is outside the folders Inventor can see - move it into ${INV_DATA_DIR:-the prefix} (D:)"
        notify "Inventor can only open files in ${INV_DATA_DIR:-~/Inventor} (drive D:). Move $(basename "$p") there."
        continue
    fi
    WIN_ARGS+=("${w//\//\\}")
done
[ $# -eq 0 ] || [ ${#WIN_ARGS[@]} -gt 0 ] || exit 1

APP_RE="$(printf '%s' "${APP_EXE,,}" | sed 's/\./\\./g')"
if pgrep -if "(^|[\\\\/])$APP_RE( |\$)" >/dev/null; then
    if [ ${#WIN_ARGS[@]} -gt 0 ]; then
        # hand the files to the running Inventor (Windows' "open" for the file type)
        for w in "${WIN_ARGS[@]}"; do info "opening $w in the running $APP_TITLE"; wine start "$w" >/dev/null 2>&1 & done
        exit 0
    fi
    warn "$APP_TITLE is already running"
    notify "$APP_TITLE is already running"
    exit 0
fi

# This project's Wine fixes are replaced when Arch updates Wine. Without them
# parts of Inventor hang or crash (Stress Analysis, Home page, ...), so say so.
if [ "$INV_WINE" = bundled ] && [ "$INV_WINE_ACTIVE" != bundled ]; then
    err "INV_WINE=bundled but this project's Wine is not installed: bash $SCRIPTS_DIR/get-wine.sh"
    notify "This project's Wine is not installed - run get-wine.sh"; exit 1
fi
if [ "$INV_WINE_OUTDATED" = 1 ]; then
    warn "using $INV_WINE_DIR - a newer build ($INV_WINE_NAME) is available: bash $SCRIPTS_DIR/get-wine.sh"
    notify "A newer Wine build for Inventor is available - run get-wine.sh"
fi
MISSING_FIXES="$(wine_fixes_missing | tr '\n' ' ')"
if [ -n "$MISSING_FIXES" ]; then
    warn "Wine fixes not installed for Wine $(wine_version): $MISSING_FIXES"
    warn "Wine was probably updated. Close Inventor and run: bash $SCRIPTS_DIR/rebuild-wine-fixes.sh"
    notify "Wine was updated - this project's Wine fixes are missing. Run rebuild-wine-fixes.sh (see README, Keeping it working)."
fi

# The adskidmgr:// login callback (adskidmgr-callback.sh, started by the
# browser) must reach THIS prefix - tell it which one is running.
ACTIVE_PREFIX_FILE="${XDG_RUNTIME_DIR:-/tmp}/inventor-on-linux.prefix"
echo "$WINEPREFIX" > "$ACTIVE_PREFIX_FILE"

cleanup() { info "shutting down Wine prefix"; wineserver -k 2>/dev/null; rm -f "$ACTIVE_PREFIX_FILE"; }
trap cleanup EXIT
trap 'exit 130' INT TERM

echo "=== $APP_TITLE $INV_YEAR | prefix $WINEPREFIX | $(wine --version 2>/dev/null) ($INV_WINE_ACTIVE${INV_WINE_DIR:+: $INV_WINE_DIR}) | logs $LOGDIR/*-$TS.log ==="

# 0. Stale Boost.Interprocess state deadlocks Identity Manager. Wipe ALL
#    session dirs, not only 01000000 (README, Open Problem #4).
info "[0/4] cleaning IDSDK IPC state"
rm -rf -- "$IDSDK_IPC_ROOT"
mkdir -p "$IDSDK_IPC_ROOT/01000000"

[ "$INV_PRODUCT" != inventor ] || migrate_disabled_addins

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
N=0
[ "$INV_PRODUCT" != inventor ] || N="$(python3 -I "$COMMON_DIR/sync-class-icons.py" "$WINEPREFIX" "$ICONREG" 2>/dev/null || echo 0)"
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

# Experimental (INV_DRIVER_NAMES=1): the display adapters' user-mode driver
# names (InstalledDisplayDrivers), which Windows drivers register and Wine
# leaves out - Inventor reports "Graphics driver file Unknown" without them and
# may refuse GPU ray tracing. Wine rewrites these keys when its display devices
# start, so this runs after that and before Inventor.
if [ "${INV_DRIVER_NAMES:-0}" = 1 ]; then
    CLS='HKLM\System\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}'
    wine reg query 'HKLM\System\CurrentControlSet\Enum\PCI' /s /v Driver 2>/dev/null | tr -d '\r' |
    while read -r line; do
        case "$line" in
            HKEY_*VEN_*) ven="${line#*VEN_}"; ven="${ven%%&*}" ;;
            Driver*REG_SZ*) n="${line##*\\}"
                case "$ven" in
                    1002) names='aticfx64\0aticfx64\0aticfx64\0amdxc64' ;;
                    10DE|10de) names='nvldumdx\0nvldumdx\0nvldumdx\0nvldumdx' ;;
                    8086) names='igdumdim64\0igd10iumd64\0igd10iumd64\0igd12umd64' ;;
                    *) continue ;;
                esac
                wine reg add "$CLS\\$n" /v InstalledDisplayDrivers /t REG_MULTI_SZ /d "$names" /f >/dev/null 2>&1 \
                    && info "    driver names for GPU $n (vendor $ven)" ;;
        esac
    done
fi

info "[4/4] launching $APP_TITLE"
cd "$P_APP_BIN" || exit 1
# Not "wine ... | tee": processes Inventor starts (WebView2, licensing agent)
# inherit the pipe, so tee - and this script - would wait for them after
# Inventor itself has exited or crashed. Write to the log and follow it instead.
LOG="$LOGDIR/inventor-$TS.log"
if [ -n "$INV_VDESKTOP" ]; then
    info "    inside Wine virtual desktop $INV_VDESKTOP"
    wine explorer "/desktop=$APP_TITLE,$INV_VDESKTOP" "$APP_EXE" "${WIN_ARGS[@]}" >>"$LOG" 2>&1 &
else
    wine "$APP_EXE" "${WIN_ARGS[@]}" >>"$LOG" 2>&1 &
fi
INV_PID=$!
# Inventor writes the old icons to HKCR (= HKLM in Wine) again while it
# starts: keep putting the per-user icons back during the first minutes (live
# registry; the .reg files on disk lag behind). A New dialog opened before
# that shows the old icons once.
[ "$INV_PRODUCT" != inventor ] || (
    python3 -I "$COMMON_DIR/sync-class-icons.py" --list "$WINEPREFIX" > "$LOGDIR/.class-icons-$TS" 2>/dev/null
    END=$(( $(date +%s) + ${INV_ICON_SYNC_SECONDS:-180} ))
    while [ "$(date +%s)" -lt "$END" ] && kill -0 "$INV_PID" 2>/dev/null; do
        while IFS=$'\t' read -r SUBKEY VALUE; do
            K="HKLM\\Software\\Classes\\$SUBKEY"
            CUR="$(wine reg query "$K" /ve </dev/null 2>/dev/null | sed -n 's/.*REG_[A-Z_]*[[:space:]]*//p' | tr -d '\r')"
            [ "$CUR" = "$VALUE" ] || wine reg add "$K" /ve /d "$VALUE" /f </dev/null >/dev/null 2>&1
        done < "$LOGDIR/.class-icons-$TS"
        sleep 3
    done
    rm -f "$LOGDIR/.class-icons-$TS"
) >/dev/null 2>&1 &
tail -n +1 -f --pid="$INV_PID" "$LOG" &
wait "$INV_PID"
RC=$?
sleep 1
info "$APP_TITLE exited (code $RC)"
