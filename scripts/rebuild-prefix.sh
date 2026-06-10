#!/bin/bash
set -e
export WINEPREFIX="$HOME/.wine-inventor2026"
export WINEARCH=win64

echo "=== Rebuilding Inventor 2026 Wine Prefix ==="

# Kill existing
wineserver -k 2>/dev/null; sleep 3
rm -rf "$WINEPREFIX"
echo "[1/20] Creating fresh prefix..."
wineboot --init 2>/dev/null
sleep 3

echo "[2/20] Setting Windows 10..."
winetricks -q win10 2>/dev/null

echo "[3/20] Installing DXVK..."
setup_dxvk install 2>/dev/null
wine reg add "HKCU\\Software\\Wine\\DllOverrides" /v d3d11 /t REG_SZ /d native /f 2>/dev/null
wine reg add "HKCU\\Software\\Wine\\DllOverrides" /v dxgi /t REG_SZ /d native /f 2>/dev/null
wine reg add "HKCU\\Software\\Wine\\DllOverrides" /v d3dcompiler_47 /t REG_SZ /d native /f 2>/dev/null

echo "[4/20] Copying Inventor files..."
DEST="$WINEPREFIX/drive_c/Program Files/Autodesk/Inventor 2026"
mkdir -p "$DEST"
rsync -a --exclude='Anark' "/mnt/windows/Program Files/Autodesk/Inventor 2026/Bin/" "$DEST/Bin/"
cp -a "/mnt/windows/Program Files/Autodesk/Inventor 2026/Configuration" "$DEST/"
cp -a "/mnt/windows/Program Files/Autodesk/Inventor 2026/Preferences" "$DEST/"

echo "[5/20] Copying ASC SharedComponents into Bin..."
for dll in "/mnt/windows/Program Files/Common Files/Autodesk Shared/Components/2026/1.8.0/"*.dll; do
    base=$(basename "$dll")
    [ ! -f "$DEST/Bin/$base" ] && cp "$dll" "$DEST/Bin/"
done
mkdir -p "$WINEPREFIX/drive_c/Program Files/Common Files/Autodesk Shared"
cp -a "/mnt/windows/Program Files/Common Files/Autodesk Shared/Components" \
   "$WINEPREFIX/drive_c/Program Files/Common Files/Autodesk Shared/"

echo "[6/20] Copying MSVC/MFC runtimes..."
for dll in msvcp140.dll msvcp140_1.dll msvcp140_2.dll vcruntime140.dll vcruntime140_1.dll concrt140.dll vcomp140.dll mfc140u.dll mfc140.dll; do
    cp "/mnt/windows/Windows/System32/$dll" "$WINEPREFIX/drive_c/windows/system32/" 2>/dev/null
done

echo "[7/20] Copying RealDWG..."
mkdir -p "$WINEPREFIX/drive_c/Program Files/Common Files/Autodesk Shared/RealDWG Shared 2026"
cp -a "/mnt/windows/Program Files/Common Files/Autodesk Shared/RealDWG Shared 2026/"* \
   "$WINEPREFIX/drive_c/Program Files/Common Files/Autodesk Shared/RealDWG Shared 2026/"

echo "[8/20] Copying RealDWGSettings.xml..."
mkdir -p "$WINEPREFIX/drive_c/users/$USER/AppData/Roaming/Autodesk/Inventor 2026"
cp "/mnt/windows/Users/$(ls /mnt/windows/Users/ | grep -vE '^(Public|Default|All Users)$' | head -1)/AppData/Roaming/Autodesk/Inventor 2026/RealDWGSettings.xml" \
   "$WINEPREFIX/drive_c/users/$USER/AppData/Roaming/Autodesk/Inventor 2026/"

echo "[9/20] Installing WebView2..."
wine /tmp/MicrosoftEdgeWebView2RuntimeInstallerX64.exe /silent /install 2>/dev/null &
sleep 30

echo "[10/20] Copying Identity Manager..."
mkdir -p "$WINEPREFIX/drive_c/Program Files/Autodesk/AdskIdentityManager"
cp -a "/mnt/windows/Program Files/Autodesk/AdskIdentityManager/Current" \
   "$WINEPREFIX/drive_c/Program Files/Autodesk/AdskIdentityManager/"
