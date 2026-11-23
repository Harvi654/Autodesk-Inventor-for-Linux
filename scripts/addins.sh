#!/bin/bash
# List / enable / disable Inventor add-ins in the prefix.
# finish-install.sh / rebuild-prefix.sh turn off a few (notes/disabled-addins.md:
# the Assistant; without .NET Framework 4.8 also 3D PDF, SharedViews and InteractiveTutorial);
# this lets you turn them on or off one by one. Add-ins are in Bin\Addins and,
# since 2027.2, also in ProgramData\Autodesk\Inventor <year>\Addins (the
# Assistant); both are listed and handled.
#
# Usage:
#   bash scripts/addins.sh list
#   bash scripts/addins.sh enable  <name-or-part>    e.g. enable assistant
#   bash scripts/addins.sh disable <name-or-part>
#   bash scripts/addins.sh enable-safe     everything, except the add-ins that need
#                                          .NET Framework 4.8 when it is missing
#                                          (also restores InteractiveTutorial.dll)
#   bash scripts/addins.sh reset           back to the defaults

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

echo "Inventor $INV_YEAR in $INV_PREFIX (prefix: $INV_PREFIX_SOURCE; INV_YEAR=... or INV_PREFIX=... chooses another)"
ADDINS="$P_ADDINS"
OFF="$P_ADDINS_OFF"
LIBS="$OFF/libs"
[ -d "$ADDINS" ] || die "no add-in folder: $ADDINS (build the prefix first)"
mkdir -p "$OFF"
migrate_disabled_addins

# pick <on|off> <pattern> -> "bin NAME" or "pd NAME": the one add-in matching
# the pattern among those on (Bin\Addins and ProgramData) or off
pick() {
    local bindir pddir m
    if [ "$1" = on ]; then bindir="$ADDINS"; pddir="$P_PD_ADDINS"; else bindir="$OFF"; pddir="$P_PD_ADDINS_OFF"; fi
    mapfile -t m < <( { find "$bindir" -maxdepth 1 -iname "*$2*.addin" -printf 'bin %f\n'
                        [ -d "$pddir" ] && find "$pddir" -mindepth 2 -maxdepth 4 -type f -iname "*$2*.addin" -printf 'pd %f\n'
                      } 2>/dev/null | sort -u)
    [ ${#m[@]} -gt 0 ] || die "no add-in matching '$2' ($1)"
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
        [ -d "$P_PD_ADDINS" ] && find "$P_PD_ADDINS" -mindepth 2 -maxdepth 4 -type f -iname '*.addin' -printf '    %f  (ProgramData: %P)\n' | sort
        echo "disabled:"; find "$OFF" -maxdepth 1 -iname '*.addin' -printf '    %f\n' | sort
        [ -d "$P_PD_ADDINS_OFF" ] && find "$P_PD_ADDINS_OFF" -mindepth 2 -maxdepth 4 -type f -iname '*.addin' -printf '    %f  (ProgramData: %P)\n' | sort
        if [ -d "$LIBS" ]; then find "$LIBS" -maxdepth 1 -type f -printf '    (moved library) %f\n'; fi
        ;;
    enable)
        sel="$(pick off "${2:?name}")"; kind="${sel%% *}"; f="${sel#* }"
        if [ "$kind" = bin ]; then mv "$OFF/$f" "$ADDINS/"
        else pd_addin_enable "$f" >/dev/null; fi
        ok "enabled $f"
        case "$f" in *InteractiveTutorial*) restore_tutorial_libs ;; esac
        ;;
    disable)
        sel="$(pick on "${2:?name}")"; kind="${sel%% *}"; f="${sel#* }"
        if [ "$kind" = bin ]; then mv "$ADDINS/$f" "$OFF/"
        else pd_addin_disable "$f" >/dev/null; fi
        ok "disabled $f"
        ;;
    enable-safe)
        has48=1; dotnet48_present || has48=""
        while IFS= read -r f; do
            if [ -z "$has48" ] && printf '%s\n' "${INV_DOTNET48_ADDINS[@]}" | grep -qixF -- "$f"; then
                info "kept disabled: $f (needs .NET Framework 4.8)"; continue
            fi
            mv "$OFF/$f" "$ADDINS/"; ok "enabled $f"
        done < <(find "$OFF" -maxdepth 1 -iname '*.addin' -printf '%f\n' | sort)
        while IFS= read -r f; do
            [ -n "$(pd_addin_enable "$f")" ] && ok "enabled $f (ProgramData)"
        done < <([ -d "$P_PD_ADDINS_OFF" ] && find "$P_PD_ADDINS_OFF" -mindepth 2 -maxdepth 4 -type f -iname '*.addin' -printf '%f\n' | sort -u)
        restore_tutorial_libs
        ;;
    reset)
        mapfile -t defoff < <(inv_default_disabled_addins)
        for f in "${defoff[@]}"; do
            if [ -f "$ADDINS/$f" ]; then mv "$ADDINS/$f" "$OFF/"; ok "disabled $f"; fi
            [ -n "$(pd_addin_disable "$f")" ] && ok "disabled $f (ProgramData)"
        done
        # on by default: the .NET 4.8 add-ins when it is there, and those
        # that were off by default until 2026-11-16 (with InteractiveTutorial's
        # libraries); add-ins turned off by hand otherwise stay off
        for f in "${INV_DOTNET48_ADDINS[@]}" "${INV_ADDINS_ON_SINCE_2026_11_16[@]}"; do
            printf '%s\n' "${defoff[@]}" | grep -qixF -- "$f" && continue
            if [ -f "$OFF/$f" ]; then mv "$OFF/$f" "$ADDINS/"; ok "enabled $f"; fi
        done
        restore_tutorial_libs
        ;;
    *) die "usage: $0 list | enable NAME | disable NAME | enable-safe | reset" ;;
esac
