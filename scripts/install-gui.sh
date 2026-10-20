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
HICOLOR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
mkdir -p "$APPS"
# one PNG per size: a simplified drawing up to 32 px, the detailed one above
for png in "$PROJECT_DIR"/config/icons/hicolor/*/inventor-on-linux.png; do
    size="$(basename "$(dirname "$png")")"
    mkdir -p "$HICOLOR/$size/apps"
    cp -f "$png" "$HICOLOR/$size/apps/inventor-on-linux.png"
done
rm -f "$HICOLOR/scalable/apps/inventor-on-linux.svg"   # older version; a scalable icon would win over the small PNGs
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
gtk-update-icon-cache -q -f -t "$HICOLOR" 2>/dev/null || true
for k in kbuildsycoca6 kbuildsycoca5; do command -v "$k" >/dev/null && { "$k" >/dev/null 2>&1 || true; break; }; done

exec python3 -I "$SCRIPTS_DIR/gui/installer.py" "$@"
