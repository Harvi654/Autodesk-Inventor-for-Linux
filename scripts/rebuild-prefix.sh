#!/bin/bash
# Build the Inventor Wine prefix from a mounted Windows installation.
#
# Usage: bash scripts/rebuild-prefix.sh [--yes] [--content-center] [--data-dir PATH] [--no-sandbox]
#   --yes              don't ask before deleting an existing prefix
#   --content-center   also copy Content Center libraries (~7 GB)
#   --data-dir PATH    your Inventor files, mapped as D: (default: ~/Inventor)
#   --no-sandbox       keep Wine's defaults (Z: = /, Documents etc. linked to $HOME)
#
# Component versions (Shared Components, AdskLicensing, Identity Manager) are
# detected from the Windows installation instead of being hard-coded.
# Run scripts/check-system.sh first - it shows what will be used.

set -Eeuo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"
trap 'err "failed at line $LINENO: $BASH_COMMAND (see $LOGDIR/setup-wine.log)"' ERR

ASSUME_YES=0; WITH_CC=0
while [ $# -gt 0 ]; do
    case "$1" in
        --yes|-y) ASSUME_YES=1 ;;
        --content-center) WITH_CC=1 ;;
        --data-dir) INV_DATA_DIR="$2"; shift ;;
        --no-sandbox) INV_SANDBOX=0 ;;
        *) die "unknown option: $1" ;;
    esac
    shift
done

WEBVIEW2_URL="https://go.microsoft.com/fwlink/?linkid=2124701"   # Evergreen Standalone x64
WEBVIEW2_INSTALLER="${WEBVIEW2_INSTALLER:-$DOWNLOAD_DIR/MicrosoftEdgeWebView2RuntimeInstallerX64.exe}"
: > "$LOGDIR/setup-wine.log"
_STEPS=23

# rsync wrapper: archive mode, no ownership/permissions from NTFS
copy() { rsync -rlt --info=progress2 --no-inc-recursive "$@"; }

# -----------------------------------------------------------------------------
step "Preflight checks..."
for c in wine wineserver winetricks rsync curl sha256sum; do
    command -v "$c" >/dev/null || die "$c not found - run scripts/phase0-setup.sh"
