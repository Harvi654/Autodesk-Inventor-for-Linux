#!/bin/bash
# Import Inventor's file types (.ipt, .iam, .idw, .ipn, .ipj, ...) from the
# Windows user's registry: icons (DefaultIcon -> SrvRes.dll) and the shell
# extensions for thumbnails, info tips and property pages.
#
# Inventor registers these per user, i.e. in
# Users\<you>\AppData\Local\Microsoft\Windows\UsrClass.dat - not in NTUSER.DAT,
# so export-registry.sh does not have them. Without them file dialogs and the
# New dialog show Inventor's old "I" icon for every file type.
#
# Shell verbs (open/print commands) are not imported: they hold 8.3 paths of the
# Windows disk; Inventor registers working ones itself on start.
#
# Usage: bash scripts/import-file-types.sh

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

command -v hivexregedit >/dev/null || die "hivexregedit not found: sudo pacman -S hivex"
command -v python3 >/dev/null || die "python3 not found"
[ -d "$P_C/windows" ] || die "no prefix at $WINEPREFIX"
WU="$(detect_win_user)"
USRCLASS="$WIN_ROOT/Users/$WU/AppData/Local/Microsoft/Windows/UsrClass.dat"
SOFTWARE_HIVE="$WIN_ROOT/Windows/System32/config/SOFTWARE"
[ -f "$USRCLASS" ] || die "not found: $USRCLASS"
FILTER="$SCRIPTS_DIR/lib/regfilter.py"

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
OUT="$PROJECT_DIR/registry/inventor-file-types.reg"
mkdir -p "$(dirname "$OUT")"

info "reading $USRCLASS ..."
hivexregedit --export "$USRCLASS" '\' > "$TMP/usrclass.reg"
python3 -I "$FILTER" filter "$TMP/usrclass.reg" "$TMP/user.reg" "$TMP/guids" "$INV_YEAR"

# Classes registered for the whole machine live in the SOFTWARE hive.
cp "$TMP/user.reg" "$OUT"
while IFS= read -r g; do
    [ -n "$g" ] || continue
    for k in "\\Classes\\CLSID\\$g" "\\Classes\\WOW6432Node\\CLSID\\$g"; do
        if hivexregedit --export "$SOFTWARE_HIVE" "$k" > "$TMP/c.reg" 2>/dev/null; then
            python3 -I "$FILTER" fix "$TMP/c.reg" 'HKEY_LOCAL_MACHINE\Software' "$TMP/c2.reg" "$INV_YEAR"
            tail -n +2 "$TMP/c2.reg" >> "$OUT"
            case "$k" in *WOW6432Node*) info "machine class $g (32-bit)" ;; *) info "machine class $g" ;; esac
        fi
    done
done < "$TMP/guids"
ok "written $OUT"

wine_stop
import_reg_file "$OUT"
wine_stop
ok "Inventor file types imported (icons, shell extensions)"
