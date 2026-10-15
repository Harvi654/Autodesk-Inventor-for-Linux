#!/bin/bash
# Read-only diagnostic: checks that this machine and the mounted Windows
# installation have everything rebuild-prefix.sh needs, and prints the
# component versions it will use. Changes nothing.
#
# Usage: bash scripts/check-system.sh            (report also saved to logs/)

set -u
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

REPORT="$LOGDIR/check-system-$(date +%Y%m%d-%H%M%S).txt"
exec > >(tee "$REPORT") 2>&1

PROBLEMS=0
bad()  { err "$*"; PROBLEMS=$((PROBLEMS + 1)); }
hdr()  { printf '\n%s== %s ==%s\n' "$_B" "$*" "$_N"; }
have() { command -v "$1" >/dev/null 2>&1; }

hdr "System"
info "Kernel:   $(uname -r)"
info "Distro:   $(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-?}")"
info "Session:  XDG_SESSION_TYPE=${XDG_SESSION_TYPE:-?}  WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-}  DISPLAY=${DISPLAY:-<none>}"
if have hyprctl; then
    info "Hyprland: $(hyprctl version 2>/dev/null | head -1)"
    info "Monitors: $(hyprctl monitors 2>/dev/null | awk '/^Monitor/{m=$2} /scale:/{printf "%s scale=%s  ", m, $2}')"
    info "xwayland:force_zero_scaling = $(hyprctl getoption xwayland:force_zero_scaling 2>/dev/null | awk '/int:/{print $2}')"
fi
[ -z "${DISPLAY:-}" ] && bad "DISPLAY is not set - Wine needs XWayland (check 'xwayland { enabled = true }' in Hyprland)"

hdr "GPU / Vulkan"
lspci 2>/dev/null | grep -Ei 'vga|3d|display' | sed 's/^/    /'
if have vulkaninfo; then
    vulkaninfo --summary 2>/dev/null | grep -E 'deviceName|driverName|apiVersion' | sed 's/^ */    /'
else
    warn "vulkaninfo not installed (pacman -S vulkan-tools) - can't verify Vulkan"
fi

hdr "Packages"
if grep -qE '^\[multilib\]' /etc/pacman.conf 2>/dev/null; then ok "multilib enabled"; else warn "[multilib] not enabled in /etc/pacman.conf"; fi
for p in wine wine-staging wine-mono wine-gecko winetricks hivex rsync imagemagick mingw-w64-gcc xdg-utils vulkan-icd-loader lib32-vulkan-icd-loader; do
    v="$(pacman -Q "$p" 2>/dev/null)" && info "$v" || info "($p not installed)"
done

hdr "Wine"
if have wine; then
    WV="$(wine --version 2>/dev/null)"
    info "wine --version: $WV"
    PE="$(wine_pe_dir)"
    info "PE DLL dir:     ${PE:-<not found>}"
    if [ -n "$PE" ] && strings -el "$PE/wbemprox.dll" 2>/dev/null | grep -qx Win32_TimeZone; then
        ok "wbemprox.dll already has Win32_TimeZone"
    else
        warn "wbemprox.dll is unpatched (run scripts/build-wbemprox.sh later)"
    fi
    for d in /usr/share/wine/mono "$P_C/windows/mono"; do
        [ -d "$d" ] && info "wine-mono at:   $d ($(ls "$d" 2>/dev/null | tr '\n' ' '))"
    done
else
    bad "wine not installed"
fi
have winetricks && ok "winetricks" || bad "winetricks missing"
if [ "$INV_DXVK" = system ]; then
    have setup_dxvk && ok "setup_dxvk ($(command -v setup_dxvk))" || bad "INV_DXVK=system but setup_dxvk is missing"
else
    info "DXVK: pinned $DXVK_VER from GitHub (sha256 ${DXVK_SHA256:0:12}...)$([ -f "$DOWNLOAD_DIR/dxvk-$DXVK_VER.tar.gz" ] && echo ', already downloaded')"
fi
info "Isolation: INV_SANDBOX=$INV_SANDBOX, data folder (D:) = ${INV_DATA_DIR:-<none>}"

hdr "Windows partition ($WIN_ROOT)"
if findmnt -n "$WIN_ROOT" >/dev/null 2>&1; then
    findmnt -n -o SOURCE,FSTYPE,OPTIONS "$WIN_ROOT" | sed 's/^/    /'
else
    bad "$WIN_ROOT is not a mount point. Mount it read-only, e.g.: sudo mount -t ntfs3 -o ro /dev/sdc2 $WIN_ROOT"
