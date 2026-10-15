#!/bin/bash
# Register the adskidmgr:// OAuth2 handler and an app-launcher entry
# (works with rofi/wofi/fuzzel/walker on Hyprland - anything reading .desktop files).
#
# Usage: bash scripts/install-desktop-integration.sh [--uninstall]

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"
BIN="$HOME/.local/bin"
NAME="autodesk-inventor-$INV_YEAR"

if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$APPS/adskidmgr-handler.desktop" "$APPS/$NAME.desktop" "$ICONS/$NAME.png" \
          "$BIN/adskidmgr-callback" "$BIN/launch-inventor"
    update-desktop-database "$APPS" 2>/dev/null || true
    ok "removed"; exit 0
fi

mkdir -p "$APPS" "$ICONS" "$BIN"
chmod +x "$SCRIPTS_DIR"/*.sh

# OAuth2 callback handler
ln -sfn "$SCRIPTS_DIR/adskidmgr-callback.sh" "$BIN/adskidmgr-callback"
cat > "$APPS/adskidmgr-handler.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Autodesk Identity Manager
Exec=$BIN/adskidmgr-callback %u
MimeType=x-scheme-handler/adskidmgr;
NoDisplay=true
EOF
xdg-mime default adskidmgr-handler.desktop x-scheme-handler/adskidmgr
ok "adskidmgr:// -> $(xdg-mime query default x-scheme-handler/adskidmgr)"

# Launcher + icon
ln -sfn "$SCRIPTS_DIR/launch-inventor.sh" "$BIN/launch-inventor"
ICO="$P_INV/Bin/idv.ico"
IM="$(command -v magick || command -v convert || true)"
if [ -n "$IM" ] && [ -f "$ICO" ]; then
    "$IM" "${ICO}[0]" -thumbnail 256x256 -flatten "$ICONS/$NAME.png" 2>/dev/null && ok "icon extracted" \
        || warn "icon extraction failed"
fi
cat > "$APPS/$NAME.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Autodesk Inventor $INV_YEAR
GenericName=CAD Application
Comment=Autodesk Inventor Professional $INV_YEAR (Wine)
Exec=$BIN/launch-inventor
Icon=$NAME
Terminal=false
Categories=Graphics;Engineering;3DGraphics;
StartupWMClass=inventor.exe
Keywords=CAD;3D;Modeling;Engineering;Inventor;Autodesk;
EOF
update-desktop-database "$APPS" 2>/dev/null || true
ok "launcher entry: $APPS/$NAME.desktop"

BROWSER_DEFAULT="$(xdg-settings get default-web-browser 2>/dev/null || true)"
info "Default browser (used for the Autodesk login): ${BROWSER_DEFAULT:-<not set - run: xdg-settings set default-web-browser firefox.desktop>}"
