#!/bin/bash
# Make a prefix that install-from-image.py filled ready to run Inventor:
# the same Wine-specific setup rebuild-prefix.sh does, without copying
# anything from a Windows installation (Autodesk's installers already put
# the files and registry entries in place).
#
# Usage: INV_PREFIX=~/.wine-invtest bash scripts/finish-install.sh [--data-dir PATH] [--no-sandbox]
#
# Windows fonts: if a Windows partition is mounted at WIN_ROOT (default
# /mnt/windows) its fonts are copied (windows-fonts.sh); otherwise a warning.

set -Eeuo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"
source "$COMMON_DIR/configure.sh"
trap 'err "failed at line $LINENO: $BASH_COMMAND (see $LOGDIR/setup-wine.log)"' ERR

while [ $# -gt 0 ]; do
    case "$1" in
        --data-dir) INV_DATA_DIR="$2"; shift ;;
        --no-sandbox) INV_SANDBOX=0 ;;
        *) die "unknown option: $1" ;;
    esac
    shift
done
: > "$LOGDIR/setup-wine.log"
_STEPS=12

step "Checking the installation in $WINEPREFIX..."
[ -f "$P_INV/Bin/Inventor.exe" ] || die "no Inventor in $P_INV - run install-from-image.py first"
[ "$(readlink -f "$WINEPREFIX")" != "$(readlink -f "$HOME/.wine-inventor$INV_YEAR")" ] \
    || [ "${INV_FINISH_MAIN:-0}" = 1 ] \
    || die "this is your working prefix - set INV_FINISH_MAIN=1 if you really mean it"
wine_stop

step "Current links (Wine leaves Autodesk's junctions as unusable 'Current?' folders)..."
cfg_current_link "$P_LIC_BASE" Current
cfg_current_link "$P_LIC_BASE" CurrentSDK AdskLicensingSDK
cfg_current_link "$P_IDMGR_BASE" Current
detect_prefix_versions
[ -n "$LIC_VER" ] || die "AdskLicensing not found in $P_LIC_BASE"
[ -n "$ASC_VER" ] || die "Shared Components not found in $P_ASC_BASE"
info "Licensing $LIC_VER | Shared Components $ASC_VER | Identity Manager $(latest_version_dir "$P_IDMGR_BASE")"

step "Windows 10 mode, X11 (XWayland) graphics driver..."
cfg_wine_mode

step "Installing DXVK ($([ "$INV_DXVK" = system ] && echo "system setup_dxvk" || echo "$DXVK_VER, pinned"))..."
install_dxvk

step "Registry: Shared Components, search path, adskidmgr:// handler..."
# The Shared Components were unpacked by us, not by Autodesk's installer -
# ASCRegistryTool writes most of this, these make sure the essentials are there.
wine_reg_add "HKLM\\SOFTWARE\\Autodesk\\SharedComponents\\$INV_YEAR" /v InstallPath /t REG_EXPAND_SZ \
    /d "C:\\Program Files\\Common Files\\Autodesk Shared\\Components\\$INV_YEAR"
wine_reg_add "HKLM\\SOFTWARE\\Autodesk\\SharedComponents\\$INV_YEAR" /v Version /t REG_EXPAND_SZ /d "$ASC_VER"
wine_reg_add 'HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment' /v Path /t REG_EXPAND_SZ \
    /d "C:\\windows\\system32;C:\\windows;C:\\windows\\system32\\wbem;C:\\Program Files\\Common Files\\Autodesk Shared\\Components\\$INV_YEAR\\$ASC_VER;C:\\Program Files\\Autodesk\\Inventor $INV_YEAR\\Bin"
IDMGR_EXE='C:\Program Files\Autodesk\AdskIdentityManager\Current\AdskIdentityManager.exe'
wine_reg_add 'HKCR\adskidmgr' /ve /t REG_SZ /d "URL:Autodesk Identity Manager Protocol"
wine_reg_add 'HKCR\adskidmgr' /v "URL Protocol" /t REG_SZ /d ""
wine_reg_add 'HKCR\adskidmgr\shell\open\command' /ve /t REG_SZ /d "\"$IDMGR_EXE\" \"%1\""
ok "registry keys set"

step "Licensing service: manual start (launch-inventor.sh runs it as a process)..."
# Under Wine it never reports "running" as a Windows service (1053/1077);
# left on automatic start, Wine would try - and time out - on every boot.
# (Wine's sc.exe has no "config" command - set the start type directly: 3 = demand)
wine_reg_add 'HKLM\SYSTEM\CurrentControlSet\Services\AdskLicensingService' /v Start /t REG_DWORD /d 3 \
    && ok "AdskLicensingService: manual start" || warn "could not change the service start type"

step "Installing IdSDK SSO plugin into the Licensing Agent..."
cfg_sso_plugin

step "Disabling non-essential and Wine-broken add-ins, known crash sources..."
cfg_disable_addins
cfg_crash_sources
cfg_wpf_stubs

step "Checking project and Home page files..."
[ -f "$P_PUBDOCS/Default.ipj" ] && ok "Default.ipj" \
    || warn "Default.ipj not found in $P_PUBDOCS - create a project in Inventor (Get Started > Projects)"
[ -f "$P_C/ProgramData/Autodesk/Inventor $INV_YEAR/WebBrowser/index.html" ] && ok "App Home page" \
    || warn "WebBrowser/index.html not found - the Home tab will stay empty"

step "WebView2 for Wine (Windows 7 + wined3d for msedgewebview2.exe, policy switches)..."
webview2_reg
ok "done"

step "Windows fonts (WPF needs Segoe UI/Arial/Tahoma)..."
if [ -d "$WIN_ROOT/Windows/Fonts" ]; then
    bash "$SCRIPTS_DIR/windows-fonts.sh" || warn "Windows fonts not copied - WPF may FailFast in TypefaceMap.MapUnresolvedCharacters"
else
    warn "no Windows fonts at $WIN_ROOT/Windows/Fonts - Inventor's ribbon/Home page may crash without Segoe UI"
fi

step "Isolation (drives, home folders)..."
wine_stop
rm -f "$WINEPREFIX/dosdevices/m:"   # the install image drive
cfg_isolation
wine_stop
wine --version > "$WINEPREFIX/.inventor-wine-version"

echo
ok "Prefix ready: $WINEPREFIX ($(du -sh "$WINEPREFIX" | cut -f1))"
info "Start it with: INV_PREFIX=$WINEPREFIX bash scripts/launch-inventor.sh"
