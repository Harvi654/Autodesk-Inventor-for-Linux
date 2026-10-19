#!/bin/bash
# Remove Inventor and this project's changes to the system.
#
# Usage: bash scripts/uninstall.sh [--keep-prefix]
#
# Removes: the app-launcher entry and sign-in handler, the pacman hook, this
# project's Wine (~/.local/share/inventor-on-linux), Wine fixes copied into the
# system's Wine (by reinstalling the wine package, which puts Arch's files back)
# and - after asking - the Wine prefix with Inventor in it.
# Kept: your Inventor files (INV_DATA_DIR, by default ~/Inventor), this
# folder, the downloads and the build cache (~/.cache/inventor-on-linux) -
# the script prints how to delete them.

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

KEEP_PREFIX=0
[ "${1:-}" = "--keep-prefix" ] && KEEP_PREFIX=1

pgrep -x wineserver >/dev/null && die "close Inventor and all Wine programs first (or: wineserver -k)"

info "app-launcher entry and adskidmgr:// handler"
bash "$SCRIPTS_DIR/install-desktop-integration.sh" --uninstall

info "pacman hook"
sudo rm -f /etc/pacman.d/hooks/inventor-wine.hook
ok "removed"

info "this project's Wine ($INV_WINE_HOME)"
rm -rf "$INV_WINE_HOME"/wine-inventor-*-x86_64
ok "removed"

if find /usr/lib/wine /usr/bin -maxdepth 3 -name '*.orig-*' 2>/dev/null | grep -q .; then
    info "Wine fixes in the system's Wine: reinstalling the wine package (puts the original files back)"
    pkg="$(pacman -Qqo /usr/bin/wine 2>/dev/null || echo wine)"
    sudo pacman -S --noconfirm "$pkg"
    sudo find /usr/lib/wine /usr/bin -maxdepth 3 -name '*.orig-*' -delete 2>/dev/null || true
    ok "Wine is back to Arch's $pkg"
fi

if [ "$KEEP_PREFIX" -eq 0 ] && [ -d "$INV_PREFIX" ]; then
    du -sh "$INV_PREFIX" 2>/dev/null || true
    read -r -p "Delete the Wine prefix $INV_PREFIX (Inventor and its settings)? [y/N] " a
    if [ "${a,,}" = y ]; then rm -rf "$INV_PREFIX"; ok "prefix deleted"; else info "prefix kept"; fi
fi

echo
info "Kept - delete them yourself if you don't need them:"
info "  your Inventor files:  ${INV_DATA_DIR:-$HOME/Inventor}"
info "  build cache:          ${XDG_CACHE_HOME:-$HOME/.cache}/inventor-on-linux"
info "  this project:         $PROJECT_DIR"
