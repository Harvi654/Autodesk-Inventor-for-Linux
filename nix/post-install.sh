# The prefix setup of the Nix installation, after install-from-image.py (and
# the updates) in the same build: what migration 0001 does there and what
# depends on the installed files. Fixed settings (fonts, WebView2, X11) are in
# the separate configuration layer (nix/config-layer.sh), so a
# change to them does not reinstall Inventor. The script migrations
# (scripts/lib/migrations/) are not run here; nix/migrations.nix says for each
# one where the Nix package has it.
#
# Runs with WINEPREFIX, INV_YEAR and USER set and wine, wineserver, python3,
# coreutils, findutils, gnugrep on PATH. No network.
set -euo pipefail

: "${WINEPREFIX:?}" "${INV_YEAR:?}" "${USER:?}"
c="$WINEPREFIX/drive_c"
inv="$c/Program Files/Autodesk/Inventor $INV_YEAR"
asc_base="$c/Program Files/Common Files/Autodesk Shared/Components/$INV_YEAR"
lic_base="$c/Program Files (x86)/Common Files/Autodesk Shared/AdskLicensing"
idmgr_base="$c/Program Files/Autodesk/AdskIdentityManager"

say() { printf 'post-install: %s\n' "$*"; }
# Every wine call is bounded, and its output goes to a file, never to a pipe:
# a wine call into a stopped prefix can start services (licensing, Edge
# update) that inherit stdout and never exit - a command substitution would
# wait for them forever (scripts/lib/common.sh, wine_capture).
reg_add() {
    timeout 120 wine reg add "$@" /f </dev/null >/dev/null 2>&1 \
        || { say "wine reg add $1 failed or timed out"; exit 1; }
}
# A value from the prefix's registry ("" when not set), as `reg query`
# prints it (REG_DWORD as 0x...).
reg_get() {
    local t
    t="$(mktemp)"
    WINEDEBUG=-all timeout 120 wine reg query "$1" /v "$2" </dev/null >"$t" 2>/dev/null || true
    tr -d '\r' < "$t" | awk -v v="$2" \
        'tolower($1) == tolower(v) && $2 ~ /^REG_/ { $1 = ""; $2 = ""; sub(/^ +/, ""); print; exit }'
    rm -f -- "$t"
}
# End this prefix's Wine processes. A `wine reg` call into a stopped prefix
# can start services (licensing, Edge update) that never exit by themselves
# (scripts/lib/common.sh, wine_capture), so wait for a bounded time only.
stop_wine() {
    wineserver -k >/dev/null 2>&1 || true
    timeout 120 wineserver --wait >/dev/null 2>&1 || { say "Wine did not stop within 120 s"; exit 1; }
}
stop_wine

# Highest dotted-version subdirectory of $1, or nothing.
latest_version_dir() {
    [ -d "$1" ] || return 0
    find "$1" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' \
        | grep -E '^[0-9]+(\.[0-9]+)+$' | sort -V | tail -1 || true
}

# Autodesk's "Current" junctions as relative symlinks to the newest version
# folder (Wine leaves an unusable "Current?" directory). $1 = folder with
# version subfolders, $2 = link name, $3 = optional path below the version.
current_link() {
    local base="$1" name="$2" sub="${3:-}" ver junk
    [ -d "$base" ] || return 0
    if [ -e "$base/$name" ] && [ ! -d "$base/$name?" ]; then return 0; fi
    ver="$(latest_version_dir "$base")"
    [ -n "$ver" ] || return 0
    # the target first: nothing is removed for a link that cannot be made
    [ -d "$base/$ver${sub:+/$sub}" ] || return 0
    for junk in "$base/$name" "$base/$name?"; do
        if [ -L "$junk" ] || [ -f "$junk" ]; then rm -f -- "$junk"
        elif [ -d "$junk" ]; then
            # as configure.sh: a junction left with contents is kept
            rmdir -- "$junk" 2>/dev/null || { say "warning: $junk is not empty - left alone"; return 0; }
        fi
    done
    ln -s "$ver${sub:+/$sub}" "$base/$name"
    say "$(basename "$base")/$name -> $ver${sub:+/$sub}"
}

