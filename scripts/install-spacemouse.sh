#!/bin/bash
# 3D mouse (3Dconnexion SpaceMouse) in Inventor: builds spacenav/siappdll.c
# with MinGW and puts it into the prefix as C:\windows\system32\siappdll.dll.
#
# Inventor navigates with a 3D mouse through siappdll.dll, 3Dconnexion's
# client library. Ours reads spacenavd, the free Linux driver, instead of
# 3DxWare; launch-inventor.sh relays spacenavd's socket to 127.0.0.1 with
# socat while the prefix runs (Wine has no AF_UNIX). Buttons and the radial
# menu come from ~/.config/inventor-on-linux/spacemouse.ini (a copy of
# spacenav/spacemouse.ini, made on first use; edits apply at the next press).
#
# Packages (official Arch repos): spacenavd socat mingw-w64-gcc;
# then: sudo systemctl enable --now spacenavd
#
# Usage: bash scripts/install-spacemouse.sh [--uninstall]

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

[ -d "$P_C/windows/system32" ] || die "no prefix at $WINEPREFIX"
DLL="$P_C/windows/system32/siappdll.dll"

if [ "${1:-}" = --uninstall ]; then
    rm -f "$DLL" "$WINEPREFIX/.inventor-on-linux/siappdll-source"
    ok "removed $DLL (Inventor runs without a 3D mouse; spacemouse.ini is kept)"
    exit 0
fi

command -v x86_64-w64-mingw32-gcc >/dev/null || die "needs MinGW: sudo pacman -S --needed mingw-w64-gcc"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT
# --kill-at: undecorated stdcall names, as Inventor imports them;
# -static-libgcc: no MinGW runtime DLL needed in the prefix
x86_64-w64-mingw32-gcc -O2 -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers \
    -shared -o "$OUT/siappdll.dll" "$PROJECT_DIR/spacenav/siappdll.c" \
    -lws2_32 -lole32 -loleaut32 -luuid -lgdi32 -luser32 -Wl,--kill-at -static-libgcc
install -m 644 "$OUT/siappdll.dll" "$DLL"
# which source the DLL was built from: the launcher compares it with
# spacenav/siappdll.c and says when to run this script again (the DLL is
# outside the migrations, so an updated checkout does not rebuild it)
mkdir -p "$WINEPREFIX/.inventor-on-linux"
sha256sum "$PROJECT_DIR/spacenav/siappdll.c" | cut -d' ' -f1 > "$WINEPREFIX/.inventor-on-linux/siappdll-source"
ok "siappdll.dll -> $DLL"

[ -S /run/spnav.sock ] && ok "spacenavd is running" \
    || warn "spacenavd is not running: sudo pacman -S --needed spacenavd && sudo systemctl enable --now spacenavd"
command -v socat >/dev/null && ok "socat found" || warn "socat missing (the launcher relays spacenavd with it): sudo pacman -S --needed socat"
info "buttons: ${XDG_CONFIG_HOME:-$HOME/.config}/inventor-on-linux/spacemouse.ini (created at the next start)"