done
[ -f "$WIN_INV/Bin/Inventor.exe" ] || die "Inventor not found at $WIN_INV (is $WIN_ROOT mounted?)"
detect_source_versions
WU="$(detect_win_user)"
[ -n "$ASC_VER" ] || die "Shared Components version not found in $WIN_ASC_BASE"
[ -n "$LIC_VER" ] || die "AdskLicensing version not found in $WIN_LIC_BASE"
[ -n "$WU" ]      || die "no Windows user profile found in $WIN_ROOT/Users (set WIN_USER=...)"
INV_CLIENT_VER="$(reg_value "Inventor\\RegistryVersion$INV_REGMAJOR.0" ClientVersion)"
mapfile -t IDMGR_VERS < <(reg_idmgr_versions)
info "Wine $(wine_version) | prefix $WINEPREFIX"
info "Windows user: $WU | Components $ASC_VER | Licensing $LIC_VER"
info "Inventor ClientVersion (registry): ${INV_CLIENT_VER:-<none - will use Inventor.exe FileVersion>}"
# Fallback: the version folders that actually exist on Windows (not the
# original author's 1.16.5.1/1.14.0.3, which don't exist on newer installs)
if [ ${#IDMGR_VERS[@]} -eq 0 ]; then
    mapfile -t IDMGR_VERS < <(find "$WIN_IDMGR_BASE" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null \
        | grep -E '^[0-9]+(\.[0-9]+)+$' | sort -V)
fi
info "IdentityManager versions: ${IDMGR_VERS[*]:-<none>}"
[ -f "$REG_FILE" ] || warn "no registry export - run scripts/export-registry.sh first for a complete setup"
INV_CLIENT_VER="${INV_CLIENT_VER:-$(inv_file_version "$WIN_INV/Bin/Inventor.exe")}"
INV_CLIENT_VER="${INV_CLIENT_VER:-30.0.17500.0000}"
FREE_GB=$(df -BG --output=avail "$HOME" | tail -1 | tr -dc 0-9)
[ "$FREE_GB" -ge 25 ] || die "only ${FREE_GB} GB free in \$HOME, need ~25 GB"

# -----------------------------------------------------------------------------
step "Creating fresh prefix..."
if [ -d "$WINEPREFIX" ]; then
    if [ "$ASSUME_YES" -ne 1 ]; then
        read -r -p "    Delete existing prefix $WINEPREFIX? [y/N] " a
        [[ "$a" =~ ^[Yy]$ ]] || die "aborted"
    fi
    wine_stop
    rm -rf -- "$WINEPREFIX"
fi
wine_q wineboot --init
wine_stop
ok "prefix created"

step "Windows 10 mode, X11 (XWayland) graphics driver..."
winetricks -q win10 >>"$LOGDIR/setup-wine.log" 2>&1
# Pin the X11 driver: under Hyprland it runs via XWayland. Wine's native
# Wayland driver is not tested with Inventor yet.
wine_reg_add 'HKCU\Software\Wine\Drivers' /v Graphics /t REG_SZ /d x11

step "Installing DXVK ($([ "$INV_DXVK" = system ] && echo "system setup_dxvk" || echo "$DXVK_VER, pinned"))..."
install_dxvk

step "Starting WebView2 install in the background..."
if [ ! -f "$WEBVIEW2_INSTALLER" ]; then
    mkdir -p "$(dirname "$WEBVIEW2_INSTALLER")"
    info "downloading WebView2 runtime installer..."
    curl -fL --retry 3 -o "$WEBVIEW2_INSTALLER" "$WEBVIEW2_URL" \
        || { rm -f "$WEBVIEW2_INSTALLER"; die "download failed - put the installer at $WEBVIEW2_INSTALLER"; }
fi
wine "$(to_wine_temp "$WEBVIEW2_INSTALLER")" /silent /install >>"$LOGDIR/webview2.log" 2>&1 &
WEBVIEW2_PID=$!

# -----------------------------------------------------------------------------
step "Copying Inventor $INV_YEAR (Bin, Configuration, Preferences)..."
mkdir -p "$P_INV"
copy --exclude='Anark' "$WIN_INV/Bin/" "$P_INV/Bin/"
for d in Configuration Preferences; do
    [ -d "$WIN_INV/$d" ] && copy "$WIN_INV/$d" "$P_INV/"
done

step "Copying Shared Components $ASC_VER..."
mkdir -p "$(dirname "$P_ASC_BASE")"
copy "$WIN_ASC_BASE" "$(dirname "$P_ASC_BASE")/"
for dll in "$WIN_ASC_BASE/$ASC_VER/"*.dll; do
    [ -f "$P_INV/Bin/$(basename "$dll")" ] || cp "$dll" "$P_INV/Bin/"
done

step "Copying MSVC/MFC runtimes..."
for dll in msvcp140.dll msvcp140_1.dll msvcp140_2.dll vcruntime140.dll vcruntime140_1.dll \
           concrt140.dll vcomp140.dll mfc140u.dll mfc140.dll; do
    if [ -f "$WIN_ROOT/Windows/System32/$dll" ]; then cp "$WIN_ROOT/Windows/System32/$dll" "$P_C/windows/system32/"
    else warn "$dll not found on Windows"; fi
done

step "Copying RealDWG and user settings..."
RDWG="Program Files/Common Files/Autodesk Shared/RealDWG Shared $INV_YEAR"
if [ -d "$WIN_ROOT/$RDWG" ]; then mkdir -p "$P_C/$RDWG"; copy "$WIN_ROOT/$RDWG/" "$P_C/$RDWG/"; else warn "RealDWG not found"; fi
WIN_APPDATA_INV="$WIN_ROOT/Users/$WU/AppData/Roaming/Autodesk/Inventor $INV_YEAR"
mkdir -p "$P_USER/AppData/Roaming/Autodesk/Inventor $INV_YEAR"
[ -f "$WIN_APPDATA_INV/RealDWGSettings.xml" ] \
    && cp "$WIN_APPDATA_INV/RealDWGSettings.xml" "$P_USER/AppData/Roaming/Autodesk/Inventor $INV_YEAR/" \
    || warn "RealDWGSettings.xml not found for user $WU"
# Shared material libraries (location varies between releases; copy what exists)
for m in "Program Files (x86)/Common Files/Autodesk Shared/Materials" \
         "Program Files/Common Files/Autodesk Shared/Materials"; do
    [ -d "$WIN_ROOT/$m" ] && { mkdir -p "$P_C/$m"; copy "$WIN_ROOT/$m/" "$P_C/$m/"; info "copied $m"; }
done

step "Copying Identity Manager..."
mkdir -p "$P_IDMGR_BASE"
copy "$WIN_IDMGR_BASE/" "$P_IDMGR_BASE/"
for v in "${IDMGR_VERS[@]}"; do
    [ -d "$P_IDMGR_BASE/$v" ] || cp -a "$P_IDMGR_BASE/Current" "$P_IDMGR_BASE/$v"
done

step "Copying Licensing $LIC_VER and license cache..."
mkdir -p "$P_LIC_BASE"
# Whole folder: newer installs have Current/CurrentSDK as NTFS junctions, which
# ntfs3 shows as RELATIVE symlinks - they stay valid inside drive_c.
copy --exclude='uninstall.exe' "$WIN_LIC_BASE/" "$P_LIC_BASE/"
for l in "$P_LIC_BASE"/* "$P_IDMGR_BASE"/*; do
    if [ -L "$l" ] && [ ! -e "$l" ]; then warn "broken link after copy: $l -> $(readlink "$l")"; fi
done
mkdir -p "$P_C/ProgramData/Autodesk/Adlm/ASR" "$P_C/ProgramData/Autodesk/AdskLicensingService"
shopt -s nullglob
for f in "$WIN_PROGDATA/Adlm/ASR/"*.asr; do cp "$f" "$P_C/ProgramData/Autodesk/Adlm/ASR/"; done
shopt -u nullglob
for f in Adlm/ProductInformation.pit AdskLicensingService/AdskLicensingService.data \
         AdskLicensingService/AdskLicensingService.sds; do
    [ -f "$WIN_PROGDATA/$f" ] && cp "$WIN_PROGDATA/$f" "$P_C/ProgramData/Autodesk/$f" || info "(no $f)"
done

step "Copying .NET runtime..."
if [ -d "$WIN_ROOT/Program Files/dotnet" ]; then
    copy "$WIN_ROOT/Program Files/dotnet" "$P_C/Program Files/"
    ok ".NET $(ls "$P_C/Program Files/dotnet/shared/Microsoft.NETCore.App" | tr '\n' ' ')"
else
    warn ".NET not found on Windows - Inventor add-ins will not load"
fi

# -----------------------------------------------------------------------------
step "Importing registry..."
if [ -f "$REG_FILE" ]; then
    # Full export from Windows first; the explicit keys below then fix paths/versions.
    import_reg_file "$REG_FILE"
    ok "imported $(basename "$REG_FILE") (as UTF-16)"
fi
K="HKLM\\SOFTWARE\\Autodesk\\Inventor\\RegistryVersion$INV_REGMAJOR.0"
wine_reg_add "$K" /v ProductVersionMajor /t REG_DWORD /d "$INV_REGMAJOR"
wine_reg_add "$K" /v BinPath /t REG_SZ /d "C:\\Program Files\\Autodesk\\Inventor $INV_YEAR\\Bin\\"
wine_reg_add "$K" /v AppPath /t REG_SZ /d "C:\\Program Files\\Autodesk\\Inventor $INV_YEAR\\"
wine_reg_add "$K" /v ClientVersion /t REG_SZ /d "$INV_CLIENT_VER"
wine_reg_add "$K" /v ProductEdition /t REG_SZ /d "INVPROSA"
wine_reg_add "HKLM\\SOFTWARE\\Autodesk\\SharedComponents\\$INV_YEAR" /v InstallPath /t REG_EXPAND_SZ \
    /d "C:\\Program Files\\Common Files\\Autodesk Shared\\Components\\$INV_YEAR"
wine_reg_add "HKLM\\SOFTWARE\\Autodesk\\SharedComponents\\$INV_YEAR" /v Version /t REG_EXPAND_SZ /d "$ASC_VER"
wine_reg_add 'HKLM\SOFTWARE\Autodesk\AdskLicensing' /v Version /t REG_EXPAND_SZ /d "$LIC_VER"
for v in "${IDMGR_VERS[@]}"; do
    wine_reg_add "HKLM\\SOFTWARE\\Autodesk\\AdskIdentityManager\\$v" /v Location /t REG_EXPAND_SZ \
        /d "C:\\Program Files\\Autodesk\\AdskIdentityManager\\$v"
done
IDMGR_EXE='C:\Program Files\Autodesk\AdskIdentityManager\Current\AdskIdentityManager.exe'
wine_reg_add 'HKCR\adskidmgr' /ve /t REG_SZ /d "URL:Autodesk Identity Manager Protocol"
wine_reg_add 'HKCR\adskidmgr' /v "URL Protocol" /t REG_SZ /d ""
wine_reg_add 'HKCR\adskidmgr\shell\open\command' /ve /t REG_SZ /d "\"$IDMGR_EXE\" \"%1\""
wine_reg_add 'HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment' /v Path /t REG_EXPAND_SZ \
    /d "C:\\windows\\system32;C:\\windows;C:\\windows\\system32\\wbem;C:\\Program Files\\Common Files\\Autodesk Shared\\Components\\$INV_YEAR\\$ASC_VER;C:\\Program Files\\Autodesk\\Inventor $INV_YEAR\\Bin"
ok "registry keys set"

step "Installing IdSDK SSO plugin into the Licensing Agent..."
AGENTDIR="$P_LIC_BASE/$LIC_VER/AdskLicensingAgent"
AGENT_WIN="C:\\\\Program Files (x86)\\\\Common Files\\\\Autodesk Shared\\\\AdskLicensing\\\\$LIC_VER\\\\AdskLicensingAgent\\\\SSOPlugin\\\\Current"
mkdir -p "$AGENTDIR/SSOPlugin/Current"
for f in "$P_IDMGR_BASE/Current/SSOPlugin/Current/"*.dll; do
    [ -e "$AGENTDIR/SSOPlugin/Current/$(basename "$f")" ] || cp "$f" "$AGENTDIR/SSOPlugin/Current/"
done
if [ -f "$AGENTDIR/IDSDKVersionCompatibility.config" ]; then
    info "Licensing Agent already ships IDSDKVersionCompatibility.config - keeping Autodesk's file"
else
    cat > "$AGENTDIR/IDSDKVersionCompatibility.config" <<EOF
{
    "comment": "Version compatibility file",
    "ssoClientPlugin": [
        {
            "version": "0",
            "module": "IdSDKPlugin.dll",
            "modulePath": "$AGENT_WIN",
            "modulePathWoW64": "$AGENT_WIN",
            "compatibleSsoServicesVersion": { "minVersion": "0.0" }
        }
    ]
}
EOF
    ok "created IDSDKVersionCompatibility.config (original project's workaround)"
fi

# -----------------------------------------------------------------------------
step "Disabling non-essential and Wine-broken add-ins (see notes/disabled-addins.md)..."
ADDINS="$P_INV/Bin/Addins"
mkdir -p "$P_ADDINS_OFF/libs"
for f in "${INV_DEFAULT_DISABLED_ADDINS[@]}"; do
    if [ -f "$ADDINS/$f" ]; then mv "$ADDINS/$f" "$P_ADDINS_OFF/"; else info "(not present: $f)"; fi
done

step "Removing known crash sources (InteractiveTutorial, CER reporter, bcp47langs)..."
for f in "$P_INV/Bin/InteractiveTutorial.dll" "$P_INV/Bin/en-US/InteractiveTutorial.resources.dll"; do
    [ -f "$f" ] && mv "$f" "$P_ADDINS_OFF/libs/"
done
[ -f "$P_INV/Bin/CER/senddmp.exe" ] && mv "$P_INV/Bin/CER/senddmp.exe" "$P_INV/Bin/CER/senddmp.exe.disabled"
for f in "$P_C/windows/system32/bcp47langs.dll" "$P_C/windows/syswow64/bcp47langs.dll"; do
    [ -f "$f" ] && mv "$f" "$f.disabled"
done
wine_q reg delete 'HKCU\Software\Wine\DllOverrides' /v bcp47langs /f || true

step "Removing wine-mono WPF stub assemblies (README: Key Discovery #1)..."
# Delete only the DLL files, not the GAC directories.
WPF_RE='/(PresentationCore|PresentationFramework|WindowsBase|System\.Xaml)\.dll$'
mapfile -t WPF_LOCAL < <(find "$P_C/windows" -path '*gac*' -name '*.dll' 2>/dev/null | grep -E "$WPF_RE" || true)
if [ ${#WPF_LOCAL[@]} -gt 0 ]; then
    rm -f -- "${WPF_LOCAL[@]}"
    ok "removed ${#WPF_LOCAL[@]} stub DLL(s) from the prefix"
else
    mapfile -t WPF_SYS < <(find /usr/share/wine/mono -path '*gac*' -name '*.dll' 2>/dev/null | grep -E "$WPF_RE" || true)
    if [ ${#WPF_SYS[@]} -gt 0 ]; then
        warn "wine-mono is the shared system install (/usr/share/wine/mono); its WPF stubs are still there."
        warn "This is the case the original setup did not cover - test Inventor first; if it exits"
        warn "right after loading .NET add-ins, see docs/arch-hyprland.md (wine-mono section)."
    else
        info "no WPF stub assemblies found"
    fi
fi

step "Copying public Inventor documents (Design Data, Templates, Default.ipj, ...)..."
# The whole folder, not a list of subfolders: Default.ipj lives at its top level
# and without an active project Inventor loads no material/appearance libraries
# (empty lists, unlit flat-grey parts, iLogic E_FAIL on get_ActiveDesignProject).
mkdir -p "$P_PUBDOCS"
[ -d "$WIN_PUBDOCS" ] || die "not found: $WIN_PUBDOCS"
copy "$WIN_PUBDOCS/" "$P_PUBDOCS/"
for d in "Design Data" Templates; do
    [ -d "$P_PUBDOCS/$d" ] || warn "$d not found"
done
[ -f "$P_PUBDOCS/Default.ipj" ] && ok "Default.ipj" || warn "Default.ipj not found - create a project in Inventor (Get Started > Projects)"

step "Copying ProgramData\\Autodesk\\Inventor $INV_YEAR (App Home page in WebBrowser\\, ...)..."
# The App Home page is file:///C:/ProgramData/Autodesk/Inventor <year>/WebBrowser/index.html;
# without it the Home tab shows ERR_FILE_NOT_FOUND. Content Center (~7 GB) only on request.
WIN_INVDATA="$WIN_PROGDATA/Inventor $INV_YEAR"
mkdir -p "$P_C/ProgramData/Autodesk/Inventor $INV_YEAR"
if [ -d "$WIN_INVDATA" ]; then
    if [ "$WITH_CC" -eq 1 ]; then
        copy "$WIN_INVDATA/" "$P_C/ProgramData/Autodesk/Inventor $INV_YEAR/"
    else
        copy --exclude='/Content Center/' "$WIN_INVDATA/" "$P_C/ProgramData/Autodesk/Inventor $INV_YEAR/"
        info "Content Center skipped (use --content-center to copy ~7 GB)"
    fi
    [ -f "$P_C/ProgramData/Autodesk/Inventor $INV_YEAR/WebBrowser/index.html" ] && ok "App Home page" \
        || warn "WebBrowser/index.html not found - the Home tab will stay empty"
else
    warn "not found: $WIN_INVDATA"
fi

# -----------------------------------------------------------------------------
step "Patching OGSFactory.dll (null-pointer guard for the 3D viewport)..."
if [ "${INV_OGS_PATCH:-1}" = 1 ]; then
    bash "$SCRIPTS_DIR/ogs-patch.sh" apply || warn "OGSFactory.dll not patched - please report its sha256 in an issue"
else
    info "skipped (INV_OGS_PATCH=0) - experiment: does Inventor work unpatched with the wbemprox patch?"
fi

step "Waiting for the WebView2 installer..."
for _ in $(seq 1 180); do kill -0 "$WEBVIEW2_PID" 2>/dev/null || break; sleep 1; done
if kill -0 "$WEBVIEW2_PID" 2>/dev/null; then warn "WebView2 installer still running after 3 min - leaving it"; else ok "done"; fi
rm -f "$P_C/windows/temp/$(basename "$WEBVIEW2_INSTALLER")"
webview2_reg
ok "WebView2 set up for Wine (Windows 7 + wined3d for msedgewebview2.exe, policy switches)"

step "Inventor file types (icons, thumbnail/property shell extensions)..."
bash "$SCRIPTS_DIR/import-file-types.sh" || warn "file types not imported - dialogs show the old 'I' icon"

step "Windows fonts (WPF needs Segoe UI/Arial/Tahoma)..."
# After the WebView2 wait: windows-fonts.sh stops wineserver to import the registry.
bash "$SCRIPTS_DIR/windows-fonts.sh" || warn "Windows fonts not copied - WPF may FailFast in TypefaceMap.MapUnresolvedCharacters"

step "Isolation (drives, home folders)..."
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
wine_stop
wine --version > "$WINEPREFIX/.inventor-wine-version"

echo
ok "Prefix ready: $WINEPREFIX ($(du -sh "$WINEPREFIX" | cut -f1))"
info "Next: bash scripts/install-desktop-integration.sh   (OAuth2 handler + app launcher entry)"
info "Then: bash scripts/launch-inventor.sh"
