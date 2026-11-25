# shellcheck shell=bash
# Step 0001: the prefix setup finish-install.sh did until migrations existed,
# unchanged (moved here from finish-install.sh). finish-install.sh runs it
# again on every call; existing prefixes are recorded as having it.
# It is never edited: a change to the prefix is a new step.
MIG_DESC="base setup: links, Windows 10, DXVK, vkd3d-proton, registry, add-ins, RealDWG, WebView2, fonts, isolation"
# installation time: nothing to save (and too much to save: DXVK, fonts, ...)
MIG_BACKUP=none

mig_apply() {
    step "Current links (Wine leaves Autodesk's junctions as unusable 'Current?' folders)..."
    cfg_current_link "$P_LIC_BASE" Current
    cfg_current_link "$P_LIC_BASE" CurrentSDK AdskLicensingSDK
    cfg_current_link "$P_IDMGR_BASE" Current
    detect_prefix_versions
    [ -n "$LIC_VER" ] || die "AdskLicensing not found in $P_LIC_BASE"
    [ -n "$ASC_VER" ] || die "Shared Components not found in $P_ASC_BASE"
    info "Licensing $LIC_VER | Shared Components $ASC_VER | Identity Manager $(latest_version_dir "$P_IDMGR_BASE")"

    step "Windows 10 mode, X11 (XWayland) graphics driver..."
    cfg_wine_mode

    step "Installing DXVK ($([ "$INV_DXVK" = system ] && echo "system setup_dxvk" || echo "$DXVK_VER, pinned")) and vkd3d-proton ($([ "$INV_VKD3D" = off ] && echo off || echo "$VKD3D_VER, pinned"))..."
    install_dxvk
    install_vkd3d

    step "Registry: Shared Components, search path, adskidmgr:// handler..."
    # The Shared Components were unpacked by us, not by Autodesk's installer -
    # ASCRegistryTool writes most of this, these make sure the essentials are there.
    wine_reg_add "HKLM\\SOFTWARE\\Autodesk\\SharedComponents\\$INV_YEAR" /v InstallPath /t REG_EXPAND_SZ \
        /d "C:\\Program Files\\Common Files\\Autodesk Shared\\Components\\$INV_YEAR"
    wine_reg_add "HKLM\\SOFTWARE\\Autodesk\\SharedComponents\\$INV_YEAR" /v Version /t REG_EXPAND_SZ /d "$ASC_VER"
    wine_reg_add 'HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment' /v Path /t REG_EXPAND_SZ \
        /d "C:\\windows\\system32;C:\\windows;C:\\windows\\system32\\wbem;C:\\Program Files\\Common Files\\Autodesk Shared\\Components\\$INV_YEAR\\$ASC_VER;C:\\Program Files\\Autodesk\\Inventor $INV_YEAR\\Bin"
    IDMGR_EXE='C:\Program Files\Autodesk\AdskIdentityManager\Current\AdskIdentityManager.exe'
    wine_reg_add 'HKCR\adskidmgr' /ve /t REG_SZ /d "URL:Autodesk Identity Manager Protocol"
    wine_reg_add 'HKCR\adskidmgr' /v "URL Protocol" /t REG_SZ /d ""
    wine_reg_add 'HKCR\adskidmgr\shell\open\command' /ve /t REG_SZ /d "\"$IDMGR_EXE\" \"%1\""
    ok "registry keys set"

    step "Licensing service: manual start (launch-inventor.sh runs it as a process)..."
    # Under Wine it never reports "running" as a Windows service (1053/1077);
    # left on automatic start, Wine would try - and time out - on every boot.
    # (Wine's sc.exe has no "config" command - set the start type directly: 3 = demand)
    wine_reg_add 'HKLM\SYSTEM\CurrentControlSet\Services\AdskLicensingService' /v Start /t REG_DWORD /d 3 \
        && ok "AdskLicensingService: manual start" || warn "could not change the service start type"

    step "Installing IdSDK SSO plugin into the Licensing Agent..."
    cfg_sso_plugin

    step "Disabling non-essential and Wine-broken add-ins, known crash sources..."
    cfg_disable_addins
    cfg_crash_sources
    cfg_wpf_stubs

    step "RealDWG settings (Inventor's access to AutoCAD files)..."
    # Without it Inventor stops at the splash screen: "Failed to initialize a
    # component for accessing AutoCAD files. Error 82". On Windows the file is
    # in the user profile; Inventor normally writes it itself (a copy of what a
    # working Windows install has - UTF-16 with BOM, CRLF).
    RDWG_DIR="C:\\Program Files\\Common Files\\Autodesk Shared\\RealDWG Shared $INV_YEAR"
    RDWG_XML="$P_USER/AppData/Roaming/Autodesk/Inventor $INV_YEAR/RealDWGSettings.xml"
    if [ -d "$P_C/Program Files/Common Files/Autodesk Shared/RealDWG Shared $INV_YEAR" ]; then
        mkdir -p "$(dirname "$RDWG_XML")"
        if [ ! -f "$RDWG_XML" ]; then
            { printf '\xff\xfe'; printf '<?xml version="1.0" encoding="utf-16" standalone="no" ?>\r\n<RealDWGSettings InstallDirectory="%s"></RealDWGSettings>\r\n' \
                "$RDWG_DIR" | iconv -f UTF-8 -t UTF-16LE; } > "$RDWG_XML"
        fi
        ok "RealDWGSettings.xml -> $RDWG_DIR"
    else
        warn "RealDWG Shared $INV_YEAR not installed - DWG import/export will not work"
    fi

    step "Checking project and Home page files..."
    [ -f "$P_PUBDOCS/Default.ipj" ] && ok "Default.ipj" \
        || warn "Default.ipj not found in $P_PUBDOCS - create a project in Inventor (Get Started > Projects)"
    [ -f "$P_C/ProgramData/Autodesk/Inventor $INV_YEAR/WebBrowser/index.html" ] && ok "App Home page" \
        || warn "WebBrowser/index.html not found - the Home tab will stay empty"

    step "WebView2 for Wine (Windows 7 + wined3d for msedgewebview2.exe, policy switches)..."
    webview2_reg
    ok "done"

    step "Fonts (WPF needs fonts for Segoe UI/Arial/Tahoma)..."
    if [ "${INV_FONTS:-linux}" = windows ]; then
        bash "$SCRIPTS_DIR/windows-fonts.sh" || warn "Windows fonts not copied - WPF may FailFast in TypefaceMap.MapUnresolvedCharacters"
    else
        bash "$SCRIPTS_DIR/linux-fonts.sh" || warn "fonts not set up - WPF may FailFast in TypefaceMap.MapUnresolvedCharacters"
    fi

    step "Isolation (drives, home folders)..."
    wine_stop
    rm -f "$WINEPREFIX/dosdevices/m:"   # the install image drive
    cfg_isolation
    wine_stop
    wine --version > "$WINEPREFIX/.inventor-wine-version"

}
