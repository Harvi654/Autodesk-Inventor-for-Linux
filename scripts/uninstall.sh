#!/bin/bash
# Remove Inventor and this project's changes to the system.
#
# Usage: bash scripts/uninstall.sh [--keep-prefix]
#        bash scripts/uninstall.sh --yes PART...     (no questions; the graphical installer)
#
# Without PART: the app-launcher entries and sign-in handler, the pacman hook,
# this project's Wine (~/.local/share/inventor-on-linux), Wine fixes copied
# into the system's Wine (by reinstalling the wine package, which puts Arch's
# files back) and - after asking - the Wine prefix with Inventor in it.
#
# PART selects what to remove instead:
#   --desktop   app-launcher entry, file types, sign-in handler
#   --wine      this project's Wine builds (+ Arch: the system Wine's originals back)
#   --prefix    the Wine prefix with Inventor (INV_PREFIX)
#   --cache     the unpacked downloads and build cache (~/.cache/inventor-on-linux)
#   --data      YOUR Inventor files (INV_DATA_DIR, ~/Inventor) - only with --yes
#   --project   this folder (the scripts) and its Setup menu entry - done last
# Autodesk's downloads in your Downloads folder are never touched.

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

KEEP_PREFIX=0 YES=0
declare -A DO=()
for a in "$@"; do
    case "$a" in
        --keep-prefix) KEEP_PREFIX=1 ;;
        --yes) YES=1 ;;
        --desktop|--wine|--prefix|--cache|--data|--project) DO[${a#--}]=1 ;;
        -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "unknown option: $a (see --help)" ;;
    esac
done
if [ ${#DO[@]} -eq 0 ]; then                       # the classic way
    DO=([desktop]=1 [wine]=1)
    [ "$KEEP_PREFIX" -eq 1 ] || DO[prefix]=ask
fi
[ -z "${DO[data]:-}" ] || [ "$YES" -eq 1 ] || die "--data deletes your own Inventor files - it needs --yes as well"

pgrep -x wineserver >/dev/null && die "close Inventor and all Wine programs first (or: wineserver -k)"

# never remove something that is not ours (an empty variable, /, $HOME itself)
safe_dir() { local d; d="$(realpath -m "$1")"; [ -n "$1" ] && [ "$d" != / ] && [ "$d" != "$(realpath -m "$HOME")" ]; }

if [ -n "${DO[desktop]:-}" ]; then
    info "app-launcher entries, file types and the adskidmgr:// handler"
    bash "$SCRIPTS_DIR/install-desktop-integration.sh" --uninstall
fi

if [ -n "${DO[wine]:-}" ]; then
    if [ -f /etc/pacman.d/hooks/inventor-wine.hook ]; then
        info "pacman hook"
        sudo rm -f /etc/pacman.d/hooks/inventor-wine.hook
        ok "removed"
    fi
    info "this project's Wine ($INV_WINE_HOME)"
    rm -rf "$INV_WINE_HOME"/wine-inventor-*-x86_64
    rmdir "$INV_WINE_HOME" 2>/dev/null || true
    ok "removed"
    if [ "$INV_DISTRO" = arch ] && find /usr/lib/wine /usr/bin -maxdepth 3 -name '*.orig-*' 2>/dev/null | grep -q .; then
        info "Wine fixes in the system's Wine: reinstalling the wine package (puts the original files back)"
        pkg="$(pacman -Qqo /usr/bin/wine 2>/dev/null || echo wine)"
        sudo pacman -S --noconfirm "$pkg"
        sudo find /usr/lib/wine /usr/bin -maxdepth 3 -name '*.orig-*' -delete 2>/dev/null || true
        ok "Wine is back to Arch's $pkg"
    fi
fi

if [ -n "${DO[prefix]:-}" ] && [ -d "$INV_PREFIX" ]; then
    safe_dir "$INV_PREFIX" || die "refusing to delete $INV_PREFIX"
    a=y
    if [ "${DO[prefix]}" = ask ] && [ "$YES" -eq 0 ]; then
        du -sh "$INV_PREFIX" 2>/dev/null || true
        read -r -p "Delete the Wine prefix $INV_PREFIX (Inventor and its settings)? [y/N] " a
    fi
    if [ "${a,,}" = y ]; then
        info "Wine prefix $INV_PREFIX ($(du -sh "$INV_PREFIX" 2>/dev/null | cut -f1))"
        rm -rf "$INV_PREFIX"; ok "prefix deleted"
    else
        info "prefix kept"
    fi
fi

CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/inventor-on-linux"
if [ -n "${DO[cache]:-}" ] && [ -d "$CACHE" ]; then
    info "unpacked downloads and build cache $CACHE ($(du -sh "$CACHE" 2>/dev/null | cut -f1))"
    rm -rf "$CACHE"; ok "removed"
fi

if [ -n "${DO[data]:-}" ] && [ -d "$INV_DATA_DIR" ]; then
    safe_dir "$INV_DATA_DIR" || die "refusing to delete $INV_DATA_DIR"
    info "your Inventor files $INV_DATA_DIR ($(du -sh "$INV_DATA_DIR" 2>/dev/null | cut -f1))"
    rm -rf "$INV_DATA_DIR"; ok "removed"
fi

if [ -n "${DO[project]:-}" ]; then
    safe_dir "$PROJECT_DIR" || die "refusing to delete $PROJECT_DIR"
    info "this project $PROJECT_DIR"
    # the "Inventor on Linux - Setup" menu entry goes with it
    rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/io.github.harvi654.InventorInstaller.desktop" \
          "${XDG_DATA_HOME:-$HOME/.local/share}"/icons/hicolor/*/apps/inventor-on-linux.png \
          "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps/inventor-on-linux.svg"
    update-desktop-database "${XDG_DATA_HOME:-$HOME/.local/share}/applications" 2>/dev/null || true
    cd /
    rm -rf "$PROJECT_DIR"; ok "removed"
    exit 0
fi

echo
info "Kept - delete them yourself if you don't need them:"
[ -n "${DO[data]:-}" ]  || info "  your Inventor files:  $INV_DATA_DIR"
[ -n "${DO[cache]:-}" ] || info "  unpacked downloads:   $CACHE"
info "  this project:         $PROJECT_DIR"
