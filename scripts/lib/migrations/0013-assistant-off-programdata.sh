# shellcheck shell=bash
# Step 0013: the Autodesk Assistant add-in off again in Inventor 2027.2 and
# later. Its panel is drawn wrongly under Wine (notes/disabled-addins.md), so
# it has been off by default (INV_DEFAULT_DISABLED_ADDINS). Up to 2027.1 its
# Autodesk.AssistantAddin.Inventor.addin was in Bin\Addins; 2027.2 moved it
# to ProgramData\Autodesk\Inventor <year>\Addins\Assistant\<version>\ with
# LoadOnStartUp=1, where cfg_disable_addins did not look, so it loaded at
# every start (found by @krokosik, Autodesk-Inventor-for-Linux #36; seen in
# a fresh 2027.2 prefix by the maintainer, 2026-11-23). Only the .addin file
# moves, to Addins.disabled\programdata\ with the same relative path; the
# add-in's DLLs stay (#37, the MCP server, lives in that folder too).
# cfg_disable_addins does the same after every install and update since,
# so a later version folder is caught there. `addins.sh enable assistant`
# puts it back. A copy already off is left alone.
MIG_DESC="Autodesk Assistant add-in off again in 2027.2 and later (it moved to ProgramData)"

# FROM and TO (relative to the prefix) for each ProgramData copy of a
# default-off add-in that is still on; both go into the backup, so that
# --restore puts the file back and removes the moved copy
_mig_assistant_files() {
    local f rel base="${P_PD_ADDINS#"$WINEPREFIX"/}" off="${P_PD_ADDINS_OFF#"$WINEPREFIX"/}"
    for f in "${INV_DEFAULT_DISABLED_ADDINS[@]}"; do
        while IFS= read -r rel; do
            [ -n "$rel" ] || continue
            [ -e "$P_PD_ADDINS_OFF/$rel" ] && continue
            printf '%s\n%s\n' "$base/$rel" "$off/$rel"
        done < <(pd_addins_matching "$P_PD_ADDINS" "$f")
    done
}

MIG_BACKUP="$(_mig_assistant_files)"

mig_needed() { [ -n "$(_mig_assistant_files)" ]; }

mig_apply() {
    local f rel
    for f in "${INV_DEFAULT_DISABLED_ADDINS[@]}"; do
        while IFS= read -r rel; do
            [ -n "$rel" ] && info "off: ProgramData\\...\\Addins\\$rel"
        done < <(pd_addin_disable "$f")
    done
}