fi
[ -f "$WIN_ROOT/hiberfil.sys" ] && warn "hiberfil.sys present - Windows Fast Startup/hibernation is on; mount read-only only"
[ -d "$WIN_ROOT/Windows" ] || bad "$WIN_ROOT/Windows not found"

WU="$(detect_win_user)"
info "Windows user:   ${WU:-<none found>}  (override with WIN_USER=...)"
info "All profiles:   $(ls "$WIN_ROOT/Users" 2>/dev/null | tr '\n' ' ')"

hdr "Autodesk components on Windows"
chk() { if [ -e "$2" ]; then ok "$1"; else bad "$1 missing: $2"; fi; }
chk "Inventor $INV_YEAR"         "$WIN_INV/Bin/Inventor.exe"
chk "OGSFactory.dll"            "$WIN_INV/Bin/OGSFactory.dll"
detect_source_versions
info "Shared Components versions: $(ls "$WIN_ASC_BASE" 2>/dev/null | tr '\n' ' ')-> using ${ASC_VER:-<none>}"
info "AdskLicensing versions:     $(ls "$WIN_LIC_BASE" 2>/dev/null | tr '\n' ' ')-> using ${LIC_VER:-<none>}"
info "IdentityManager dirs:       $(ls "$WIN_IDMGR_BASE" 2>/dev/null | tr '\n' ' ')"
[ -n "${ASC_VER:-}" ] || bad "no Shared Components version found under $WIN_ASC_BASE"
[ -n "${LIC_VER:-}" ] || bad "no AdskLicensing version found under $WIN_LIC_BASE"
chk "IdentityManager/Current"   "$WIN_IDMGR_BASE/Current/AdskIdentityManager.exe"
chk "IdSDK SSO plugin"          "$WIN_IDMGR_BASE/Current/SSOPlugin/Current"
chk "RealDWG Shared $INV_YEAR"  "$WIN_ROOT/Program Files/Common Files/Autodesk Shared/RealDWG Shared $INV_YEAR"
chk ".NET (Program Files/dotnet)" "$WIN_ROOT/Program Files/dotnet/dotnet.exe"
info ".NET runtimes: $(ls "$WIN_ROOT/Program Files/dotnet/shared/Microsoft.NETCore.App" 2>/dev/null | tr '\n' ' ')"
info "WebView2 on Windows: $(ls "$WIN_ROOT/Program Files (x86)/Microsoft/EdgeWebView/Application" 2>/dev/null | grep -E '^[0-9.]+$' | tr '\n' ' ')"
ls "$WIN_PROGDATA/Adlm/ASR/"*.asr >/dev/null 2>&1 && ok "license cache (.asr)" || warn "no .asr license cache - you'll need the SSO login on first launch"
chk "Design Data"               "$WIN_PUBDOCS/Design Data"
chk "Templates"                 "$WIN_PUBDOCS/Templates"
[ -d "$WIN_PROGDATA/Inventor $INV_YEAR/Content Center" ] && ok "Content Center present" || info "Content Center not installed (optional)"

if have hivexget; then
    H="$WIN_ROOT/Windows/System32/config/SOFTWARE"
    CV="$(hivexget "$H" "\\Autodesk\\Inventor\\RegistryVersion$INV_REGMAJOR.0" ClientVersion 2>/dev/null)"
    info "Inventor ClientVersion (registry): ${CV:-<not readable>}"
fi
[ -f "$REG_FILE" ] && ok "registry export present ($(wc -l < "$REG_FILE") lines)" || info "registry export not made yet (scripts/export-registry.sh)"

hdr "Disk space"
NEED_GB=30
FREE_GB=$(df -BG --output=avail "$HOME" | tail -1 | tr -dc 0-9)
info "Free in \$HOME: ${FREE_GB} GB (prefix ~20 GB, +7 GB Content Center, warning below $NEED_GB GB)"
[ "${FREE_GB:-0}" -ge "$NEED_GB" ] || warn "less than $NEED_GB GB free"

hdr "Prefix"
if [ -d "$WINEPREFIX" ]; then
    info "exists: $WINEPREFIX ($(du -sh "$WINEPREFIX" 2>/dev/null | cut -f1))"
    info "drives: $(cd "$WINEPREFIX/dosdevices" 2>/dev/null && for d in ?:; do [ -e "$d" ] || [ -L "$d" ] && printf '%s->%s  ' "$d" "$(readlink "$d")"; done)"
    [ -L "$WINEPREFIX/dosdevices/z:" ] && warn "Z: maps the whole filesystem (isolation not applied)"
else
    info "not built yet: $WINEPREFIX"
fi

hdr "Result"
if [ "$PROBLEMS" -eq 0 ]; then ok "no blocking problems"; else err "$PROBLEMS blocking problem(s) above"; fi
info "Report saved to: $REPORT"
