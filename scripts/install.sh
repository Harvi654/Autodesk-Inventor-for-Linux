#!/bin/bash
# Install Autodesk Inventor on Linux in one go, from Autodesk's own downloads.
#
#   bash scripts/install.sh DOWNLOAD [UPDATE ...]
#
#   DOWNLOAD  what Autodesk's "Browser download" gave you: the .exe file(s)
#             (all parts, e.g. ..._db_001_002.exe ..._db_002_002.exe), or the
#             folder they are in, or an already unpacked install image
#   UPDATE    optional update downloads (e.g. Inventor_2026.4_Update.exe)
#
# Steps (each can be rerun - finished work is skipped):
#   1. system packages (official Arch repos only)          phase0-setup.sh
#   2. this project's Wine (vanilla Wine + patches/,          get-wine.sh
#      downloaded to ~/.local/share/inventor-on-linux;
#      INV_WINE=system: fixes built into the system's Wine    build-wine-dll.sh)
#   3. unpack the downloads
#   4. install Inventor + Content Center libraries          install-from-image.py
#   5. install the updates
#   6. Wine settings, DXVK, WebView2, fonts, isolation      finish-install.sh
#   7. app-launcher entry and the browser-login handler     install-desktop-integration.sh
#
# Options:
#   --prefix DIR       Wine prefix (default ~/.wine-inventor2026)
#   --no-content       leave out the Content Center libraries (~12.7 GB)
#   --skip-packages    don't run pacman (packages already there)
#   --skip-wine        don't install/check Wine
#   --no-desktop       no app-launcher entry (e.g. for a test prefix)
#
# A log of everything is written to logs/install-<date>.log.

set -Eeuo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

PREFIX="$INV_PREFIX"
NO_CONTENT=() SKIP_PKG=0 SKIP_WINE=0 NO_DESKTOP=0 ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --prefix) PREFIX="$2"; shift ;;
        --no-content) NO_CONTENT=(--no-content) ;;
        --skip-packages) SKIP_PKG=1 ;;
        --skip-wine) SKIP_WINE=1 ;;
        --no-desktop) NO_DESKTOP=1 ;;
        -h|--help) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*) die "unknown option: $1 (see --help)" ;;
        *) ARGS+=("$1") ;;
    esac
    shift
done
PREFIX="$(realpath -m "$PREFIX")"
export INV_PREFIX="$PREFIX" WINEPREFIX="$PREFIX"

mkdir -p "$LOGDIR"
LOG="$LOGDIR/install-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1
trap 'err "installation stopped at line $LINENO: $BASH_COMMAND"; err "log: $LOG - fix the problem and run the same command again, finished steps are skipped"' ERR

_STEPS=8
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/inventor-on-linux/media"

kind_of() {   # product | update | ""
    python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import odis; print(odis.image_kind(sys.argv[2]) or "")' \
        "$COMMON_DIR" "$1" 2>/dev/null || true
}

# A folder that is (or contains, a few levels down) an install image or update
find_image() {
    local d="$1" m
    [ -n "$(kind_of "$d")" ] && { echo "$d"; return; }
    while IFS= read -r m; do
        m="$(dirname "$(dirname "$m")")"            # .../IMAGE/manifest/app.inventor.xml
        [ -n "$(kind_of "$m")" ] && { echo "$m"; return; }
    done < <(find "$d" -maxdepth 4 -path '*/manifest/app.inventor.xml' 2>/dev/null)
    while IFS= read -r m; do
        m="$(dirname "$m")"
        [ -n "$(kind_of "$m")" ] && { echo "$m"; return; }
    done < <(find "$d" -maxdepth 3 \( -name setup.xml -o -name bundleManifest.xml \) 2>/dev/null)
    return 0
}

