# shellcheck shell=bash
# shellcheck disable=SC2034  # variables are used by the scripts that source this file
# Shared settings and auto-detection for all Inventor-on-Linux scripts.
#
# Source it from a script in scripts/:
#     source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
#
# Every value can be overridden from the environment or from a config file
# (first found wins, later ones override earlier ones):
#     $PROJECT_DIR/config.env                     (gitignored, per-checkout)
#     ${XDG_CONFIG_HOME:-~/.config}/inventor-on-linux/config.env
#
# Useful overrides:
#     WIN_ROOT=/mnt/windows        Mounted Windows partition with Inventor installed
#     WIN_USER=<name>              Windows profile to copy settings from
#     INV_YEAR=2026                Inventor release
#     INV_PREFIX=~/.wine-inventor2026
#     ASC_VER / LIC_VER            Force a component version instead of detecting it

# --- locations ---------------------------------------------------------------
COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(dirname "$COMMON_DIR")"
PROJECT_DIR="$(dirname "$SCRIPTS_DIR")"

# INV_* variables already in the environment win over config.env (so that
# "INV_PREFIX=... bash scripts/x.sh" and install.sh --prefix reach the scripts
# it starts).
_env_inv="$(compgen -e | grep '^INV_' || true)"
_env_save=""
[ -z "$_env_inv" ] || _env_save="$(declare -px $_env_inv)"
for _cfg in "$PROJECT_DIR/config.env" "${XDG_CONFIG_HOME:-$HOME/.config}/inventor-on-linux/config.env"; do
    # shellcheck disable=SC1090
    [ -f "$_cfg" ] && source "$_cfg"
done
[ -z "$_env_save" ] || eval "$_env_save"
unset _cfg _env_inv _env_save

# Inventor release: given (environment, config.env), else the one installed in
# INV_PREFIX (newest if several), else 2026. INV_YEAR_GIVEN=1 when it was given.
INV_YEAR_GIVEN=0; [ -z "${INV_YEAR:-}" ] || INV_YEAR_GIVEN=1
inventor_year_in_prefix() {   # PREFIX -> 2027 / "" (newest Inventor in it)
    local d y=""
    for d in "$1/drive_c/Program Files/Autodesk/Inventor 20"[0-9][0-9]; do
        [ -f "$d/Bin/Inventor.exe" ] && y="${d##* }"
    done
    echo "$y"
}
if [ -z "${INV_YEAR:-}" ] && [ -n "${INV_PREFIX:-}" ]; then
    INV_YEAR="$(inventor_year_in_prefix "$INV_PREFIX")"
fi
INV_YEAR="${INV_YEAR:-2026}"
# Inventor's registry major version: 2026 -> 30, 2025 -> 29, ...
INV_REGMAJOR="${INV_REGMAJOR:-$((INV_YEAR - 1996))}"
WIN_ROOT="${WIN_ROOT:-/mnt/windows}"
INV_PREFIX="${INV_PREFIX:-$HOME/.wine-inventor$INV_YEAR}"
LOGDIR="${INV_LOGDIR:-$PROJECT_DIR/logs}"
REG_FILE="${REG_FILE:-$PROJECT_DIR/registry/autodesk-full.reg}"
DOWNLOAD_DIR="${DOWNLOAD_DIR:-$PROJECT_DIR/downloads}"

# --- distribution ------------------------------------------------------------
# arch | debian (Debian, Ubuntu, Mint, Pop!_OS ...) | fedora | unknown
detect_distro() {
    local id="" like=""
    if [ -f /etc/os-release ]; then
        id="$(. /etc/os-release; echo "${ID:-}")"; like="$(. /etc/os-release; echo "${ID_LIKE:-}")"
    fi
    case " $id $like " in
        *" arch "*) echo arch ;;
        *" debian "*|*" ubuntu "*) echo debian ;;
        *" fedora "*|*" rhel "*) echo fedora ;;
        *) command -v pacman >/dev/null && echo arch || echo unknown ;;
    esac
}
INV_DISTRO="${INV_DISTRO:-$(detect_distro)}"

