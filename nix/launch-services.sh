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
# bbolt memory-maps this database. Keep its live inode on the native filesystem,
# outside the composed overlay, and serialize users of it with launch-lock.sh.
licensing_state="$WINEPREFIX/drive_c/ProgramData/Autodesk/AdskLicensingService"
licensing_native_state="$inventor_state_dir/licensing-data"
mkdir -p "$licensing_native_state" || exit 1
chmod 700 "$licensing_native_state" || exit 1
licensing_database="$licensing_state/AdskLicensingService.sds"
licensing_native_database="$licensing_native_state/AdskLicensingService.sds"
if [ ! -f "$licensing_native_database" ]; then
    cp -- "$licensing_database" "$licensing_native_database.tmp" || exit 1
    chmod 600 "$licensing_native_database.tmp" || exit 1
    mv -T -- "$licensing_native_database.tmp" "$licensing_native_database" || exit 1
fi
if [ "$(readlink "$licensing_database" 2>/dev/null || true)" != "$licensing_native_database" ]; then
    rm -f -- "$licensing_database" || exit 1
    ln -s -- "$licensing_native_database" "$licensing_database" || exit 1
fi
# Other mutable service files still need to be copied up from the Nix layer.
for state_file in AdskLicensingService.sds AdskLicensingService.data; do
    if [ -f "$licensing_state/$state_file" ]; then
        chmod u+w "$licensing_state/$state_file" || exit 1
    fi
done
# Wine creates a profile for the runtime user; seed the build-time default once.
realdwg_relative="AppData/Roaming/Autodesk/Inventor $inventor_year/RealDWGSettings.xml"
realdwg_settings="$WINEPREFIX/drive_c/users/$USER/$realdwg_relative"
if [ ! -f "$realdwg_settings" ]; then
    mkdir -p "$(dirname "$realdwg_settings")"
    cp "$WINEPREFIX/drive_c/users/nixbld/$realdwg_relative" "$realdwg_settings" || exit 1
    chmod u+w "$realdwg_settings"
fi
# The script-based installer creates a writable working prefix. A declarative
# layer only seeds RealDWG settings, so prepare Inventor's generated user files
# before its first document opens (2027 otherwise reports failed folder/add-in saves).
inventor_public="$WINEPREFIX/drive_c/users/Public/Documents/Autodesk/Inventor $inventor_year"
inventor_addins="$WINEPREFIX/drive_c/users/$USER/AppData/Roaming/Autodesk/Inventor $inventor_year/Addins"
mkdir -p "$inventor_public/Macros" "$inventor_addins" || exit 1
chmod u+rwx "$inventor_public/Macros" "$inventor_addins" || exit 1
# As in the source launcher, remove stale per-user Boost IPC session files.
idsdk_user_hex=$(printf %s "$USER" | od -An -tx1 -v | tr -d ' \n' | tr 'a-f' 'A-F')
idsdk_ipc="$WINEPREFIX/drive_c/ProgramData/Autodesk/IDSDK/$idsdk_user_hex/interprocess"
rm -rf -- "$idsdk_ipc"
mkdir -p "$idsdk_ipc/01000000"
inventor_log_root="${XDG_STATE_HOME:-$HOME/.local/state}/autodesk-inventor-$inventor_year"
mkdir -p "$inventor_log_root"
wine 'C:\Program Files\Autodesk\AdskIdentityManager\Current\AdskIdentityManager.exe' \
    >>"$inventor_log_root/identity.log" 2>&1 &
sleep 5
wine "$licensing_root/$licensing_version/AdskLicensingService/AdskLicensingService.exe" \
    >>"$inventor_log_root/licensing.log" 2>&1 &
sleep 5