cp -a "$WINEPREFIX/drive_c/Program Files/Autodesk/AdskIdentityManager/Current" \
   "$WINEPREFIX/drive_c/Program Files/Autodesk/AdskIdentityManager/1.16.5.1"
cp -a "$WINEPREFIX/drive_c/Program Files/Autodesk/AdskIdentityManager/Current" \
   "$WINEPREFIX/drive_c/Program Files/Autodesk/AdskIdentityManager/1.14.0.3"

echo "[11/20] Copying Licensing Service..."
mkdir -p "$WINEPREFIX/drive_c/Program Files (x86)/Common Files/Autodesk Shared/AdskLicensing"
cp -a "/mnt/windows/Program Files (x86)/Common Files/Autodesk Shared/AdskLicensing/15.4.2.4" \
   "$WINEPREFIX/drive_c/Program Files (x86)/Common Files/Autodesk Shared/AdskLicensing/"

echo "[12/20] Copying license cache..."
mkdir -p "$WINEPREFIX/drive_c/ProgramData/Autodesk/Adlm/ASR"
mkdir -p "$WINEPREFIX/drive_c/ProgramData/Autodesk/AdskLicensingService"
cp "/mnt/windows/ProgramData/Autodesk/Adlm/ASR/INVPROSA202600F_"*.asr \
   "$WINEPREFIX/drive_c/ProgramData/Autodesk/Adlm/ASR/" 2>/dev/null
cp "/mnt/windows/ProgramData/Autodesk/Adlm/ProductInformation.pit" \
   "$WINEPREFIX/drive_c/ProgramData/Autodesk/Adlm/" 2>/dev/null
cp "/mnt/windows/ProgramData/Autodesk/AdskLicensingService/AdskLicensingService.data" \
   "$WINEPREFIX/drive_c/ProgramData/Autodesk/AdskLicensingService/" 2>/dev/null
cp "/mnt/windows/ProgramData/Autodesk/AdskLicensingService/AdskLicensingService.sds" \
   "$WINEPREFIX/drive_c/ProgramData/Autodesk/AdskLicensingService/" 2>/dev/null

echo "[13/20] Setting Inventor registry keys..."
wine reg add "HKLM\\SOFTWARE\\Autodesk\\Inventor\\RegistryVersion30.0" /v ProductVersionMajor /t REG_DWORD /d 30 /f 2>/dev/null
wine reg add "HKLM\\SOFTWARE\\Autodesk\\Inventor\\RegistryVersion30.0" /v BinPath /t REG_SZ /d "C:\\Program Files\\Autodesk\\Inventor 2026\\Bin\\" /f 2>/dev/null
wine reg add "HKLM\\SOFTWARE\\Autodesk\\Inventor\\RegistryVersion30.0" /v AppPath /t REG_SZ /d "C:\\Program Files\\Autodesk\\Inventor 2026\\" /f 2>/dev/null
wine reg add "HKLM\\SOFTWARE\\Autodesk\\Inventor\\RegistryVersion30.0" /v ClientVersion /t REG_SZ /d "30.0.17500.0000" /f 2>/dev/null
wine reg add "HKLM\\SOFTWARE\\Autodesk\\Inventor\\RegistryVersion30.0" /v ProductEdition /t REG_SZ /d "INVPROSA" /f 2>/dev/null

echo "[14/20] Setting SharedComponents registry..."
wine reg add "HKLM\\SOFTWARE\\Autodesk\\SharedComponents\\2026" /v InstallPath /t REG_EXPAND_SZ /d "C:\\Program Files\\Common Files\\Autodesk Shared\\Components\\2026" /f 2>/dev/null
wine reg add "HKLM\\SOFTWARE\\Autodesk\\SharedComponents\\2026" /v Version /t REG_EXPAND_SZ /d "1.8.0" /f 2>/dev/null