# --- which Wine --------------------------------------------------------------
# This project's own Wine (vanilla Wine + patches/, built in public by the
# "Build Wine" workflow, downloaded by get-wine.sh) or the system's Wine with
# the fixes copied into it (build-wine-dll.sh, the v0.1 way).
#   INV_WINE=auto     own Wine when it is installed, else the system's (default)
#   INV_WINE=bundled  own Wine only
#   INV_WINE=system   the system's Wine
INV_WINE="${INV_WINE:-auto}"
INV_WINE_HOME="${INV_WINE_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/inventor-on-linux}"
INV_WINE_VER="$(sed -n 's/^WINE_VERSION=//p' "$PROJECT_DIR/wine/version.env" 2>/dev/null)"
INV_WINE_BUILD="$(sed -n 's/^WINE_BUILD=//p' "$PROJECT_DIR/wine/version.env" 2>/dev/null)"
INV_WINE_NAME="wine-inventor-$INV_WINE_VER-$INV_WINE_BUILD-x86_64"
# checksums of the published builds (added after the "Build Wine" workflow ran)
INV_WINE_SHA256="$(awk -v f="$INV_WINE_NAME.tar.xz" '$2 == f || $2 == "*" f {print $1}' "$PROJECT_DIR/wine/SHA256SUMS" 2>/dev/null)"
# Puts this project's Wine first in PATH when it is installed (and wanted).
# Sets INV_WINE_ACTIVE (bundled|system), INV_WINE_DIR, and INV_WINE_OUTDATED=1
# when only an older build than wine/version.env names is installed.
select_wine() {
    INV_WINE_ACTIVE=system INV_WINE_OUTDATED=0 INV_WINE_DIR=""
    [ "$INV_WINE" = system ] && return 0
    local d="$INV_WINE_HOME/$INV_WINE_NAME" newest
    if [ ! -x "$d/bin/wine" ]; then
        newest="$(ls -d "$INV_WINE_HOME"/wine-inventor-*-x86_64 2>/dev/null | sort -V | tail -1 || true)"
        if [ -n "$newest" ] && [ -x "$newest/bin/wine" ]; then d="$newest"; INV_WINE_OUTDATED=1; else return 0; fi
    fi
    INV_WINE_ACTIVE=bundled INV_WINE_DIR="$d"
    case ":$PATH:" in *":$d/bin:"*) ;; *) PATH="$d/bin:$PATH" ;; esac
    export PATH WINE="$d/bin/wine" WINESERVER="$d/bin/wineserver" WINELOADER="$d/bin/wine"
}
select_wine

# Isolation: 1 = prefix sees only C: (its own drive_c) and D: (INV_DATA_DIR).
# No Z: -> /, no Desktop/Documents/... symlinks into $HOME. 0 = Wine defaults.
INV_SANDBOX="${INV_SANDBOX:-1}"
# Your files for Inventor (projects, exports). Mapped as D:. Empty = no D:.
INV_DATA_DIR="${INV_DATA_DIR-$HOME/Inventor}"
# Font folders exposed to Wine, one drive letter each (t: u: v: w: x:).
# Required with isolation: a font outside every drive gets the path
# "\\?\unix\..." and WPF (Inventor's ribbon) crashes on it with
# UriFormatException. Fonts only - nothing else of the system is exposed.
# Wine's own fonts (Tahoma, Marlett, ...) are found through Wine's DATA folder,
# whose Windows path Wine computes once per process - so the drive must point
# at the data folder itself (/usr/share/wine), not at its fonts/ subfolder.
_wine_bin="$(command -v wine 2>/dev/null || true)"
if [ -z "${WINE_DATA_DIR:-}" ] && [ -n "$_wine_bin" ]; then
    WINE_DATA_DIR="$(readlink -f "$(dirname "$(readlink -f "$_wine_bin")")/../share/wine" 2>/dev/null || true)"
fi
[ -d "${WINE_DATA_DIR:-}" ] || WINE_DATA_DIR=/usr/share/wine
unset _wine_bin
if [ -z "${INV_FONT_DIRS+x}" ]; then
    INV_FONT_DIRS=(/usr/share/fonts /usr/local/share/fonts "$HOME/.local/share/fonts" "$HOME/.fonts" "$WINE_DATA_DIR")
fi
INV_FONT_LETTERS=(t u v w x)

