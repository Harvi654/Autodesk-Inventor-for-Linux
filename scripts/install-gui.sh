#!/bin/bash
# Graphical installer: the same steps as scripts/install.sh, with a window that
# shows the phases, a progress bar and the output, and asks for the sudo
# password itself. Needs Python with GTK 4 (PyGObject); if it is missing it is
# installed first (that one step asks for the password here in the terminal).
#
#   bash scripts/install-gui.sh

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

[ "$EUID" -ne 0 ] || die "run this as your normal user, not with sudo"
[ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ] || die "no graphical session - use the terminal installer: bash scripts/install.sh"

have_gtk4() {
    python3 -I -c 'import gi; gi.require_version("Gtk", "4.0"); from gi.repository import Gtk' >/dev/null 2>&1
}

if ! have_gtk4; then
    case "$INV_DISTRO" in
        arch)   PKGS=(python python-gobject gtk4);          CMD=(sudo pacman -S --needed --noconfirm) ;;
        debian) PKGS=(python3 python3-gi gir1.2-gtk-4.0);   CMD=(sudo apt-get install -y) ;;
        fedora) PKGS=(python3 python3-gobject gtk4);        CMD=(sudo dnf install -y) ;;
        *)      die "unsupported distribution - use: bash scripts/install.sh" ;;
    esac
    info "the installer window needs GTK 4 for Python: ${PKGS[*]}"
    "${CMD[@]}" "${PKGS[@]}"
    have_gtk4 || die "GTK 4 for Python is still not usable - use the terminal installer: bash scripts/install.sh"
fi

chmod +x "$SCRIPTS_DIR/gui/askpass.py"
exec python3 -I "$SCRIPTS_DIR/gui/installer.py" "$@"
