# shellcheck shell=bash
# Step 0012: the Interactive Tutorial add-in off again in a prefix without
# Microsoft's .NET Framework 4.8. Step 0010 turned it on in every prefix,
# but it was only tested with .NET Framework 4.8 (2026-11-16). On Wine Mono
# - every prefix installed before 2026-11-11, so every v0.3.x installation
# upgraded to v0.4.0 - Inventor crashed right after the splash at every
# start ("Can't find custom attr constructor image: ...InteractiveTutorial.dll",
# then a native crash in CCWInvokeInternal; found by @Lukas10999,
# 2026-11-18, Autodesk-Inventor-for-Linux #8), and
# `addins.sh disable InteractiveTutorial` was enough to fix it. So exactly
# that: Autodesk.InteractiveTutorial.Inventor.addin moves from Bin\Addins
# back to Addins.disabled; its two libraries stay in Bin, as in the tested
# fix (and as `addins.sh disable` leaves them). With .NET Framework 4.8
# nothing changes. common.sh lists the add-in in INV_DOTNET48_ADDINS since,
# so a reinstall with .NET Framework 4.8 (cfg_disable_addins),
# `addins.sh enable-safe` and `addins.sh reset` turn it on there and keep
# it off without. A copy already in Addins.disabled is left alone (the one
# in Bin\Addins too, with a warning).
MIG_DESC="Interactive Tutorial add-in off without .NET Framework 4.8 (it crashes Inventor on Wine Mono)"

_mig_tutorial=Autodesk.InteractiveTutorial.Inventor.addin

# FROM TO (relative to the prefix) if this step would move the add-in;
# "all": regardless of .NET Framework 4.8 (no wine call, for MIG_BACKUP)
_mig_tutorial_move() {
    local r="${P_INV#"$WINEPREFIX"/}" src
    src="$(find "$P_ADDINS" -maxdepth 1 -type f -iname "$_mig_tutorial" -printf '%f\n' 2>/dev/null | head -1)"
    [ -n "$src" ] || return 0
    if [ -n "$(find "$P_ADDINS_OFF" -maxdepth 1 -iname "$src" 2>/dev/null)" ]; then
        [ "${1:-}" = all ] || warn "$src is in Bin\\Addins and in Addins.disabled - left as it is"
        return 0
    fi
    [ "${1:-}" = all ] || ! dotnet48_present || return 0
    printf '%s\n%s\n' "$r/Bin/Addins/$src" "$r/Addins.disabled/$src"
}

MIG_BACKUP="$(_mig_tutorial_move all)"

mig_needed() { [ -n "$(_mig_tutorial_move)" ]; }

mig_apply() {
    local from to
    while IFS= read -r from && IFS= read -r to; do
        mkdir -p "$WINEPREFIX/$(dirname "$to")"
        mv -n -- "$WINEPREFIX/$from" "$WINEPREFIX/$to"
        info "off (needs .NET Framework 4.8): ${to##*/}"
    done < <(_mig_tutorial_move)
}
