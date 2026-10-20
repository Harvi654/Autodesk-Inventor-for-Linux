#!/bin/bash
# Fonts for a prefix without Windows: free fonts from the distribution,
# registered so DirectWrite/WPF list them, plus family replacements for the
# Windows fonts Inventor and WPF ask for by name.
#
# Why: WPF's font fallback (composite font "Global User Interface") maps
# characters to Segoe UI, Arial, Tahoma, ...; when it finds no font at all it
# kills Inventor on purpose (Environment.FailFast in
# TypefaceMap.MapUnresolvedCharacters). Wine's DirectWrite lists only fonts
# registered under HKLM\...\Windows NT\CurrentVersion\Fonts and maps missing
# families through HKCU\Software\Wine\Fonts\Replacements (gdi32 reads the same
# key), so both are set here.
#
#   Arial / Helvetica / MS Sans Serif -> Liberation Sans  (metric-compatible)
#   Times New Roman                    -> Liberation Serif
#   Courier New                        -> Liberation Mono
#   Segoe UI (+ variants), Verdana ... -> Noto Sans, DejaVu Sans
#   Calibri / Cambria                  -> Carlito / Caladea if installed
#
# Packages (official Arch repos): ttf-liberation noto-fonts ttf-dejavu
# (optional: ttf-carlito ttf-caladea, noto-fonts-cjk for Chinese/Japanese/Korean)
#
# Usage: bash scripts/linux-fonts.sh [--remove-windows-fonts]
#   --remove-windows-fonts  for testing a prefix that got Windows fonts from
#                           windows-fonts.sh: moves them to
#                           C:\windows\Fonts.windows-copy and unregisters them
#                           (windows-fonts.sh puts them back)

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

REMOVE_WIN=0
[ "${1:-}" = --remove-windows-fonts ] && REMOVE_WIN=1

DST="$P_C/windows/Fonts"
[ -d "$P_C/windows" ] || die "no prefix at $WINEPREFIX"
mkdir -p "$DST"