current_link "$lic_base" Current
current_link "$lic_base" CurrentSDK AdskLicensingSDK
current_link "$idmgr_base" Current
lic_ver="$(latest_version_dir "$lic_base")"
asc_ver="$(latest_version_dir "$asc_base")"
[ -n "$lic_ver" ] || { say "no AdskLicensing in $lic_base"; exit 1; }
[ -n "$asc_ver" ] || { say "no Shared Components in $asc_base"; exit 1; }
[ -f "$inv/Bin/Inventor.exe" ] || { say "no Inventor.exe in $inv/Bin"; exit 1; }
say "Licensing $lic_ver, Shared Components $asc_ver"

# Windows 10 (install-from-image.py sets it too, without checking).
reg_add 'HKCU\Software\Wine' /v Version /t REG_SZ /d win10
# Registry that names the installed versions.
reg_add "HKLM\\SOFTWARE\\Autodesk\\SharedComponents\\$INV_YEAR" /v InstallPath /t REG_EXPAND_SZ \
    /d "C:\\Program Files\\Common Files\\Autodesk Shared\\Components\\$INV_YEAR"
reg_add "HKLM\\SOFTWARE\\Autodesk\\SharedComponents\\$INV_YEAR" /v Version /t REG_EXPAND_SZ /d "$asc_ver"
reg_add 'HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment' /v Path /t REG_EXPAND_SZ \
    /d "C:\\windows\\system32;C:\\windows;C:\\windows\\system32\\wbem;C:\\Program Files\\Common Files\\Autodesk Shared\\Components\\$INV_YEAR\\$asc_ver;C:\\Program Files\\Autodesk\\Inventor $INV_YEAR\\Bin"
# Licensing service on manual start: the launcher runs it as a process; under
# Wine it never reports "running" as a service.
reg_add 'HKLM\SYSTEM\CurrentControlSet\Services\AdskLicensingService' /v Start /t REG_DWORD /d 3

# The Licensing Agent needs Identity Manager's IdSDK SSO plugin next to it.
agentdir="$lic_base/$lic_ver/AdskLicensingAgent"
if [ -d "$agentdir" ]; then
    mkdir -p "$agentdir/SSOPlugin/Current"
    for f in "$idmgr_base/Current/SSOPlugin/Current/"*.dll; do
        [ -e "$f" ] || continue
        [ -e "$agentdir/SSOPlugin/Current/$(basename "$f")" ] || cp "$f" "$agentdir/SSOPlugin/Current/"
    done
    if [ ! -f "$agentdir/IDSDKVersionCompatibility.config" ]; then
        agent_win="C:\\\\Program Files (x86)\\\\Common Files\\\\Autodesk Shared\\\\AdskLicensing\\\\$lic_ver\\\\AdskLicensingAgent\\\\SSOPlugin\\\\Current"
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
    fi
else
    say "no Licensing Agent in $agentdir"
fi

# Add-ins off by default (INV_DEFAULT_DISABLED_ADDINS in scripts/lib/common.sh;
# .NET Framework 4.8 is a layer here, so its add-ins stay on).
mkdir -p "$inv/Addins.disabled/libs"
for f in Autodesk.AssistantAddin.Inventor.addin; do
    if [ -f "$inv/Bin/Addins/$f" ]; then mv "$inv/Bin/Addins/$f" "$inv/Addins.disabled/"; fi
done

# Known crash sources.
if [ -f "$inv/Bin/CER/senddmp.exe" ]; then mv "$inv/Bin/CER/senddmp.exe" "$inv/Bin/CER/senddmp.exe.disabled"; fi
for f in "$c/windows/system32/bcp47langs.dll" "$c/windows/syswow64/bcp47langs.dll"; do
    if [ -f "$f" ]; then mv "$f" "$f.disabled"; fi
done
timeout 120 wine reg delete 'HKCU\Software\Wine\DllOverrides' /v bcp47langs /f </dev/null >/dev/null 2>&1 || true

# wine-mono's WPF stub assemblies (none without Wine Mono; kept for parity).
find "$c/windows" -path '*gac*' -type f \
    \( -name PresentationCore.dll -o -name PresentationFramework.dll -o -name WindowsBase.dll -o -name System.Xaml.dll \) \
    -delete

