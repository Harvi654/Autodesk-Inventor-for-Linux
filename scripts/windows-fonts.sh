#!/bin/bash
# Copy the fonts of the mounted Windows installation into the prefix and
# register them, so WPF finds Segoe UI / Arial / Tahoma / Autodesk's fonts.
#
# Without them WPF's font fallback finds nothing for some characters and
# kills Inventor on purpose:
#   Environment.FailFast "Unrecoverable system error."
#   at MS.Internal.Shaping.TypefaceMap.MapUnresolvedCharacters
# (first seen when the App Home page is drawn).
#
# DirectWrite - and therefore WPF - only lists fonts registered under
# HKLM\Software\Microsoft\Windows NT\CurrentVersion\Fonts; copying the files
# alone is not enough.
#
# Usage: bash scripts/windows-fonts.sh

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

SRC="$WIN_ROOT/Windows/Fonts"
DST="$P_C/windows/Fonts"
REG_OUT="$PROJECT_DIR/registry/windows-fonts.reg"

[ -d "$SRC" ] || die "Windows fonts not found at $SRC (is $WIN_ROOT mounted?)"
[ -d "$P_C/windows" ] || die "no prefix at $WINEPREFIX"
mkdir -p "$DST" "$(dirname "$REG_OUT")"

info "copying TrueType/OpenType fonts from $SRC ..."
rsync -rt --info=stats1 --include='*.ttf' --include='*.TTF' --include='*.ttc' --include='*.TTC' \
      --include='*.otf' --include='*.OTF' --exclude='*' "$SRC/" "$DST/"

# One registry value per file. DirectWrite resolves a value without a
# backslash to %windir%\Fonts\<value>; the value NAME is not used by it.
n=0
{
    printf 'Windows Registry Editor Version 5.00\r\n\r\n'
    printf '[HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Fonts]\r\n'
    while IFS= read -r f; do
        name="${f//\"/}"
        printf '"%s (Windows)"="%s"\r\n' "$name" "$name"
        n=$((n + 1))
    done < <(find "$DST" -maxdepth 1 -type f \( -iname '*.ttf' -o -iname '*.ttc' -o -iname '*.otf' \) -printf '%f\n' | sort)
} > "$REG_OUT"
ok "$n font files in $DST"

info "registering them (Wine stopped for this)"
wine_stop
import_reg_file "$REG_OUT"
wine_stop
ok "done - fonts are listed by DirectWrite/WPF on the next start"
for f in segoeui.ttf arial.ttf tahoma.ttf; do
    if [ -n "$(find "$DST" -maxdepth 1 -iname "$f" -print -quit)" ]; then ok "$f"; else warn "$f missing"; fi
done
