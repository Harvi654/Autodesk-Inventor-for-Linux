#!/bin/bash
# List / enable / disable Inventor add-ins in the prefix.
# rebuild-prefix.sh disables some of them (see notes/disabled-addins.md);
# this lets you turn them back on one by one to test.
#
# Usage:
#   bash scripts/addins.sh list
#   bash scripts/addins.sh enable  <name-or-part>    e.g. enable InteractiveTutorial
#   bash scripts/addins.sh disable <name-or-part>
#   bash scripts/addins.sh enable-safe     everything except iLogic and Anark
#                                          (also restores InteractiveTutorial.dll)

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

ADDINS="$P_INV/Bin/Addins"
OFF="$ADDINS/disabled"
LIBS="$OFF/libs"
[ -d "$ADDINS" ] || die "no add-in folder: $ADDINS (build the prefix first)"
mkdir -p "$OFF"

pick() {  # pick <dir> <pattern> -> one matching .addin file name
    local m
    mapfile -t m < <(find "$1" -maxdepth 1 -iname "*$2*.addin" -printf '%f\n' | sort)
    [ ${#m[@]} -gt 0 ] || die "no add-in matching '$2' in $1"
    [ ${#m[@]} -eq 1 ] || die "'$2' matches several: ${m[*]}"
    printf '%s\n' "${m[0]}"
}

restore_tutorial_libs() {
    local f
    for f in InteractiveTutorial.dll InteractiveTutorial.resources.dll; do
        [ -f "$LIBS/$f" ] || continue
        if [ "$f" = InteractiveTutorial.resources.dll ]; then mv "$LIBS/$f" "$P_INV/Bin/en-US/"; else mv "$LIBS/$f" "$P_INV/Bin/"; fi
        info "restored $f"
    done
}

case "${1:-list}" in
    list)
        echo "enabled:";  find "$ADDINS" -maxdepth 1 -iname '*.addin' -printf '    %f\n' | sort
        echo "disabled:"; find "$OFF" -maxdepth 1 -iname '*.addin' -printf '    %f\n' | sort
        [ -d "$LIBS" ] && find "$LIBS" -maxdepth 1 -type f -printf '    (moved library) %f\n'
        ;;
    enable)
        f="$(pick "$OFF" "${2:?name}")"; mv "$OFF/$f" "$ADDINS/"; ok "enabled $f"
        case "$f" in *InteractiveTutorial*) restore_tutorial_libs ;; esac
        ;;
    disable)
        f="$(pick "$ADDINS" "${2:?name}")"; mv "$ADDINS/$f" "$OFF/"; ok "disabled $f"
        ;;
    enable-safe)
        while IFS= read -r f; do
            case "$f" in *ilogic*|*Anark*) info "kept disabled: $f"; continue ;; esac
            mv "$OFF/$f" "$ADDINS/"; ok "enabled $f"
        done < <(find "$OFF" -maxdepth 1 -iname '*.addin' -printf '%f\n' | sort)
        restore_tutorial_libs
        ;;
    *) die "usage: $0 list | enable NAME | disable NAME | enable-safe" ;;
esac