# DXVK: pinned release from the official GitHub project, verified by SHA-256.
# Same version and hash as winetricks' "dxvk2071" verb and the original setup.
# INV_DXVK=system uses setup_dxvk from an installed package instead.
INV_DXVK="${INV_DXVK:-pinned}"
DXVK_VER="${DXVK_VER:-2.7.1}"
DXVK_SHA256="${DXVK_SHA256:-d85ce7c79f57ecd765aaa1b9e7007cb875e6fde9f6d331df799bce73d513ce87}"
DXVK_DLLS=(dxgi d3d8 d3d9 d3d10core d3d11)
# vkd3d-proton: Direct3D 12 on Vulkan (works with DXVK's dxgi). Inventor 2027
# tests for Direct3D 12 and warns when Wine's own d3d12 (vkd3d) is not enough.
# Pinned release from github.com/HansKristian-Work/vkd3d-proton, SHA-256 of
# the release file. INV_VKD3D=off keeps Wine's builtin d3d12.
INV_VKD3D="${INV_VKD3D:-pinned}"
VKD3D_VER="${VKD3D_VER:-3.0.1}"
VKD3D_SHA256="${VKD3D_SHA256:-3cf2315522af5e43605ef6d3c41dad91387040bf97199934f3f7ab76caaa2f0c}"
VKD3D_DLLS=(d3d12 d3d12core)
# With several GPUs: part of the Vulkan device name DXVK should use
# (see "deviceName" in check-system.sh), e.g. INV_GPU="RX 6500"
INV_GPU="${INV_GPU:-}"
# This project's Wine fixes (scripts/build-wine-dll.sh targets), in build order
WINE_FIX_PARTS=(wbemprox shell32 oleaut32 kernelbase riched20 msi mspatcha comctl32 comctl32_v6 ntdll rpcrt4 combase server winex11)
# Add-ins rebuild-prefix.sh disables (notes/disabled-addins.md). Some of them
# are loaded through wine-mono instead of CoreCLR and abort Inventor
# (SharedViews confirmed: mono assertion -> Environment.Exit).
INV_DEFAULT_DISABLED_ADDINS=(
    Anark.Core.addin Autodesk.Feedback.Inventor.addin Autodesk.PerfFeedbackAddin.Inventor.addin
    Autodesk.SharedViews.Inventor.addin Autodesk.InteractiveTutorial.Inventor.addin
    Autodesk.Publisher.Inventor.addin
    autodesk.frameanalysis.inventor.addin
    autodesk.translatorfusion.inventor.addin
)
# Run Inventor inside a Wine virtual desktop of this size (e.g. 1920x1080).
# Empty = normal windows managed by Hyprland.
INV_VDESKTOP="${INV_VDESKTOP:-}"
# Chromium switches for WebView2 (Inventor's home page, licensing dialog, ...).
# Written to the HKLM WebView2 policy by webview2_reg (rebuild-prefix.sh, webview2-fix.sh).
INV_WEBVIEW2_ARGS="${INV_WEBVIEW2_ARGS:---no-sandbox --enable-unsafe-swiftshader --use-angle=swiftshader}"
# Inventor.exe's own WebView2 (Home page): software output without the GPU
# process - with it the page lagged one frame behind the mouse (hover highlight
# on the wrong Recent row) even with the winex11 flush fix. The licensing and
# sign-in windows keep INV_WEBVIEW2_ARGS.
INV_WEBVIEW2_ARGS_INVENTOR="${INV_WEBVIEW2_ARGS_INVENTOR:-$INV_WEBVIEW2_ARGS --disable-gpu}"

export WINEPREFIX="$INV_PREFIX"
# win64 by default; the NixOS flake builds wow64 prefixes. Anything else
# (e.g. a WINEARCH=win32 left in the environment by other tools) would make
# a prefix Inventor can't run in, so it is ignored.
case "${WINEARCH:-}" in win64|wow64) ;; *) WINEARCH=win64 ;; esac
export WINEARCH
# No Wine menu entries and file associations: Autodesk's installers create
# Start-menu shortcuts and register .ipt/.iam/.dwg/... - Wine's winemenubuilder
# would copy them to ~/.local/share/applications as entries that start the
# programs without this project's launcher. The launcher entry comes from
# install-desktop-integration.sh instead.
case ";${WINEDLLOVERRIDES:-};" in
    *";winemenubuilder.exe="*) ;;
    *) export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:+$WINEDLLOVERRIDES;}winemenubuilder.exe=d" ;;
esac

# Windows-side source paths
WIN_INV="$WIN_ROOT/Program Files/Autodesk/Inventor $INV_YEAR"
WIN_ASC_BASE="$WIN_ROOT/Program Files/Common Files/Autodesk Shared/Components/$INV_YEAR"
WIN_LIC_BASE="$WIN_ROOT/Program Files (x86)/Common Files/Autodesk Shared/AdskLicensing"
WIN_IDMGR_BASE="$WIN_ROOT/Program Files/Autodesk/AdskIdentityManager"
WIN_PUBDOCS="$WIN_ROOT/Users/Public/Documents/Autodesk/Inventor $INV_YEAR"
WIN_PROGDATA="$WIN_ROOT/ProgramData/Autodesk"

