#!/bin/bash
# Build and install all of this project's Wine fixes for the installed Wine.
# Run it after Arch updated Wine (the pacman hook reminds you). Parts that are
# already installed for this Wine version are only checked.
#
#   bash scripts/rebuild-wine-fixes.sh

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

[ "$EUID" -ne 0 ] || die "run this as your normal user - it asks for the password itself"
if [ "$INV_WINE_ACTIVE" = bundled ]; then
    ok "Inventor uses this project's own Wine ($INV_WINE_DIR) - the fixes are built in, nothing to do"
    info "(to build them into the system's Wine anyway: INV_WINE=system bash $0)"
    exit 0
fi
if pgrep -x wineserver >/dev/null; then
    die "Wine is running - close Inventor first (or: wineserver -k)"
fi
info "Wine $(wine_version): building ${#WINE_FIX_PARTS[@]} parts (the first time for a new Wine version 10-30 minutes)"
for p in "${WINE_FIX_PARTS[@]}"; do
    info "-- $p"
    bash "$SCRIPTS_DIR/build-wine-dll.sh" "$p" --install --hook
done
ok "all Wine fixes installed for Wine $(wine_version)"