# file globs per font directory candidates (Arch, Debian/Ubuntu, Fedora paths)
find_fonts() {
    local pat dirs=()
    for pat in "${INV_FONT_DIRS[@]}"; do [ -d "$pat" ] && dirs+=("$pat"); done
    [ ${#dirs[@]} -gt 0 ] || return 0
    # "|| true": under set -e a find error (unreadable dir) would end the loop
    for pat in "$@"; do
        find -L "${dirs[@]}" -type f -name "$pat" 2>/dev/null || true
    done | sort -u
}

mapfile -t FILES < <(
    # Noto comes as static (NotoSans-Regular.ttf) or variable fonts
    # (NotoSans[wdth,wght].ttf, NotoSans-Italic[wdth,wght].ttf - Arch)
    find_fonts 'Liberation*.ttf' \
               'DejaVuSans*.ttf' 'DejaVuSerif*.ttf' \
               'NotoSans-*.ttf' 'NotoSans\[*.ttf' 'NotoSerif-*.ttf' 'NotoSerif\[*.ttf' \
               'NotoSansMono-*.ttf' 'NotoSansMono\[*.ttf' \
               'NotoSansSymbols-*.ttf' 'NotoSansSymbols\[*.ttf' 'NotoSansSymbols2-*.ttf' \
               'NotoSansMath-*.ttf' \
               'Carlito-*.ttf' 'Caladea-*.ttf'
    find "$WINE_DATA_DIR/fonts" -maxdepth 1 -type f -name '*.ttf' 2>/dev/null
)

# (no "printf | grep -q": with pipefail the early exit of grep fails the pipe)
have() {
    local f p
    for f in "${FILES[@]}"; do
        for p in "$@"; do
            # shellcheck disable=SC2053
            [[ "${f##*/}" == $p ]] && return 0
        done
    done
    return 1
}
MISSING=()
have 'LiberationSans-Regular.ttf'                 || MISSING+=(ttf-liberation)
have 'NotoSans-Regular.ttf' 'NotoSans\[*.ttf'      || MISSING+=(noto-fonts)
have 'DejaVuSans.ttf'                             || MISSING+=(ttf-dejavu)
if [ ${#MISSING[@]} -gt 0 ]; then
    die "missing fonts - install them first: sudo pacman -S --needed ${MISSING[*]}"
fi

if [ "$REMOVE_WIN" -eq 1 ]; then
    WINREG="$PROJECT_DIR/registry/windows-fonts.reg"
    [ -f "$WINREG" ] || die "no $WINREG - nothing to remove"
    info "moving the Windows fonts listed in $(basename "$WINREG") out of the prefix"
    mkdir -p "$DST.windows-copy"
    UNREG="$(mktemp --suffix=.reg)"
    {
        printf 'Windows Registry Editor Version 5.00\r\n\r\n'
        printf '[HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Fonts]\r\n'
        grep -a '(Windows)"=' "$WINREG" | while IFS= read -r line; do
            name="${line%%\"=*}"; name="${name#\"}"
            file="${line#*\"=\"}"; file="${file%\"*}"
            [ -f "$DST/$file" ] && mv -f "$DST/$file" "$DST.windows-copy/"
            printf '"%s"=-\r\n' "$name"
        done
    } > "$UNREG"
    wine_stop
    import_reg_file "$UNREG"
    rm -f "$UNREG"
    ok "$(ls "$DST.windows-copy" | wc -l) Windows font files moved to $DST.windows-copy"
fi

info "copying ${#FILES[@]} font files into C:\\windows\\Fonts"
for f in "${FILES[@]}"; do
    cp -f "$f" "$DST/"
done

REG="$(mktemp --suffix=.reg)"
{
    printf 'Windows Registry Editor Version 5.00\r\n\r\n'
    printf '[HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Fonts]\r\n'
    for f in "${FILES[@]}"; do
        b="$(basename "$f")"
        printf '"%s (Linux)"="%s"\r\n' "${b%.*}" "$b"
    done
    printf '\r\n[HKEY_CURRENT_USER\\Software\\Wine\\Fonts\\Replacements]\r\n'
    # REG_MULTI_SZ: first family that exists wins (dwrite); hex(7) = UTF-16LE list
    multi() {
        local out="" s
        for s in "$@"; do out+="$s"$'\n'; done
        out+=$'\n'
        printf 'hex(7):%s' "$(printf '%s' "$out" | tr '\n' '\0' | iconv -f UTF-8 -t UTF-16LE | od -An -tx1 -v | tr -s ' \n' ',' | sed 's/^,//;s/,$//')"
    }
    sans=("Noto Sans" "DejaVu Sans" "Liberation Sans")
    for fam in "Segoe UI" "Segoe UI Semibold" "Segoe UI Semilight" "Segoe UI Light" "Segoe UI Black" \
               "Verdana" "Tahoma" "Trebuchet MS" "Arial Unicode MS" "Lucida Sans Unicode" "Microsoft YaHei UI"; do
        printf '"%s"=%s\r\n' "$fam" "$(multi "${sans[@]}")"
    done
    for fam in "Segoe UI Symbol" "Segoe UI Emoji" "Segoe MDL2 Assets" "Segoe Fluent Icons"; do
        printf '"%s"=%s\r\n' "$fam" "$(multi "Noto Sans Symbols 2" "Noto Sans Symbols" "DejaVu Sans")"
    done
    for fam in "Arial" "Helvetica" "MS Sans Serif" "Microsoft Sans Serif" "Arial Narrow"; do
        printf '"%s"=%s\r\n' "$fam" "$(multi "Liberation Sans" "DejaVu Sans")"
    done
    printf '"Times New Roman"=%s\r\n' "$(multi "Liberation Serif" "DejaVu Serif")"
    printf '"Georgia"=%s\r\n' "$(multi "Noto Serif" "Liberation Serif")"
    for fam in "Courier New" "Consolas" "Lucida Console"; do
        printf '"%s"=%s\r\n' "$fam" "$(multi "Liberation Mono" "DejaVu Sans Mono")"
    done
    printf '"Calibri"=%s\r\n' "$(multi "Carlito" "Liberation Sans")"
    printf '"Cambria"=%s\r\n' "$(multi "Caladea" "Liberation Serif")"
    printf '"Cambria Math"=%s\r\n' "$(multi "Noto Sans Math" "DejaVu Serif")"
} > "$REG"

info "registering them and the family replacements (Wine stopped for this)"
wine_stop
import_reg_file "$REG"
wine_stop
cp -f "$REG" "$PROJECT_DIR/registry/linux-fonts.reg" 2>/dev/null || true
rm -f "$REG"
ok "done - DirectWrite/WPF list them on the next start"
