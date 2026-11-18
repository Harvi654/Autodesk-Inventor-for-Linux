# shellcheck shell=bash
# Step 0013: DWG TrueView (installed with Inventor since 2026-11-16) can
# start in the prefix. Inventor runs it as an in-place OLE server when a
# sketch inserts an AutoCAD file (Insert AutoCAD file - the DWG/DXF wizard
# of File > Open does not use it); on Windows its first start loads the
# per-user registry seed the installer left in UserDataCache\User.dat
# (RegLoadAppKey) and writes it under HKCU\Software\Autodesk\DWG TrueView.
# Wine's RegLoadAppKey is a stub, so under Wine that first start crashes
# (page fault in dwgviewr.exe) and the insert does nothing. The step writes
# the same keys itself: hivexregedit exports the hive, trueview-seed.py
# fills in the installer's folder tokens ([{AppData}], [{ProgramFilesX64}],
# ...) for this prefix and re-roots it under HKEY_CURRENT_USER, regedit
# imports it. The viewer then starts and finishes the setup itself
# (Profile.aws, dwgviewr.startup).
# Second part: the prefix's global `d3dcompiler_47=native` override (for
# Inventor, which ships the DLL in its Bin) also applies to dwgviewr.exe,
# whose folder has none - Wine finds no native file and the viewer hangs
# on its first shader. Autodesk ships the DLL in TrueView's own
# d3dcompiler_v2\ (the same file as Inventor's Bin\d3dcompiler_47.dll);
# a copy next to dwgviewr.exe is what the override expects. Both parts for
# every TrueView found in the prefix (`DWG TrueView <year> - <language>`).
# Without hivex (hivexregedit; INV_HIVEXREGEDIT names another one, tests
# only) the step is put off like 0006, with the package to install in the
# log. docs/arch-hyprland.md, "DWG TrueView: first start, Insert AutoCAD file".
MIG_DESC="DWG TrueView: per-user registry seed (RegLoadAppKey is a Wine stub), d3dcompiler_47 next to dwgviewr.exe"

# every installed TrueView folder, one per line
_mig_tv_dirs() {
    local d
    for d in "$P_C/Program Files/Autodesk/DWG TrueView "*" - "*/; do
        [ -f "$d/dwgviewr.exe" ] || continue
        printf '%s\n' "${d%/}"
    done
}

# the HKCU key UserData.ini names (Registry=HKCU\Software\Autodesk\DWG TrueView\R25)
_mig_tv_key() {   # DIR
    sed -n 's/^Registry=//p' "$1/UserDataCache/UserData.ini" 2>/dev/null | tr -d '\r' | head -1
}

# the seed is wanted when the hive exists and its key has no CurVer yet
_mig_tv_seed_needed() {   # DIR
    local key
    [ -f "$1/UserDataCache/User.dat" ] || return 1
    key="$(_mig_tv_key "$1")"
    [ -n "$key" ] || return 1
    [ -z "$(mig_reg_get "$key" CurVer)" ]
}

_mig_tv_dll_needed() {   # DIR
    [ -f "$1/d3dcompiler_v2/d3dcompiler_47.dll" ] && [ ! -f "$1/d3dcompiler_47.dll" ]
}

# the copied DLL of every TrueView, one path per line because the folder has
# spaces; the leading empty line keeps the runner on the per-line reading
# (which it uses when the list holds a newline) even for a single TrueView
MIG_BACKUP="$(printf '\n'; while IFS= read -r d; do [ -n "$d" ] && printf '%s/d3dcompiler_47.dll\n' "${d#"$WINEPREFIX"/}"; done < <(_mig_tv_dirs))"

mig_needed() {
    local d
    while IFS= read -r d; do
        [ -n "$d" ] || continue
        _mig_tv_seed_needed "$d" && return 0
        _mig_tv_dll_needed "$d" && return 0
    done < <(_mig_tv_dirs)
    return 1
}

mig_apply() {
    local d key n tmp reg
    local -a seeds=()
    while IFS= read -r d; do
        [ -n "$d" ] && _mig_tv_seed_needed "$d" && seeds+=("$d")
    done < <(_mig_tv_dirs)
    if [ ${#seeds[@]} -gt 0 ] && ! command -v "${INV_HIVEXREGEDIT:-hivexregedit}" >/dev/null; then
        warn "hivexregedit not found (package hivex): DWG TrueView's registry seed put off"
        return "$MIG_DEFER"
    fi
    wine_stop
    # not local: the EXIT trap runs after the function has returned
    _mig_tv_tmp="$(mktemp -d)"; trap 'rm -rf "$_mig_tv_tmp"' EXIT; tmp="$_mig_tv_tmp"
    for d in "${seeds[@]}"; do
        key="$(_mig_tv_key "$d")"
        # an export that fails (hive unreadable, hivex's Perl module missing)
        # is a reason outside the prefix too: put off, not failed
        "${INV_HIVEXREGEDIT:-hivexregedit}" --export "$d/UserDataCache/User.dat" '\' > "$tmp/export.reg" \
            || { warn "hivexregedit could not export $d/UserDataCache/User.dat: DWG TrueView's registry seed put off"; return "$MIG_DEFER"; }
        n="$(python3 -I "$COMMON_DIR/trueview-seed.py" "$tmp/export.reg" "$USER" "$tmp/seed.reg" "$key")"
        # the hive does not hold the key the ini names: not this step's seed,
        # leave the install alone rather than fail every start
        [ "$n" != "0" ] || { warn "$(basename "$d"): UserDataCache\\User.dat has no CurVer under $key - seed not imported"; continue; }
        import_reg_file "$tmp/seed.reg"
        wine_stop
        [ -n "$(mig_reg_get "$key" CurVer)" ] || { err "$key has no CurVer after the import"; return 1; }
        info "    $(basename "$d"): $n keys under HKCU from UserDataCache\\User.dat"
    done
    while IFS= read -r d; do
        [ -n "$d" ] && _mig_tv_dll_needed "$d" || continue
        cp -f -- "$d/d3dcompiler_v2/d3dcompiler_47.dll" "$d/d3dcompiler_47.dll"
        [ -f "$d/d3dcompiler_47.dll" ] || { err "$d/d3dcompiler_47.dll was not copied"; return 1; }
        info "    $(basename "$d"): d3dcompiler_47.dll next to dwgviewr.exe (from d3dcompiler_v2)"
    done < <(_mig_tv_dirs)
}
