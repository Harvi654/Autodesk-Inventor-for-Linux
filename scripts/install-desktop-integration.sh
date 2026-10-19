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
MIME_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/mime"
MIME_XML="$MIME_DIR/packages/autodesk-inventor.xml"
# Inventor's file types: MIME type, pattern, description
INV_TYPES=(
    "application/x-autodesk-inventor-part|*.ipt|Autodesk Inventor part"
    "application/x-autodesk-inventor-assembly|*.iam|Autodesk Inventor assembly"
    "application/x-autodesk-inventor-drawing|*.idw|Autodesk Inventor drawing"
    "application/x-autodesk-inventor-presentation|*.ipn|Autodesk Inventor presentation"
    "application/x-autodesk-inventor-project|*.ipj|Autodesk Inventor project"
)

if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$APPS/adskidmgr-handler.desktop" "$APPS/$NAME.desktop" "$ICONS/$NAME.png" "$ICONS/$NAME"-*.png \
          "$BIN/adskidmgr-callback" "$BIN/launch-inventor" "$MIME_XML"
    update-desktop-database "$APPS" 2>/dev/null || true
    update-mime-database "$MIME_DIR" 2>/dev/null || true
    ok "removed"; exit 0
fi

mkdir -p "$APPS" "$ICONS" "$BIN"
chmod +x "$SCRIPTS_DIR"/*.sh

# Entries Wine's menu builder made for this prefix before it was turned off
# (lib/common.sh): Autodesk's Start-menu shortcuts and file associations that
# (Exec=env "WINEPREFIX=/path" wine ...)
# start the programs without the launcher. Other Wine programs are left alone.
removed=0
while IFS= read -r -d '' f; do
    rm -f "$f"; removed=$((removed + 1))
done < <(grep -rlZF -e "WINEPREFIX=$INV_PREFIX\"" -e "WINEPREFIX=\"$INV_PREFIX\"" "$APPS" 2>/dev/null || true)
find "$APPS/wine" -type d -empty -delete 2>/dev/null || true
[ "$removed" -eq 0 ] || ok "removed $removed Wine menu entries of $INV_PREFIX"

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
# the program's own icon from Inventor.exe (Bin/idv.ico is Inventor View's)
ICO="$P_INV/Bin/idv.ico"
IM="$(command -v magick || command -v convert || true)"
if python3 -I "$COMMON_DIR/exe-icon.py" "$P_INV/Bin/Inventor.exe" "$ICONS/$NAME.png" >/dev/null 2>&1; then
    ok "icon extracted from Inventor.exe"
elif [ -n "$IM" ] && [ -f "$ICO" ]; then
    "$IM" "${ICO}[0]" -thumbnail 256x256 -flatten "$ICONS/$NAME.png" 2>/dev/null && ok "icon extracted" \
        || warn "icon extraction failed"
fi
gtk-update-icon-cache -q -t "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" 2>/dev/null || true
EXEC="$BIN/launch-inventor"
# a prefix other than the default has to be passed on
[ "$(realpath -m "$INV_PREFIX")" = "$(realpath -m "$HOME/.wine-inventor$INV_YEAR")" ] \
    || EXEC="env INV_PREFIX=$(realpath -m "$INV_PREFIX") $EXEC"
# File types: the files are OLE compound documents, so without this file
# managers call them "document" and offer an office suite. Sub-class of
# application/x-ole-storage: the file name decides, not the content sniffing.
mkdir -p "$MIME_DIR/packages"
# each type's own icon, as Inventor registered it (DefaultIcon); the program
# icon where none is found
declare -A TYPE_ICON=()
while read -r ext res _; do
    [ "$res" = ok ] && TYPE_ICON[$ext]="$NAME-$ext"
done < <(python3 -I "$COMMON_DIR/file-type-icons.py" "$WINEPREFIX" "$ICONS" "$NAME" ipt iam idw ipn ipj 2>/dev/null || true)
gtk-update-icon-cache -q -t "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" 2>/dev/null || true
OWN_ICONS="${!TYPE_ICON[*]}"
{
    echo '<?xml version="1.0" encoding="UTF-8"?>'
    echo '<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">'
    for t in "${INV_TYPES[@]}"; do
        IFS='|' read -r mt pat desc <<<"$t"
        base=application/x-ole-storage; [ "$pat" = "*.ipj" ] && base=application/xml   # projects are XML
        ext="${pat#*.}"; icon="${TYPE_ICON[$ext]:-$NAME}"
        echo "  <mime-type type=\"$mt\"><comment>$desc</comment><sub-class-of type=\"$base\"/><icon name=\"$icon\"/><glob pattern=\"$pat\" weight=\"80\"/></mime-type>"
    done
    echo '</mime-info>'
} > "$MIME_XML"
update-mime-database "$MIME_DIR" 2>/dev/null || warn "update-mime-database not found - file types not registered"
MIMES="$(for t in "${INV_TYPES[@]}"; do printf '%s;' "${t%%|*}"; done)"
# .dwg (AutoCAD, also Inventor drawings): offered, but not made the default
MIMES+="image/vnd.dwg;application/acad;image/x-dwg;"
cat > "$APPS/$NAME.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Autodesk Inventor $INV_YEAR
GenericName=CAD Application
Comment=Autodesk Inventor Professional $INV_YEAR (Wine)
Exec=$EXEC %F
MimeType=$MIMES
Icon=$NAME
Terminal=false
Categories=Graphics;Engineering;3DGraphics;
StartupWMClass=inventor.exe
Keywords=CAD;3D;Modeling;Engineering;Inventor;Autodesk;
EOF
update-desktop-database "$APPS" 2>/dev/null || true
for t in "${INV_TYPES[@]}"; do xdg-mime default "$NAME.desktop" "${t%%|*}" 2>/dev/null || true; done
ok "launcher entry: $APPS/$NAME.desktop"
ok "file types: .ipt .iam .idw .ipn .ipj open in Inventor ($(xdg-mime query default application/x-autodesk-inventor-part 2>/dev/null)), own icons: ${OWN_ICONS:-none found}"

BROWSER_DEFAULT="$(xdg-settings get default-web-browser 2>/dev/null || true)"
info "Default browser (used for the Autodesk login): ${BROWSER_DEFAULT:-<not set - run: xdg-settings set default-web-browser firefox.desktop>}"