echo "[15/20] Setting licensing registry..."
wine reg add "HKLM\\SOFTWARE\\Autodesk\\AdskLicensing" /v Version /t REG_EXPAND_SZ /d "15.4.2.4" /f 2>/dev/null
wine reg add "HKLM\\SOFTWARE\\Autodesk\\AdskIdentityManager\\1.16.5.1" /v Location /t REG_EXPAND_SZ /d "C:\\Program Files\\Autodesk\\AdskIdentityManager\\1.16.5.1" /f 2>/dev/null
wine reg add "HKLM\\SOFTWARE\\Autodesk\\AdskIdentityManager\\1.14.0.3" /v Location /t REG_EXPAND_SZ /d "C:\\Program Files\\Autodesk\\AdskIdentityManager\\1.14.0.3" /f 2>/dev/null

echo "[16/20] Setting protocol handler registry..."
wine reg add "HKCR\\adskidmgr" /ve /t REG_SZ /d "URL:Autodesk Identity Manager Protocol" /f 2>/dev/null
wine reg add "HKCR\\adskidmgr" /v "URL Protocol" /t REG_SZ /d "" /f 2>/dev/null
wine reg add "HKCR\\adskidmgr\\shell\\open\\command" /ve /t REG_SZ /d "\"C:\\Program Files\\Autodesk\\AdskIdentityManager\\Current\\AdskIdentityManager.exe\" \"%1\"" /f 2>/dev/null

echo "[17/20] Setting PATH..."
wine reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment" /v Path /t REG_EXPAND_SZ /d "C:\\windows\\system32;C:\\windows;C:\\windows\\system32\\wbem;C:\\Program Files\\Common Files\\Autodesk Shared\\Components\\2026\\1.8.0;C:\\Program Files\\Autodesk\\Inventor 2026\\Bin" /f 2>/dev/null

echo "[18/20] CRITICAL: Copying IDSDK plugin to licensing agent..."
AGENTDIR="$WINEPREFIX/drive_c/Program Files (x86)/Common Files/Autodesk Shared/AdskLicensing/15.4.2.4/AdskLicensingAgent"
IDMGRDIR="$WINEPREFIX/drive_c/Program Files/Autodesk/AdskIdentityManager/Current"
mkdir -p "$AGENTDIR/SSOPlugin/Current"
cp "$IDMGRDIR/SSOPlugin/Current/"*.dll "$AGENTDIR/SSOPlugin/Current/"
cat > "$AGENTDIR/IDSDKVersionCompatibility.config" << 'VEOF'
{
    "comment": "Version compatibility file",
    "ssoClientPlugin": [
        {
            "version": "0",
            "module": "IdSDKPlugin.dll",
            "modulePath": "C:\\Program Files (x86)\\Common Files\\Autodesk Shared\\AdskLicensing\\15.4.2.4\\AdskLicensingAgent\\SSOPlugin\\Current",
            "modulePathWoW64": "C:\\Program Files (x86)\\Common Files\\Autodesk Shared\\AdskLicensing\\15.4.2.4\\AdskLicensingAgent\\SSOPlugin\\Current",
            "compatibleSsoServicesVersion": {
                "minVersion": "0.0"
            }
        }
    ]
}
VEOF

echo "[19/28] Disabling non-essential addins..."
ADDINS="$DEST/Bin/Addins"
mkdir -p "$ADDINS/disabled/libs"
for f in Anark.Core.addin Autodesk.Feedback.Inventor.addin Autodesk.PerfFeedbackAddin.Inventor.addin \
         Autodesk.SharedViews.Inventor.addin Autodesk.InteractiveTutorial.Inventor.addin \
         Autodesk.Publisher.Inventor.addin autodesk.dynamicsimulation.inventor.addin \
         autodesk.frameanalysis.inventor.addin autodesk.simulationstressanalysis.inventor.addin \
         autodesk.translatorfusion.inventor.addin autodesk.ilogic.inventor.addin; do
    mv "$ADDINS/$f" "$ADDINS/disabled/" 2>/dev/null
done

echo "[20/28] Moving InteractiveTutorial.dll (breaks wine-mono)..."
mv "$DEST/Bin/InteractiveTutorial.dll" "$ADDINS/disabled/libs/" 2>/dev/null
mv "$DEST/Bin/en-US/InteractiveTutorial.resources.dll" "$ADDINS/disabled/libs/" 2>/dev/null

