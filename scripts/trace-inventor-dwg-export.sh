#!/usr/bin/env bash
# Original, AI-assisted (Codex), LGPL-2.1-or-later.
# Source: https://github.com/Harvi654/winum/commit/4f3face16caf383e2856cb3916da5eec0598d663
set -euo pipefail
umask 077

if [[ $# != 0 ]]; then
    printf 'Usage: bash %s\n' "$0" >&2
    exit 2
fi
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
inventor_repo="${INV_EXPORT_REPO:-$HOME/inventor-on-linux}"
source_prefix="$(realpath -e -- "${INV_EXPORT_SOURCE:-$HOME/.wine-inventor2027}")"
storage="$(realpath -e -- "${INV_EXPORT_DISK:-$HOME/nvme}")"

if [[ ! -f "$source_prefix/drive_c/Program Files/Autodesk/Inventor 2027/Bin/Inventor.exe" ]]; then
    printf 'Inventor 2027 was not found in %s\n' "$source_prefix" >&2
    exit 1
fi
if [[ ! -f "$inventor_repo/scripts/launch-inventor.sh" ]]; then
    printf 'Inventor launcher was not found in %s\n' "$inventor_repo" >&2
    exit 1
fi

# These reference paths survive closing the terminal.
runtime=
for reference in "${ACAD_AUTOCOMPLETE_WORK:-$storage}/base-runtime.txt" \
                 "$storage"/.acad-*/base-runtime.txt; do
    [[ -s "$reference" ]] || continue
    candidate="$(< "$reference")"
    [[ -n "$candidate" && -x "$candidate/bin/wine" && -x "$candidate/bin/wineserver" ]] || continue
    if grep -Eq '^commit:[[:space:]]+aeb7a59[[:space:]]*$' "$candidate/BUILDINFO"; then
        runtime="$(realpath -e -- "$candidate")"
        break
    fi
done
if [[ -z "$runtime" ]]; then
    printf '%s\n' 'The AutoCAD reference winum build aeb7a59 was not found in the NVMe test directories.' >&2
    exit 1
fi

work="$(mktemp -d "$storage/.inventor-dwg-export.XXXXXXXX")"
printf 'inventor_export_work=%s\n' "$work"
test -f "$script_dir/summarize-inventor-dwg-export.py"
printf '%s\n' 'Copying the Inventor 2027 prefix...'
cp -aT --reflink=auto -- "$source_prefix" "$work/inventor-prefix"

export INV_PREFIX="$work/inventor-prefix"
export WINEPREFIX="$INV_PREFIX"
test "$(realpath -e -- "$INV_PREFIX/drive_c")" = "$INV_PREFIX/drive_c"
test "$(realpath -e -- "$INV_PREFIX/dosdevices/c:")" = "$INV_PREFIX/drive_c"
export INV_YEAR=2027 INV_WINE=system INV_SANDBOX=1
export INV_LOGDIR="$work/logs" INV_DATA_DIR="$work/data"
mkdir -p -- "$INV_LOGDIR" "$INV_DATA_DIR" "$INV_PREFIX/drive_c/winum-export-check"

unset WINEARCH WINELOADER WINESERVER WINEDLLPATH WINE_DATA_DIR WINEDLLOVERRIDES
export PATH="$runtime/bin:$PATH"
export WINESERVER="$runtime/bin/wineserver"
relay_apis='comdlg32.GetOpenFileNameW;comdlg32.GetSaveFileNameW;kernelbase.MoveFileWithProgressW;kernelbase.GetFileAttributesExW;ntdll.NtQueryFullAttributesFile;ntdll.NtSetInformationFile;combase.CoCreateInstance;combase.CoGetClassObject'
WINEDEBUG=-all "$runtime/bin/wine" reg add 'HKCU\Software\Wine\Debug' \
    /v RelayInclude /t REG_SZ /d "$relay_apis" /f > "$work/relay-setup.log" 2>&1

export WINEDEBUG='-all,+pid,Inventor.exe:+file,Inventor.exe:+loaddll,Inventor.exe:+seh,Inventor.exe:+ole,Inventor.exe:+relay,dwgviewr.exe:+file,dwgviewr.exe:+loaddll,dwgviewr.exe:+seh,dwgviewr.exe:+ole,dwgviewr.exe:+relay'
printf '%s\n' 'Export one sheet as AutoCAD 2018 DWG to C:\winum-export-check\inventor-export.dwg, then close Inventor.'
launcher_exit=0
bash "$inventor_repo/scripts/launch-inventor.sh" 2>&1 |
    sed -un '1,80p' > "$work/launcher-startup.txt" || launcher_exit=$?
{
    awk '$1 == "commit:" {print "runtime_commit=" $2}' "$runtime/BUILDINFO"
    printf 'inventor_export_launcher_exit=%s\n' "$launcher_exit"
    python3 -I "$script_dir/summarize-inventor-dwg-export.py" "$work"
} | tee "$work/export-summary.txt"
