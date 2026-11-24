#!/usr/bin/env bash
# Original, AI-assisted (Codex), LGPL-2.1-or-later.
# Source: https://github.com/Harvi654/winum/commit/4f3face16caf383e2856cb3916da5eec0598d663
set -euo pipefail
umask 077

usage() {
    printf 'Usage: bash %s INVENTOR_2027_PREFIX WINE_RUNTIME_DIR OUTPUT_PARENT\n' "$0"
}

die() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

if [[ $# == 1 && ( $1 == -h || $1 == --help ) ]]; then
    usage
    exit 0
fi
if [[ $# != 3 ]]; then
    usage >&2
    exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
launcher="$script_dir/../scripts/launch-inventor.sh"
summarizer="$script_dir/summarize-inventor-dwg-export.py"
source_prefix="$(realpath -e -- "$1" 2>/dev/null)" || die "Inventor prefix does not exist: $1"
runtime="$(realpath -e -- "$2" 2>/dev/null)" || die "Wine runtime does not exist: $2"
output_parent="$(realpath -e -- "$3" 2>/dev/null)" || die "Output directory does not exist: $3"

[[ -f "$source_prefix/drive_c/Program Files/Autodesk/Inventor 2027/Bin/Inventor.exe" ]] ||
    die "Inventor 2027 was not found in $source_prefix"
[[ -x "$runtime/bin/wine" && -f "$runtime/bin/wine" &&
   -x "$runtime/bin/wineserver" && -f "$runtime/bin/wineserver" ]] ||
    die "Expected executable bin/wine and bin/wineserver in $runtime"
[[ -d "$output_parent" && -w "$output_parent" && -x "$output_parent" ]] ||
    die "Output directory must be writable: $output_parent"
[[ "$output_parent" != "$source_prefix" && "$output_parent" != "$source_prefix/"* ]] ||
    die "Output directory must be outside the source prefix"
[[ -f "$launcher" ]] || die "Inventor launcher was not found: $launcher"
[[ -f "$summarizer" ]] || die "Export summarizer was not found: $summarizer"

work="$(mktemp -d -- "$output_parent/inventor-dwg-export.XXXXXXXX")" ||
    die "Could not create a trace directory in $output_parent"
printf 'inventor_export_work=%s\n' "$work"
printf '%s\n' 'Copying the Inventor 2027 prefix...'
cp -aT --reflink=auto -- "$source_prefix" "$work/inventor-prefix"

export INV_PREFIX="$work/inventor-prefix"
export WINEPREFIX="$INV_PREFIX"
[[ "$(realpath -e -- "$INV_PREFIX/drive_c" 2>/dev/null)" == "$INV_PREFIX/drive_c" &&
   "$(realpath -e -- "$INV_PREFIX/dosdevices/c:" 2>/dev/null)" == "$INV_PREFIX/drive_c" ]] ||
    die "The copied C: drive does not resolve to $INV_PREFIX/drive_c"
export INV_YEAR=2027 INV_WINE=system INV_SANDBOX=1
export INV_LOGDIR="$work/logs" INV_DATA_DIR="$work/data"
mkdir -p -- "$INV_LOGDIR" "$INV_DATA_DIR" "$INV_PREFIX/drive_c/winum-export-check"

unset WINEARCH WINELOADER WINESERVER WINEDLLPATH WINE_DATA_DIR WINEDLLOVERRIDES
export PATH="$runtime/bin:$PATH"
export WINE="$runtime/bin/wine"
export WINESERVER="$runtime/bin/wineserver"
relay_apis='comdlg32.GetOpenFileNameW;comdlg32.GetSaveFileNameW;kernelbase.MoveFileWithProgressW;kernelbase.GetFileAttributesExW;ntdll.NtQueryFullAttributesFile;ntdll.NtSetInformationFile;combase.CoCreateInstance;combase.CoGetClassObject'
WINEDEBUG=-all "$runtime/bin/wine" reg add 'HKCU\Software\Wine\Debug' \
    /v RelayInclude /t REG_SZ /d "$relay_apis" /f > "$work/relay-setup.log" 2>&1

export WINEDEBUG='-all,+pid,Inventor.exe:+file,Inventor.exe:+loaddll,Inventor.exe:+seh,Inventor.exe:+ole,Inventor.exe:+relay,dwgviewr.exe:+file,dwgviewr.exe:+loaddll,dwgviewr.exe:+seh,dwgviewr.exe:+ole,dwgviewr.exe:+relay'
printf '%s\n' 'Export one sheet as AutoCAD 2018 DWG to C:\winum-export-check\inventor-export.dwg, then close Inventor.'
launcher_exit=0
bash "$launcher" 2>&1 |
    sed -un '1,80p' > "$work/launcher-startup.txt" || launcher_exit=$?
{
    runtime_commit=
    if [[ -r "$runtime/BUILDINFO" ]]; then
        runtime_commit="$(awk '$1 == "commit:" {print $2; exit}' "$runtime/BUILDINFO")"
    fi
    printf 'runtime_commit=%s\n' "${runtime_commit:-unknown}"
    printf 'inventor_export_launcher_exit=%s\n' "$launcher_exit"
    python3 -I "$summarizer" "$work"
} | tee "$work/export-summary.txt"