echo "[21/28] Disabling CER crash reporter..."
mv "$DEST/Bin/CER/senddmp.exe" "$DEST/Bin/CER/senddmp.exe.disabled" 2>/dev/null

echo "[22/28] Removing bcp47langs.dll stubs (if present)..."
for f in "$WINEPREFIX/drive_c/windows/system32/bcp47langs.dll" \
         "$WINEPREFIX/drive_c/windows/syswow64/bcp47langs.dll"; do
    [ -f "$f" ] && mv "$f" "${f}.disabled"
done
wine reg delete 'HKCU\Software\Wine\DllOverrides' /v bcp47langs /f 2>/dev/null

echo "[23/28] Copying .NET 8 runtime..."
if [ -d "/mnt/windows/Program Files/dotnet" ]; then
    cp -a "/mnt/windows/Program Files/dotnet" "$WINEPREFIX/drive_c/Program Files/"
    echo "    Copied .NET 8 runtime ($(du -sh "$WINEPREFIX/drive_c/Program Files/dotnet" | cut -f1))"
fi

echo "[24/28] Copying Design Data..."
cp -r "/mnt/windows/Users/Public/Documents/Autodesk/Inventor 2026/Design Data" \
   "$WINEPREFIX/drive_c/users/Public/Documents/Autodesk/Inventor 2026/" 2>/dev/null

echo "[25/28] Copying Templates..."
mkdir -p "$WINEPREFIX/drive_c/users/Public/Documents/Autodesk/Inventor 2026/Templates/en-US"
cp -r "/mnt/windows/Users/Public/Documents/Autodesk/Inventor 2026/Templates/en-US/"* \
   "$WINEPREFIX/drive_c/users/Public/Documents/Autodesk/Inventor 2026/Templates/en-US/" 2>/dev/null

echo "[26/28] Copying Textures..."
cp -r "/mnt/windows/Users/Public/Documents/Autodesk/Inventor 2026/Textures" \
   "$WINEPREFIX/drive_c/users/Public/Documents/Autodesk/Inventor 2026/" 2>/dev/null

echo "[27/28] Patching OGSFactory.dll (null pointer fix for 3D viewport)..."
OGSDLL="$DEST/Bin/OGSFactory.dll"
if [ -f "$OGSDLL" ]; then
    cp "$OGSDLL" "${OGSDLL}.original"
    # Patch 1: Null check at crash site 1 (file offset 0x56E5B)
    printf '\xe9\x00\x9c\x0b\x00\x90\x90\x90' | dd of="$OGSDLL" bs=1 seek=$((0x56E5B)) conv=notrunc 2>/dev/null
    # Code cave 1 (file offset 0x110A60)
    printf '\x48\x8b\x4c\x24\x70\x48\x85\xc9\x0f\x84\x11\x64\xf4\xff\x48\x8b\x11\xe9\xed\x63\xf4\xff' | dd of="$OGSDLL" bs=1 seek=$((0x110A60)) conv=notrunc 2>/dev/null
    # Patch 2: Null check at crash site 2 (file offset 0x56EA8)
    printf '\xe9\xc9\x9b\x0b\x00\x90\x90\x90' | dd of="$OGSDLL" bs=1 seek=$((0x56EA8)) conv=notrunc 2>/dev/null
    # Code cave 2 (file offset 0x110A76)
    printf '\x48\x8b\x4c\x24\x70\x48\x85\xc9\x0f\x84\x48\x64\xf4\xff\x48\x8b\x11\xe9\x24\x64\xf4\xff' | dd of="$OGSDLL" bs=1 seek=$((0x110A76)) conv=notrunc 2>/dev/null
    echo "    OGSFactory.dll patched (backup at .original)"
fi

echo "[28/28] Waiting for WebView2 installer to finish..."
wait
sleep 5

echo ""
echo "=== Prefix rebuild complete! ==="
echo ""
echo "Post-rebuild steps:"
echo "  1. Set up OAuth2 handler: see README.md section 8"
echo "  2. First launch will require Autodesk SSO login via browser"
echo ""
echo "Run: bash ~/Projects/Inventor\ on\ linux/scripts/launch-inventor.sh"
