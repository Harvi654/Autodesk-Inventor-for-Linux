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

# "Inventor on Linux - Setup" in the app menu: this installer again later
# (repair, update). Removed by install-desktop-integration.sh --uninstall.
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
mkdir -p "$APPS" "$ICON_DIR"
cp -f "$PROJECT_DIR/config/icons/inventor-on-linux.svg" "$ICON_DIR/inventor-on-linux.svg"
cat > "$APPS/io.github.harvi654.InventorInstaller.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Inventor on Linux - Setup
Comment=Install, repair or update Autodesk Inventor on Linux
Exec=bash "$SCRIPTS_DIR/install-gui.sh"
Icon=inventor-on-linux
Terminal=false
Categories=System;Settings;
Keywords=Inventor;Autodesk;CAD;install;update;
StartupWMClass=io.github.harvi654.InventorInstaller
DESKTOP
update-desktop-database "$APPS" 2>/dev/null || true
gtk-update-icon-cache -q -f -t "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" 2>/dev/null || true

exec python3 -I "$SCRIPTS_DIR/gui/installer.py" "$@"