# Unpack Autodesk .exe/.7z downloads (7-Zip self-extractors) into one folder
unpack() {
    local name dest f
    name="$(basename "${1%.*}")"
    name="${name%_[0-9][0-9][0-9]_[0-9][0-9][0-9]}"   # ..._db_001_002 -> ..._db
    dest="$CACHE/$name"
    # Browser download = a small ..._001_002.exe (the self-extractor) plus
    # ..._002_002.7z (the data): unpack the .7z, the .exe adds nothing
    local parts=() f7=()
    for f in "$@"; do case "${f,,}" in *.7z) f7+=("$f") ;; esac; done
    if [ ${#f7[@]} -gt 0 ]; then parts=("${f7[@]}"); else parts=("$@"); fi
    if [ ! -f "$dest/.unpacked" ]; then
        mkdir -p "$dest"
        for f in "${parts[@]}"; do
            info "unpacking $(basename "$f") (several minutes, ~10 GB)" >&2
            if ! 7z x -y -o"$dest" "$f" >/dev/null 2>&1; then
                # not a 7-Zip archive (e.g. Autodesk's web "Install" .exe): not ours
                rm -rf "$dest"; return 0
            fi
        done
        touch "$dest/.unpacked"
    fi
    find_image "$dest"
}

step "Checking..."
[ "$EUID" -ne 0 ] || die "run this as your normal user, not with sudo - it asks for the password itself"
command -v pacman >/dev/null || die "this installer is for Arch Linux and its derivatives (pacman)"
[ ${#ARGS[@]} -gt 0 ] || die "tell me where Autodesk's download is: bash scripts/install.sh ~/Downloads/Inventor_Professional_2026_..._001_002.exe"
for a in "${ARGS[@]}"; do [ -e "$a" ] || die "not found: $a"; done
if [ -d "$PREFIX/drive_c" ] && [ ! -f "$PREFIX/.odis-install-state.json" ]; then
    die "$PREFIX already exists and was not made by this installer - move it away (e.g. mv $PREFIX $PREFIX.old) or use --prefix"
fi
FREE_GB=$(( $(df --output=avail -k "$HOME" | tail -1) / 1024 / 1024 ))
[ "$FREE_GB" -ge 40 ] || warn "only $FREE_GB GB free in $HOME - Inventor with libraries needs ~40 GB (plus ~15 GB for the unpacked download)"
info "prefix:  $PREFIX"
info "log:     $LOG"
sudo -v || die "sudo is needed for pacman (system packages)"
ok "ok"

step "System packages..."
if [ "$SKIP_PKG" -eq 1 ]; then info "skipped (--skip-packages)"
else bash "$SCRIPTS_DIR/phase0-setup.sh"; fi

step "Wine with this project's fixes..."
if [ "$SKIP_WINE" -eq 1 ]; then info "skipped (--skip-wine)"
elif [ "$INV_WINE" = system ]; then
    info "INV_WINE=system: building the fixes into the system's Wine ($(wine --version 2>/dev/null))"
    info "built from Wine's source the first time (10-30 minutes), later only checked"
    wineserver -k 2>/dev/null || true
    for p in "${WINE_FIX_PARTS[@]}"; do
        info "-- $p"
        bash "$SCRIPTS_DIR/build-wine-dll.sh" "$p" --install --hook
    done
else
    bash "$SCRIPTS_DIR/get-wine.sh"
    select_wine
    [ "$INV_WINE_ACTIVE" = bundled ] || die "this project's Wine is not usable - see above"
    ok "$(wine --version) from $INV_WINE_DIR"
fi

step "Looking at the downloads..."
PRODUCT="" UPDATES=() EXES=()
for a in "${ARGS[@]}"; do
    a="$(realpath "$a")"
    if [ -d "$a" ]; then
        img="$(find_image "$a")"
        if [ -n "$img" ]; then
            if [ "$(kind_of "$img")" = product ]; then PRODUCT="$img"; else UPDATES+=("$img"); fi
            continue
        fi
        # a folder with downloads in it
        while IFS= read -r f; do EXES+=("$f"); done < <(find "$a" -maxdepth 1 -type f \( -iname '*.exe' -o -iname '*.7z' \) | sort)
    else
        EXES+=("$a")
    fi
done
# group multi-part downloads (..._001_002, ..._002_002) and unpack each group
declare -A DLGROUPS=()
for f in "${EXES[@]}"; do
    g="$(basename "${f%.*}")"; g="${g%_[0-9][0-9][0-9]_[0-9][0-9][0-9]}"
    DLGROUPS["$g"]+="$f"$'\n'
done
for g in "${!DLGROUPS[@]}"; do
    mapfile -t parts < <(printf '%s' "${DLGROUPS[$g]}" | sed '/^$/d' | sort)
    img="$(unpack "${parts[@]}")"
    if [ -z "$img" ]; then
        warn "skipped (not an Inventor download or update): $(printf '%s ' "${parts[@]##*/}")"
        continue
    fi
    if [ "$(kind_of "$img")" = product ]; then PRODUCT="$img"; else UPDATES+=("$img"); fi
done
if [ -z "$PRODUCT" ] && [ ! -f "$PREFIX/.odis-install-state.json" ]; then
    die "none of the downloads is the Inventor installer itself (only updates?)"
fi
[ -n "$PRODUCT" ] && ok "Inventor: $PRODUCT"
for u in "${UPDATES[@]}"; do ok "update:   $u"; done

step "Installing Inventor (Autodesk's installers, under Wine - 15-40 minutes)..."
if [ -n "$PRODUCT" ]; then
    python3 "$SCRIPTS_DIR/install-from-image.py" "$PRODUCT" --prefix "$PREFIX" "${NO_CONTENT[@]}"
else
    info "already installed"
fi

step "Updates..."
if [ ${#UPDATES[@]} -eq 0 ]; then info "none given"; fi
for u in "${UPDATES[@]}"; do
    python3 "$SCRIPTS_DIR/install-from-image.py" "$u" --prefix "$PREFIX"
done

step "Setting up the prefix (DXVK, WebView2, fonts, isolation)..."
INV_FINISH_MAIN=1 bash "$SCRIPTS_DIR/finish-install.sh"

step "App launcher and browser login..."
if [ "$NO_DESKTOP" -eq 1 ]; then info "skipped (--no-desktop)"
else bash "$SCRIPTS_DIR/install-desktop-integration.sh"; fi

ok "Inventor is installed."
[ "$NO_DESKTOP" -eq 1 ] && info "Start it with:" || info "Start it from your app launcher (\"Autodesk Inventor $INV_YEAR\") or with:"
info "    INV_PREFIX=$PREFIX bash $SCRIPTS_DIR/launch-inventor.sh"
info "The first start asks you to sign in with your Autodesk account in the browser."