# Prefix-side paths
P_C="$WINEPREFIX/drive_c"
P_INV="$P_C/Program Files/Autodesk/Inventor $INV_YEAR"
P_ASC_BASE="$P_C/Program Files/Common Files/Autodesk Shared/Components/$INV_YEAR"
P_LIC_BASE="$P_C/Program Files (x86)/Common Files/Autodesk Shared/AdskLicensing"
P_IDMGR_BASE="$P_C/Program Files/Autodesk/AdskIdentityManager"
P_USER="$P_C/users/$USER"
P_PUBDOCS="$P_C/users/Public/Documents/Autodesk/Inventor $INV_YEAR"
P_ADDINS="$P_INV/Bin/Addins"
# Disabled add-ins live OUTSIDE Bin\Addins: Inventor 2026 also scans its
# subfolders, so the old Bin\Addins\disabled\ did not disable anything.
P_ADDINS_OFF="$P_INV/Addins.disabled"

# --- output helpers ----------------------------------------------------------
if [ -t 1 ]; then
    _B=$'\e[1m'; _G=$'\e[32m'; _Y=$'\e[33m'; _R=$'\e[31m'; _N=$'\e[0m'
else
    _B=''; _G=''; _Y=''; _R=''; _N=''
fi
_STEP=0
_STEPS="${_STEPS:-0}"

step() { _STEP=$((_STEP + 1)); printf '%s[%d/%d]%s %s\n' "$_B" "$_STEP" "$_STEPS" "$_N" "$*"; }
info() { printf '    %s\n' "$*"; }
ok()   { printf '    %sOK%s %s\n' "$_G" "$_N" "$*"; }
warn() { printf '    %sWARN%s %s\n' "$_Y" "$_N" "$*" >&2; }
err()  { printf '    %sERROR%s %s\n' "$_R" "$_N" "$*" >&2; }
die()  { err "$*"; exit 1; }

# sudo through a graphical password prompt when SUDO_ASKPASS is set (the
# graphical installer, scripts/install-gui.sh); otherwise the terminal asks.
sudo() { if [ -n "${SUDO_ASKPASS:-}" ]; then command sudo -A "$@"; else command sudo "$@"; fi; }

# Run a command; on failure only warn (for optional steps under set -e).
try() { "$@" || warn "failed (continuing): $*"; }

# Quiet wine wrappers. Wine's own chatter goes to the log, not the terminal.
wine_q() { wine "$@" >>"$LOGDIR/setup-wine.log" 2>&1; }
wine_reg_add() { wine_q reg add "$@" /f; }

# Stop this prefix's wineserver. Never fails (no server running is fine).
wine_stop() { wineserver -k >/dev/null 2>&1 || true; wineserver -w >/dev/null 2>&1 || true; }

# --- detection ---------------------------------------------------------------

# Highest dotted-version subdirectory of $1 (e.g. 15.4.2.4), or empty.
latest_version_dir() {
    [ -d "$1" ] || return 0
    find "$1" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null \
        | grep -E '^[0-9]+(\.[0-9]+)+$' | sort -V | tail -1
}

