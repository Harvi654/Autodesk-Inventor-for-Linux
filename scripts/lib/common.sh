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

for _cfg in "$PROJECT_DIR/config.env" "${XDG_CONFIG_HOME:-$HOME/.config}/inventor-on-linux/config.env"; do
    # shellcheck disable=SC1090
    [ -f "$_cfg" ] && source "$_cfg"
done
unset _cfg

INV_YEAR="${INV_YEAR:-2026}"
# Inventor's registry major version: 2026 -> 30, 2025 -> 29, ...
INV_REGMAJOR="${INV_REGMAJOR:-$((INV_YEAR - 1996))}"
WIN_ROOT="${WIN_ROOT:-/mnt/windows}"
INV_PREFIX="${INV_PREFIX:-$HOME/.wine-inventor$INV_YEAR}"
LOGDIR="${INV_LOGDIR:-$PROJECT_DIR/logs}"
REG_FILE="${REG_FILE:-$PROJECT_DIR/registry/autodesk-full.reg}"
DOWNLOAD_DIR="${DOWNLOAD_DIR:-$PROJECT_DIR/downloads}"

# Isolation: 1 = prefix sees only C: (its own drive_c) and D: (INV_DATA_DIR).
# No Z: -> /, no Desktop/Documents/... symlinks into $HOME. 0 = Wine defaults.
INV_SANDBOX="${INV_SANDBOX:-1}"
# Your files for Inventor (projects, exports). Mapped as D:. Empty = no D:.
INV_DATA_DIR="${INV_DATA_DIR-$HOME/Inventor}"
# Font folders exposed to Wine, one drive letter each (t: u: v: w: x:).
# Required with isolation: a font outside every drive gets the path
# "\\?\unix\..." and WPF (Inventor's ribbon) crashes on it with
# UriFormatException. Fonts only - nothing else of the system is exposed.
if [ -z "${INV_FONT_DIRS+x}" ]; then
    INV_FONT_DIRS=(/usr/share/fonts /usr/local/share/fonts "$HOME/.local/share/fonts" "$HOME/.fonts" /usr/share/wine/fonts)
fi
INV_FONT_LETTERS=(t u v w x)

# DXVK: pinned release from the official GitHub project, verified by SHA-256.
# Same version and hash as winetricks' "dxvk2071" verb and the original setup.
# INV_DXVK=system uses setup_dxvk from an installed package instead.
INV_DXVK="${INV_DXVK:-pinned}"
DXVK_VER="${DXVK_VER:-2.7.1}"
DXVK_SHA256="${DXVK_SHA256:-d85ce7c79f57ecd765aaa1b9e7007cb875e6fde9f6d331df799bce73d513ce87}"
DXVK_DLLS=(dxgi d3d8 d3d9 d3d10core d3d11)
# With several GPUs: part of the Vulkan device name DXVK should use
# (see "deviceName" in check-system.sh), e.g. INV_GPU="RX 6500"
INV_GPU="${INV_GPU:-}"

export WINEPREFIX="$INV_PREFIX"
export WINEARCH=win64

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
    local prefix_real; prefix_real="$(readlink -f "$WINEPREFIX")"
    while IFS= read -r -d '' l; do
        case "$(readlink -f "$l")" in
            "$prefix_real"/*) ;;
            *) if [ -d "$l" ]; then rm -f -- "$l"; mkdir -p -- "$l"; fi ;;
        esac
    done < <(find "$P_C/users" -maxdepth 4 -type l -print0 2>/dev/null)
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

# Copy a Linux file into C:\windows\temp and print its Windows path, so Wine
# can open it without a Z: drive.
to_wine_temp() {
    local dst
    dst="$P_C/windows/temp/$(basename "$1")"
    mkdir -p "$P_C/windows/temp"
    cp -f "$1" "$dst"
    printf 'C:\\windows\\temp\\%s\n' "$(basename "$1")"
}

mkdir -p "$LOGDIR"
