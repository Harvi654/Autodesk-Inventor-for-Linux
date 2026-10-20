# shellcheck shell=bash
# Prefix configuration shared by rebuild-prefix.sh (copy from Windows) and
# finish-install.sh (after install-from-image.py). Source after common.sh.

# Windows 10, X11 driver. Under Hyprland the X11 driver runs via XWayland;
# Wine's native Wayland driver is not usable for Inventor yet (menus).
cfg_wine_mode() {
    wine_reg_add 'HKCU\Software\Wine' /v Version /t REG_SZ /d win10
    wine_reg_add 'HKCU\Software\Wine\Drivers' /v Graphics /t REG_SZ /d x11
}

# The Licensing Agent needs Identity Manager's IdSDK SSO plugin next to it.
cfg_sso_plugin() {
    local agentdir="$P_LIC_BASE/$LIC_VER/AdskLicensingAgent"
    local agent_win="C:\\\\Program Files (x86)\\\\Common Files\\\\Autodesk Shared\\\\AdskLicensing\\\\$LIC_VER\\\\AdskLicensingAgent\\\\SSOPlugin\\\\Current"
    local f
    [ -d "$agentdir" ] || { warn "no Licensing Agent in $agentdir"; return 0; }
    mkdir -p "$agentdir/SSOPlugin/Current"
    for f in "$P_IDMGR_BASE/Current/SSOPlugin/Current/"*.dll; do
        [ -e "$f" ] || continue
        [ -e "$agentdir/SSOPlugin/Current/$(basename "$f")" ] || cp "$f" "$agentdir/SSOPlugin/Current/"
    done
    if [ -f "$agentdir/IDSDKVersionCompatibility.config" ]; then
        info "Licensing Agent already ships IDSDKVersionCompatibility.config - keeping Autodesk's file"
    else
        cat > "$agentdir/IDSDKVersionCompatibility.config" <<EOF
{
    "comment": "Version compatibility file",
    "ssoClientPlugin": [
        {
            "version": "0",
            "module": "IdSDKPlugin.dll",
            "modulePath": "$agent_win",
            "modulePathWoW64": "$agent_win",
            "compatibleSsoServicesVersion": { "minVersion": "0.0" }
        }
    ]
}
EOF
        ok "created IDSDKVersionCompatibility.config (original project's workaround)"
    fi
}

# Add-ins that crash or are not needed (notes/disabled-addins.md), known
# crash sources, wine-mono's WPF stub assemblies.
cfg_disable_addins() {
    local f
    mkdir -p "$P_ADDINS_OFF/libs"
    for f in "${INV_DEFAULT_DISABLED_ADDINS[@]}"; do
        if [ -f "$P_ADDINS/$f" ]; then mv "$P_ADDINS/$f" "$P_ADDINS_OFF/"; else info "(not present: $f)"; fi
    done
}

cfg_crash_sources() {
    local f
    mkdir -p "$P_ADDINS_OFF/libs"
    for f in "$P_INV/Bin/InteractiveTutorial.dll" "$P_INV/Bin/en-US/InteractiveTutorial.resources.dll"; do
        [ -f "$f" ] && mv "$f" "$P_ADDINS_OFF/libs/"
    done
    [ -f "$P_INV/Bin/CER/senddmp.exe" ] && mv "$P_INV/Bin/CER/senddmp.exe" "$P_INV/Bin/CER/senddmp.exe.disabled"
    for f in "$P_C/windows/system32/bcp47langs.dll" "$P_C/windows/syswow64/bcp47langs.dll"; do
        [ -f "$f" ] && mv "$f" "$f.disabled"
    done
    wine_q reg delete 'HKCU\Software\Wine\DllOverrides' /v bcp47langs /f || true
}

cfg_wpf_stubs() {
    # Delete only the DLL files, not the GAC directories.
    local re='/(PresentationCore|PresentationFramework|WindowsBase|System\.Xaml)\.dll$'
    local -a local_stubs sys_stubs
    mapfile -t local_stubs < <(find "$P_C/windows" -path '*gac*' -name '*.dll' 2>/dev/null | grep -E "$re" || true)
    if [ ${#local_stubs[@]} -gt 0 ]; then
        rm -f -- "${local_stubs[@]}"
        ok "removed ${#local_stubs[@]} stub DLL(s) from the prefix"
    else
        mapfile -t sys_stubs < <(find /usr/share/wine/mono -path '*gac*' -name '*.dll' 2>/dev/null | grep -E "$re" || true)
        if [ ${#sys_stubs[@]} -gt 0 ]; then
            # Inventor 2026 brings its own .NET 8/10 with WPF; a clean install
            # from Autodesk's image runs fine next to the system wine-mono.
            info "system wine-mono has WPF stubs - not used by Inventor 2026 (.NET 8+), fine"
        else
            info "no WPF stub assemblies found"
        fi
    fi
}

# Drives and home folders (see sandbox_fs / sandbox_reg in common.sh).
cfg_isolation() {
    if [ "$INV_SANDBOX" = 1 ]; then
        sandbox_reg
        wine_stop
        sandbox_fs
        ok "drives: $(cd "$WINEPREFIX/dosdevices" && ls -d ?: 2>/dev/null | while read -r d; do printf '%s->%s ' "$d" "$(readlink "$d")"; done)"
        info "your Inventor files go to: ${INV_DATA_DIR:-<none, set INV_DATA_DIR>} (D:)"
    else
        [ -n "$INV_DATA_DIR" ] && { mkdir -p "$INV_DATA_DIR"; ln -sfn "$INV_DATA_DIR" "$WINEPREFIX/dosdevices/d:"; }
        info "sandbox disabled - Wine defaults (Z: = /)"
    fi
}

# Autodesk installers create "Current" as an NTFS junction pointing at the
# newest version folder. Under Wine such a junction ends up as an empty
# "Current?" directory that Linux tools can't follow (and our scripts use
# Current). Replace it with a plain relative symlink, as an NTFS mount shows
# it. $1 = folder with version subfolders, $2 = link name, $3 = optional
# path below the version folder.
cfg_current_link() {
    local base="$1" name="$2" sub="${3:-}" ver junk
    [ -d "$base" ] || return 0
    [ -e "$base/$name" ] && [ ! -d "$base/$name?" ] && return 0
    ver="$(latest_version_dir "$base")"
    [ -n "$ver" ] || return 0
    for junk in "$base/$name" "$base/$name?"; do
        if [ -L "$junk" ] || [ -f "$junk" ]; then rm -f -- "$junk"
        elif [ -d "$junk" ]; then rmdir -- "$junk" 2>/dev/null || { warn "$junk is not empty - left alone"; return 0; }
        fi
    done
    [ -d "$base/$ver${sub:+/$sub}" ] || return 0
    ln -s "$ver${sub:+/$sub}" "$base/$name"
    ok "$(basename "$base")/$name -> $ver${sub:+/$sub}"
}
