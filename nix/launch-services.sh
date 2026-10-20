# Runs inside the supervised nix-overlayfs session, with its composed WINEPREFIX.
inventor_driver="${INVENTOR_WINE_DRIVER:-x11}"
case "$inventor_driver" in
    x11) ;;
    wayland)
        if [ -z "${WAYLAND_DISPLAY:-}" ]; then
            echo "Inventor: the Wayland launcher requires a Wayland session" >&2
            exit 1
        fi
        ;;
    *) echo "Inventor: unsupported Wine display driver: $inventor_driver" >&2; exit 1 ;;
esac
wine reg add 'HKCU\Software\Wine\Drivers' /v Graphics /t REG_SZ /d "$inventor_driver" /f || exit 1
if [ "$inventor_driver" = wayland ]; then
    unset DISPLAY
fi
licensing_root="$WINEPREFIX/drive_c/Program Files (x86)/Common Files/Autodesk Shared/AdskLicensing"
licensing_version=$(find "$licensing_root" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' |
    grep -E '^[0-9]+(\.[0-9]+)+$' | sort -V | tail -1)
if [ -z "$licensing_version" ]; then
    echo "Inventor: no Autodesk licensing service in the composed prefix" >&2
    exit 1
fi
# Nix store files arrive read-only; copy up the service's mutable database.
licensing_state="$WINEPREFIX/drive_c/ProgramData/Autodesk/AdskLicensingService"
for state_file in AdskLicensingService.sds AdskLicensingService.data; do
    if [ -f "$licensing_state/$state_file" ]; then
        chmod u+w "$licensing_state/$state_file" || exit 1
    fi
done
# Wine creates a profile for the runtime user; seed the build-time default once.
realdwg_relative="AppData/Roaming/Autodesk/Inventor 2026/RealDWGSettings.xml"
realdwg_settings="$WINEPREFIX/drive_c/users/$USER/$realdwg_relative"
if [ ! -f "$realdwg_settings" ]; then
    mkdir -p "$(dirname "$realdwg_settings")"
    cp "$WINEPREFIX/drive_c/users/nixbld/$realdwg_relative" "$realdwg_settings" || exit 1
    chmod u+w "$realdwg_settings"
fi
# As in the source launcher, remove stale per-user Boost IPC session files.
idsdk_user_hex=$(printf %s "$USER" | od -An -tx1 -v | tr -d ' \n' | tr 'a-f' 'A-F')
idsdk_ipc="$WINEPREFIX/drive_c/ProgramData/Autodesk/IDSDK/$idsdk_user_hex/interprocess"
rm -rf -- "$idsdk_ipc"
mkdir -p "$idsdk_ipc/01000000"
inventor_log_root="${XDG_STATE_HOME:-$HOME/.local/state}/autodesk-inventor-2026"
mkdir -p "$inventor_log_root"
wine 'C:\Program Files\Autodesk\AdskIdentityManager\Current\AdskIdentityManager.exe' \
    >>"$inventor_log_root/identity.log" 2>&1 &
sleep 5
wine "$licensing_root/$licensing_version/AdskLicensingService/AdskLicensingService.exe" \
    >>"$inventor_log_root/licensing.log" 2>&1 &
sleep 5