# Windows profile that has Inventor settings. Honors $WIN_USER.
detect_win_user() {
    if [ -n "${WIN_USER:-}" ]; then printf '%s\n' "$WIN_USER"; return; fi
    local d n best="" fallback=""
    for d in "$WIN_ROOT/Users"/*/; do
        n="$(basename "$d")"
        case "$n" in
            Public|Default|"Default User"|"All Users"|defaultuser*|WDAGUtilityAccount) continue ;;
        esac
        [ -f "$d/NTUSER.DAT" ] || continue
        [ -z "$fallback" ] && fallback="$n"
        if [ -d "$d/AppData/Roaming/Autodesk/Inventor $INV_YEAR" ]; then best="$n"; break; fi
    done
    printf '%s\n' "${best:-$fallback}"
}

# Linux username as uppercase hex: the IDSDK IPC directory name.
idsdk_user_hex() { printf '%s' "$USER" | od -An -tx1 | tr -d ' \n' | tr '[:lower:]' '[:upper:]'; }
IDSDK_IPC_ROOT="$P_C/ProgramData/Autodesk/IDSDK/$(idsdk_user_hex)/interprocess"

# Version detection from the Windows source (used while building the prefix)
detect_source_versions() {
    ASC_VER="${ASC_VER:-$(latest_version_dir "$WIN_ASC_BASE")}"
    LIC_VER="${LIC_VER:-$(latest_version_dir "$WIN_LIC_BASE")}"
}

# Version detection from the built prefix (used at launch time; Windows not needed)
detect_prefix_versions() {
    LIC_VER="${LIC_VER:-$(latest_version_dir "$P_LIC_BASE")}"
    ASC_VER="${ASC_VER:-$(latest_version_dir "$P_ASC_BASE")}"
}

# A string value from the exported .reg file.
#   reg_value 'Inventor\RegistryVersion30.0' ClientVersion
# The key is matched literally as the END of the key path. Handles plain
# "..." strings and hivexregedit's default hex(1)/hex(2) UTF-16LE encoding.
reg_value() {
    [ -f "$REG_FILE" ] || return 0
    RV_KEY="\\$1]" RV_NAME="\"$2\"=" awk '
        function hexval(c) { return index("0123456789abcdef", tolower(c)) - 1 }
        function utf16(s,   out, i, n, b) {
            gsub(/[^0-9a-fA-F,]/, "", s); n = split(s, b, ",")
            for (i = 1; i < n; i += 2)
                if (b[i] != "00" || b[i+1] != "00") out = out sprintf("%c", hexval(substr(b[i],1,1))*16 + hexval(substr(b[i],2,1)))
            return out
        }
        { sub(/\r$/, "") }
        /^\[/ { k = ENVIRON["RV_KEY"]; inkey = (length($0) >= length(k) && substr($0, length($0) - length(k) + 1) == k); next }
        !inkey { next }
        cont { v = v $0; if ($0 !~ /\\$/) { print utf16(v); exit } ; next }
        index($0, ENVIRON["RV_NAME"]) == 1 {
            v = substr($0, length(ENVIRON["RV_NAME"]) + 1)
            if (v ~ /^"/) { sub(/^"/, "", v); sub(/"$/, "", v); print v; exit }
            if (v ~ /^hex\([12]\):/) { sub(/^hex\([12]\):/, "", v); if (v ~ /\\$/) { cont = 1; next } ; print utf16(v); exit }
        }
    ' "$REG_FILE"
}

# Identity Manager versions referenced in the registry export (one per line)
reg_idmgr_versions() {
    [ -f "$REG_FILE" ] || return 0
    grep -aoE 'AdskIdentityManager\\[0-9]+(\.[0-9]+)+\]' "$REG_FILE" \
        | grep -oE '[0-9]+(\.[0-9]+)+' | sort -uV
}

# FileVersion from a PE file's version resource, e.g. 30.40.43500.0000
inv_file_version() {
    [ -f "$1" ] || return 0
    strings -el "$1" 2>/dev/null | grep -A1 -m1 -x FileVersion | tail -1 | grep -E '^[0-9]+(\.[0-9]+)+$' || true
}

wine_version() { wine --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1; }

# Directory holding the system's 64-bit PE builtin DLLs (where wbemprox.dll lives)
wine_pe_dir() {
    local d bin
    bin="$(command -v wine 2>/dev/null || true)"
    for d in \
        "${bin:+$(dirname "$(readlink -f "$bin")")/../lib/wine/x86_64-windows}" \
        /usr/lib/wine/x86_64-windows /usr/lib64/wine/x86_64-windows \
        /usr/local/lib/wine/x86_64-windows; do
        [ -n "$d" ] && [ -f "$d/wbemprox.dll" ] && { readlink -f "$d"; return; }
    done
}

# System file that a WINE_FIX_PARTS part replaces (build-wine-dll.sh installs it)
wine_fix_file() {
    local pe; pe="$(wine_pe_dir)"; [ -n "$pe" ] || return 1
    case "$1" in
        server)  readlink -f "$(command -v wineserver)" ;;
        winex11) echo "$(dirname "$pe")/x86_64-unix/winex11.so" ;;
        *)       echo "$pe/$1.dll" ;;
    esac
}

# Parts of this project's Wine fixes that are NOT active in the installed Wine:
# no backup for this Wine version (Wine was updated), or the system file is the
# original again (Wine was reinstalled). Prints the part names, one per line.
wine_fixes_missing() {
    # this project's own Wine has them built in
    [ "$INV_WINE_ACTIVE" = bundled ] && return 0
    local wv p f; wv="$(wine_version)"; [ -n "$wv" ] || return 0
    for p in "${WINE_FIX_PARTS[@]}"; do
        f="$(wine_fix_file "$p")" || { echo "$p"; continue; }
        if [ ! -f "$f.orig-$wv" ] || cmp -s "$f" "$f.orig-$wv"; then echo "$p"; fi
    done
}

# Move add-ins from the old Bin\Addins\disabled\ (still scanned by Inventor)
# to P_ADDINS_OFF. Safe to call any time.
migrate_disabled_addins() {
    local old="$P_ADDINS/disabled" f
    [ -d "$old" ] || return 0
    mkdir -p "$P_ADDINS_OFF/libs"
    for f in "$old"/*.addin "$old"/*.Addin "$old"/*.ADDIN; do
        [ -f "$f" ] && mv -f "$f" "$P_ADDINS_OFF/"
    done
    if [ -d "$old/libs" ]; then
        for f in "$old/libs"/*; do [ -f "$f" ] && mv -f "$f" "$P_ADDINS_OFF/libs/"; done
        rmdir "$old/libs" 2>/dev/null || true
    fi
    rmdir "$old" 2>/dev/null || warn "could not remove $old (not empty?)"
    info "moved disabled add-ins out of Bin\\Addins (Inventor scans its subfolders)"
}

# --- DXVK --------------------------------------------------------------------

# Download (once, cached in DOWNLOAD_DIR), verify, and copy DXVK into the prefix.
install_dxvk() {
    if [ "$INV_DXVK" = system ]; then
        command -v setup_dxvk >/dev/null || die "INV_DXVK=system but setup_dxvk is not installed"
        setup_dxvk install >>"$LOGDIR/setup-wine.log" 2>&1
    else
        local tgz="$DOWNLOAD_DIR/dxvk-$DXVK_VER.tar.gz" tmp d
        local url="https://github.com/doitsujin/dxvk/releases/download/v$DXVK_VER/dxvk-$DXVK_VER.tar.gz"
        mkdir -p "$DOWNLOAD_DIR"
        if [ ! -f "$tgz" ]; then
            info "downloading $url"
            curl -fL --retry 3 -o "$tgz.part" "$url" || die "DXVK download failed"
            mv "$tgz.part" "$tgz"
        fi
        if ! echo "$DXVK_SHA256  $tgz" | sha256sum -c --quiet - >/dev/null 2>&1; then
            rm -f "$tgz"
            die "DXVK $DXVK_VER checksum mismatch - file deleted. (Changed DXVK_VER? Set DXVK_SHA256 too.)"
        fi
        ok "DXVK $DXVK_VER sha256 verified"
        tmp="$(mktemp -d)"
        tar -xzf "$tgz" -C "$tmp"
        for d in "${DXVK_DLLS[@]}"; do
            cp "$tmp/dxvk-$DXVK_VER/x64/$d.dll" "$P_C/windows/system32/"
            if [ -d "$P_C/windows/syswow64" ]; then cp "$tmp/dxvk-$DXVK_VER/x32/$d.dll" "$P_C/windows/syswow64/"; fi
        done
        rm -rf "$tmp"
    fi
    # native = load DXVK's DLLs instead of Wine's wined3d; d3dcompiler_47 as in the original setup
    for d in "${DXVK_DLLS[@]}" d3dcompiler_47; do
        wine_reg_add 'HKCU\Software\Wine\DllOverrides' /v "$d" /t REG_SZ /d native
    done
}

# Same for vkd3d-proton (Direct3D 12). INV_VKD3D=off: Wine's builtin d3d12 again.
install_vkd3d() {
    local d
    if [ "$INV_VKD3D" = off ]; then
        for d in "${VKD3D_DLLS[@]}"; do
            # builtin explicitly: vkd3d-proton's DLLs may still be in system32
            wine_reg_add 'HKCU\Software\Wine\DllOverrides' /v "$d" /t REG_SZ /d builtin
        done
        info "vkd3d-proton off (INV_VKD3D=off) - Wine's own d3d12"
        return 0
    fi
    local tzst="$DOWNLOAD_DIR/vkd3d-proton-$VKD3D_VER.tar.zst" tmp
    local url="https://github.com/HansKristian-Work/vkd3d-proton/releases/download/v$VKD3D_VER/vkd3d-proton-$VKD3D_VER.tar.zst"
    mkdir -p "$DOWNLOAD_DIR"
    if [ ! -f "$tzst" ]; then
        info "downloading $url"
        curl -fL --retry 3 -o "$tzst.part" "$url" || die "vkd3d-proton download failed"
        mv "$tzst.part" "$tzst"
    fi
    if ! echo "$VKD3D_SHA256  $tzst" | sha256sum -c --quiet - >/dev/null 2>&1; then
        rm -f "$tzst"
        die "vkd3d-proton $VKD3D_VER checksum mismatch - file deleted. (Changed VKD3D_VER? Set VKD3D_SHA256 too.)"
    fi
    ok "vkd3d-proton $VKD3D_VER sha256 verified"
    tmp="$(mktemp -d)"
    tar --zstd -xf "$tzst" -C "$tmp" || { rm -rf "$tmp"; die "unpacking vkd3d-proton failed (zstd missing?)"; }
    for d in "${VKD3D_DLLS[@]}"; do
        cp "$tmp/vkd3d-proton-$VKD3D_VER/x64/$d.dll" "$P_C/windows/system32/"
        if [ -d "$P_C/windows/syswow64" ]; then cp "$tmp/vkd3d-proton-$VKD3D_VER/x86/$d.dll" "$P_C/windows/syswow64/"; fi
    done
    rm -rf "$tmp"
    for d in "${VKD3D_DLLS[@]}"; do
        wine_reg_add 'HKCU\Software\Wine\DllOverrides' /v "$d" /t REG_SZ /d native
    done
}

# --- isolation ---------------------------------------------------------------
# Limits what the Windows programs SEE: drive letters and the user's shell
# folders. This is not a security boundary - Wine programs run as your user and
# can still reach Unix paths directly (e.g. \\?\unix\...). It stops file
# dialogs, drive scans and default save locations from touching the rest of
# the system. For a real boundary see docs/arch-hyprland.md (bubblewrap).

# Filesystem part: safe to run on every launch (no Wine needed).
sandbox_fs() {
    [ "$INV_SANDBOX" = 1 ] || return 0
    local dd="$WINEPREFIX/dosdevices" l n
    [ -d "$dd" ] || return 0
    for l in "$dd"/*; do
        n="$(basename "$l")"
        case "$n" in
            c:) ;;                                   # the prefix's own drive_c
            [a-z]:|[a-z]::) rm -f -- "$l" ;;          # z: -> /, raw devices, auto-mounted media
        esac
    done
    if [ -n "$INV_DATA_DIR" ]; then
        mkdir -p "$INV_DATA_DIR"
        ln -sfn "$INV_DATA_DIR" "$dd/d:"
    fi
    local i=0 f
    for f in "${INV_FONT_DIRS[@]}"; do
        [ -d "$f" ] || continue
        [ "$i" -lt "${#INV_FONT_LETTERS[@]}" ] || break
        ln -sfn "$f" "$dd/${INV_FONT_LETTERS[$i]}:"
        i=$((i + 1))
    done
    # Desktop, Documents, Downloads, ... are symlinks into $HOME by default:
    # replace every directory symlink that leaves the prefix with a real directory.
    local prefix_real data_real=""; prefix_real="$(readlink -f "$WINEPREFIX")"
    [ -n "$INV_DATA_DIR" ] && data_real="$(readlink -f "$INV_DATA_DIR")"
    while IFS= read -r -d '' l; do
        case "$(readlink -f "$l")" in
            "$prefix_real"/*) ;;
            "${data_real:-/nonexistent}") ;;                  # Documents -> your Inventor folder (below)
            *) if [ -d "$l" ]; then rm -f -- "$l"; mkdir -p -- "$l"; fi ;;
        esac
    done < <(find "$P_C/users" -maxdepth 4 -type l -print0 2>/dev/null)
    # Documents = your Inventor folder (D:): Inventor's Save/Open dialogs start
    # there, so files don't end up hidden in the prefix. What is already in the
    # prefix's Documents is moved over (nothing is overwritten).
    local docs="$P_USER/Documents" e
    if [ -n "$data_real" ] && [ -d "$P_USER" ] && [ "$(readlink -f "$docs")" != "$data_real" ]; then
        if [ -d "$docs" ] && [ ! -L "$docs" ]; then
            for e in "$docs"/* "$docs"/.[!.]*; do
                [ -e "$e" ] || continue
                [ -e "$data_real/$(basename "$e")" ] || mv -- "$e" "$data_real/"
            done
            rmdir -- "$docs" 2>/dev/null || mv -- "$docs" "$docs.old-$(date +%s)"
        fi
        rm -f -- "$docs"
        ln -s "$data_real" "$docs"
    fi
    # Don't let wineboot re-create the links/drives automatically after a Wine
    # update; launch-inventor.sh runs the update itself and re-applies this.
    echo disable > "$WINEPREFIX/.update-timestamp"
}

# Font paths Wine stored while a font folder had no drive letter look like
# "\\??\\unix\\usr\\share\\fonts\\..." (in system.reg). Deleting Wine's
# "External Fonts" list makes it re-register every font with the current
# drive letters on the next start. Run only with no wineserver running.
fix_font_registry() {
    [ -f "$WINEPREFIX/system.reg" ] || return 0
    local n
    n=$(grep -cF '??\\unix\\' "$WINEPREFIX/system.reg" || true)
    [ "${n:-0}" -gt 0 ] || return 0
    info "    $n font path(s) without a drive letter in the registry - re-registering fonts"
    wine_stop
    wine_q reg delete 'HKCU\Software\Wine\Fonts\External Fonts' /f || true
    wine_stop
}

# Registry part: hides the "/" (unixfs) entry in file dialogs. Needs Wine.
sandbox_reg() {
    [ "$INV_SANDBOX" = 1 ] || return 0
    wine_q reg delete 'HKLM\Software\Microsoft\Windows\CurrentVersion\Explorer\Desktop\Namespace\{9D20AAE8-0625-44B0-9CA7-71889C2254D9}' /f || true
}

# WebView2 (App Home page, licensing dialog, notifications) under Wine.
# Runtime 15x's GPU process dies on a CHECK three times and the browser exits
# ("GPU process isn't usable. Goodbye.") -> white windows. What made it render:
#   - msedgewebview2.exe reported as Windows 7 (Wine AppDefaults), so Chromium
#     avoids the Windows 10 presentation paths Wine lacks;
#   - wined3d instead of DXVK (and Wine's d3d12, not vkd3d-proton) for msedgewebview2.exe only (wined3d accepts a
#     D3D_DRIVER_TYPE_WARP device, DXVK rejects it);
#   - switches via the HKLM WebView2 policy - the WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS
#     environment variable does not reach the browsers started by
#     AdskLicensingAgent / Inventor.
webview2_reg() {
    local k='HKCU\Software\Wine\AppDefaults\msedgewebview2.exe' d app
    wine_reg_add "$k" /v Version /t REG_SZ /d win7
    for d in d3d11 dxgi d3d10core d3d9 d3d12 d3d12core; do wine_reg_add "$k\\DllOverrides" /v "$d" /t REG_SZ /d builtin; done
    k='HKLM\Software\Policies\Microsoft\Edge\WebView2\AdditionalBrowserArguments'
    for app in '*' AdskLicensingAgent.exe AdskIdentityManager.exe; do
        wine_reg_add "$k" /v "$app" /t REG_SZ /d "$INV_WEBVIEW2_ARGS"
    done
    wine_reg_add "$k" /v Inventor.exe /t REG_SZ /d "$INV_WEBVIEW2_ARGS_INVENTOR"
}

# Copy a Linux file into C:\windows\temp and print its Windows path, so Wine
# can open it without a Z: drive.
to_wine_temp() {
    local dst
    dst="$P_C/windows/temp/$(basename "$1")"
    mkdir -p "$P_C/windows/temp"
    cp -f "$1" "$dst"
    printf 'C:\\windows\\temp\\%s\n' "$(basename "$1")"
}

# Import a .reg file into the prefix.
# Wine's regedit treats a file WITHOUT a UTF-16 byte-order mark as ANSI and
# widens every byte of hex(1)/hex(2)/hex(7) data to its own character. The
# hivexregedit export stores strings as UTF-16LE bytes, so "False" (46,00,61,00,...)
# would become "F\0a\0l\0s\0e\0" - which is how InfoCenter crashed Inventor
# (FormatException: 'False' is not a valid Boolean). Converting the whole file
# to UTF-16LE with a BOM makes regedit take the bytes as they are.
import_reg_file() {
    local src="$1" name tmp
    name="$(basename "$src" .reg)-utf16.reg"
    tmp="$P_C/windows/temp/$name"
    mkdir -p "$P_C/windows/temp"
    { printf '\xff\xfe'; iconv -f UTF-8 -t UTF-16LE "$src"; } > "$tmp" || die "iconv failed for $src"
    wine_q regedit /S "C:\\windows\\temp\\$name"
    rm -f "$tmp"
}

mkdir -p "$LOGDIR"