# RealDWG settings in the build user's profile; the launcher copies them into
# the runtime user's (nix/launch-services.sh). Without them Inventor stops at
# the splash screen ("Error 82").
rdwg="Program Files/Common Files/Autodesk Shared/RealDWG Shared $INV_YEAR"
if [ -d "$c/$rdwg" ]; then
    python3 -I - "$c/users/$USER/AppData/Roaming/Autodesk/Inventor $INV_YEAR/RealDWGSettings.xml" \
        "C:\\${rdwg//\//\\}" <<'PY'
import os, sys
path, install_dir = sys.argv[1], sys.argv[2]
os.makedirs(os.path.dirname(path), exist_ok=True)
if not os.path.exists(path):
    text = ('<?xml version="1.0" encoding="utf-16" standalone="no" ?>\r\n'
            '<RealDWGSettings InstallDirectory="%s"></RealDWGSettings>\r\n' % install_dir)
    with open(path, "wb") as f:
        f.write(b"\xff\xfe" + text.encode("utf-16-le"))
PY
else
    say "RealDWG Shared $INV_YEAR not installed - DWG import/export will not work"
fi

[ -f "$c/users/Public/Documents/Autodesk/Inventor $INV_YEAR/Default.ipj" ] || say "warning: no Default.ipj"
[ -f "$c/ProgramData/Autodesk/Inventor $INV_YEAR/WebBrowser/index.html" ] || say "warning: no App Home page"

# Migrations 0007/0008: plain-string (REG_SZ) values of Autodesk's packages
# that still hold %PUBLIC%\ unexpanded point nowhere; as on Windows they get
# the real folder. install-from-image.py maps the known folder tokens, so
# normally there is nothing to do. The hives on disk are current once Wine
# is stopped.
stop_wine
public_values="$(
    for hive in HKLM HKCU; do
        reg="$WINEPREFIX/system.reg"; [ "$hive" = HKCU ] && reg="$WINEPREFIX/user.reg"
        [ -f "$reg" ] || continue
        python3 -I - "$reg" "$hive" <<'PY'
import re, sys
path, hive = sys.argv[1], sys.argv[2]
unesc = lambda s: re.sub(r"\\(.)", r"\1", s)
roots = ("software\\autodesk\\", "software\\wow6432node\\autodesk\\")
helps = ("software\\microsoft\\windows\\html help", "software\\wow6432node\\microsoft\\windows\\html help")
key = None
for line in open(path, encoding="utf-8", errors="replace"):
    line = line.rstrip("\n")
    if line.startswith("["):
        k = unesc(line[1:line.rfind("]")])
        low = k.lower()
        key = k if (low.startswith(roots) or low in helps) else None
        continue
    if key is None:
        continue
    m = re.match(r'^(@|"((?:[^"\\]|\\.)*)")="((?:[^"\\]|\\.)*)"$', line)   # plain REG_SZ only
    if not m:
        continue
    data = unesc(m.group(3))
    if "%public%\\" not in data.lower():
        continue
    new = re.sub(r"(?i)%PUBLIC%\\", lambda _: "C:\\users\\Public\\", data)
    name = "" if m.group(1) == "@" else unesc(m.group(2))
    # \x1f, not a tab: tabs are IFS whitespace, so `read` would merge the
    # empty name of a default value (@) with its neighbours
    print("\x1f".join((hive, key, name, new)))
PY
    done
)"
if [ -n "$public_values" ]; then
    while IFS=$'\x1f' read -r hive key name new; do
        [ -n "$key" ] || continue
        if [ -n "$name" ]; then reg_add "$hive\\$key" /v "$name" /t REG_SZ /d "$new"
        else reg_add "$hive\\$key" /ve /t REG_SZ /d "$new"; fi
        say "%PUBLIC% -> C:\\users\\Public in $hive\\$key ${name:-(default)}"
    done <<< "$public_values"
fi

# The values Inventor needs from this script, read back.
check_value() {
    local got
    got="$(reg_get "$1" "$2")"
    [ "$got" = "$3" ] || { say "$1 $2 is '$got', expected '$3'"; exit 1; }
}
check_value 'HKCU\Software\Wine' Version win10
check_value "HKLM\\SOFTWARE\\Autodesk\\SharedComponents\\$INV_YEAR" Version "$asc_ver"
check_value 'HKLM\SYSTEM\CurrentControlSet\Services\AdskLicensingService' Start 0x3

# The install image drive.
rm -f "$WINEPREFIX/dosdevices/m:"
stop_wine
