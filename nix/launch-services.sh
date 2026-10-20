# Runs inside the supervised nix-overlayfs session, with its composed WINEPREFIX.
licensing_root="$WINEPREFIX/drive_c/Program Files (x86)/Common Files/Autodesk Shared/AdskLicensing"
licensing_version=$(find "$licensing_root" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' |
    grep -E '^[0-9]+(\.[0-9]+)+$' | sort -V | tail -1)
if [ -z "$licensing_version" ]; then
    echo "Inventor: no Autodesk licensing service in the composed prefix" >&2
    exit 1
fi
inventor_log_root="${XDG_STATE_HOME:-$HOME/.local/state}/autodesk-inventor-2026"
mkdir -p "$inventor_log_root"
wine 'C:\Program Files\Autodesk\AdskIdentityManager\Current\AdskIdentityManager.exe' \
    >>"$inventor_log_root/identity.log" 2>&1 &
sleep 5
wine "C:\Program Files (x86)\Common Files\Autodesk Shared\AdskLicensing\$licensing_version\AdskLicensingService\AdskLicensingService.exe" \
    >>"$inventor_log_root/licensing.log" 2>&1 &
sleep 5
