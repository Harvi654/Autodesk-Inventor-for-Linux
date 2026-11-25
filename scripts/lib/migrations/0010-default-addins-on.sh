# shellcheck shell=bash
# Step 0010: add-ins that were off by default until 2026-11-16 are on again,
# as on Windows. The maintainer turned them all on at once with
# `addins.sh enable-safe` on a copy of a 2027 prefix with .NET Framework
# 4.8, winum-11.20-2 and vkd3d-proton 3.0.1-winum-1 (2026-11-16):
# - Autodesk.SharedViews: share and Autodesk Viewer work - only with .NET
#   Framework 4.8 (on wine-mono it ended Inventor), so it stays off without;
# - Autodesk.InteractiveTutorial: the tutorial downloads and runs (its
#   window opens at the far right, a WebView placement issue); its
#   InteractiveTutorial.dll and en-US\InteractiveTutorial.resources.dll
#   come back from Addins.disabled\libs to Bin;
# - Autodesk.Feedback, Autodesk.PerfFeedbackAddin: load, nothing broke
#   (Inventor's own settings turn usage reporting off);
# - autodesk.translatorfusion: loads; real use needs Autodesk Desktop
#   Connector and Fusion Team data, which are not installed.
# Autodesk.AssistantAddin stays where it is (its panel is drawn wrongly).
# Exactly these files move; an add-in already in Bin\Addins is left as it
# is (its disabled copy too). Whoever wants one off again:
# bash scripts/addins.sh disable NAME. notes/disabled-addins.md.
MIG_DESC="add-ins on as on Windows: Feedback, PerfFeedback, InteractiveTutorial, translatorfusion, SharedViews (.NET 4.8)"

_mig_addins=(Autodesk.Feedback.Inventor.addin Autodesk.PerfFeedbackAddin.Inventor.addin
             Autodesk.InteractiveTutorial.Inventor.addin autodesk.translatorfusion.inventor.addin)
_mig_shared=Autodesk.SharedViews.Inventor.addin

# FROM TO pairs (relative to the prefix) that this step would move; the
# SharedViews pair only with .NET Framework 4.8 unless "all" is given
_mig_moves() {
    local r="${P_INV#"$WINEPREFIX"/}" f src
    local -a names=("${_mig_addins[@]}")
    if [ "${1:-}" = all ] || dotnet48_present; then names+=("$_mig_shared"); fi
    for f in "${names[@]}"; do
        src="$(find "$P_ADDINS_OFF" -maxdepth 1 -type f -iname "$f" -printf '%f\n' 2>/dev/null | head -1)"
        [ -n "$src" ] || continue
        [ -n "$(find "$P_ADDINS" -maxdepth 1 -iname "$src" 2>/dev/null)" ] && continue
        printf '%s\n%s\n' "$r/Addins.disabled/$src" "$r/Bin/Addins/$src"
    done
    for f in InteractiveTutorial.dll en-US/InteractiveTutorial.resources.dll; do
        [ -f "$P_ADDINS_OFF/libs/${f##*/}" ] && [ ! -e "$P_INV/Bin/$f" ] || continue
        printf '%s\n%s\n' "$r/Addins.disabled/libs/${f##*/}" "$r/Bin/$f"
    done
}

# both ends of every move that could happen (no wine call when sourced
# by the runner): what is restored if the step fails or is put off
MIG_BACKUP="$(_mig_moves all)"

mig_needed() { [ -n "$(_mig_moves)" ]; }

mig_apply() {
    local from to
    while IFS= read -r from && IFS= read -r to; do
        mkdir -p "$WINEPREFIX/$(dirname "$to")"
        mv -n -- "$WINEPREFIX/$from" "$WINEPREFIX/$to"
        info "on: ${to##*/}"
    done < <(_mig_moves)
}
