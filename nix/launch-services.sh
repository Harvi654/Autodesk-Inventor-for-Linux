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
# Font smoothing as on Windows by default: ClearType with RGB subpixels. The
# win32u-font-smoothing patch of winum (since 11.22-3) follows these desktop
# values for normal text such as Tahoma's; Wine's own default is grayscale
# (FontSmoothingType 1). They are written at every start, because a value
# that the writable state already has wins over one from a layer.
wine reg add 'HKCU\Control Panel\Desktop' /v FontSmoothing /t REG_SZ /d 2 /f || exit 1
wine reg add 'HKCU\Control Panel\Desktop' /v FontSmoothingType /t REG_DWORD /d 2 /f || exit 1
wine reg add 'HKCU\Control Panel\Desktop' /v FontSmoothingOrientation /t REG_DWORD /d 1 /f || exit 1
# Registry values that name the installed Shared Components version
# (nix/post-install.sh writes them into the installation layer). The writable
# state's registry is merged after the layers, so after an update that moves
# the version, an existing user would keep the old values, which point at
# files that the update removed. Writing them again at every start makes them
# follow the installation instead.
inventor_asc_base="$WINEPREFIX/drive_c/Program Files/Common Files/Autodesk Shared/Components/$inventor_year"
inventor_asc_version=$(find "$inventor_asc_base" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null |
    grep -E '^[0-9]+(\.[0-9]+)+$' | sort -V | tail -1)
if [ -n "$inventor_asc_version" ]; then
    inventor_asc_key="HKLM\\SOFTWARE\\Autodesk\\SharedComponents\\$inventor_year"
    inventor_asc_dir="C:\\Program Files\\Common Files\\Autodesk Shared\\Components\\$inventor_year"
    wine reg add "$inventor_asc_key" /v InstallPath /t REG_EXPAND_SZ /d "$inventor_asc_dir" /f || exit 1
    wine reg add "$inventor_asc_key" /v Version /t REG_EXPAND_SZ /d "$inventor_asc_version" /f || exit 1
    # The system Path: only its Shared Components segment is replaced, and
    # other segments (the user's, other programs') stay. The output is read
    # through a file, not a pipe, because a wine call can leave a service that
    # holds stdout open.
    inventor_env_key='HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
    inventor_path_out=$(mktemp) || exit 1
    # A failed query, or output without a Path value, leaves Path as it is.
    inventor_path_status=0
    WINEDEBUG=-all wine reg query "$inventor_env_key" /v Path </dev/null >"$inventor_path_out" 2>/dev/null ||
        inventor_path_status=$?
    inventor_path_new=$(python3 -I - "$inventor_path_out" "$inventor_year" "$inventor_asc_dir\\$inventor_asc_version" \
        "$inventor_path_status" <<'PY'
import re, sys
out, year, managed, status = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
current = None
for line in open(out, encoding="utf-8", errors="replace"):
    m = re.match(r"\s*Path\s+REG_[A-Z_]+\s+(.*?)\s*$", line, re.I)
    if m:
        current = m.group(1)
        break
if status != "0" or not current:
    # the query failed or gave no Path: keep whatever is there
    print("Inventor: could not read the Windows Path; left as it is", file=sys.stderr)
    print("")
    sys.exit(0)
inventor_bin = "C:\\Program Files\\Autodesk\\Inventor %s\\Bin" % year
# only the version directory in the release's Shared Components folder is
# managed; other segments stay, including custom subdirectories of that folder
version_dir = re.compile(r"(?i)^c:\\program files\\common files\\autodesk shared\\components\\%s\\\d+(\.\d+)+\\?$"
                         % re.escape(year))
kept, placed = [], False
for s in [s for s in current.split(";") if s]:
    if version_dir.match(s):
        if not placed:
            kept.append(managed)
            placed = True
        continue
    kept.append(s)
if not placed:
    lower = [s.lower() for s in kept]
    kept.insert(lower.index(inventor_bin.lower()) if inventor_bin.lower() in lower else len(kept), managed)
if inventor_bin.lower() not in [s.lower() for s in kept]:
    kept.append(inventor_bin)
new = ";".join(kept)
print("" if new == current else new)
PY
    ) || exit 1
    rm -f -- "$inventor_path_out"
    if [ -n "$inventor_path_new" ]; then
        wine reg add "$inventor_env_key" /v Path /t REG_EXPAND_SZ /d "$inventor_path_new" /f || exit 1
    fi
fi
unset inventor_asc_base inventor_asc_version inventor_asc_key inventor_asc_dir inventor_env_key \
    inventor_path_out inventor_path_new inventor_path_status
licensing_root="$WINEPREFIX/drive_c/Program Files (x86)/Common Files/Autodesk Shared/AdskLicensing"
licensing_version=$(find "$licensing_root" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' |
    grep -E '^[0-9]+(\.[0-9]+)+$' | sort -V | tail -1)
if [ -z "$licensing_version" ]; then
    echo "Inventor: no Autodesk licensing service in the composed prefix" >&2
    exit 1
fi
# bbolt memory-maps this database. Keep its live inode on the native filesystem,
# outside the composed overlay, and rely on nix-overlayfs's session lock to
# allow only one user of it at a time.
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
