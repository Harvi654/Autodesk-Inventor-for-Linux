#!/bin/bash
# Export Autodesk registry keys from a Windows installation.
# Generates registry/autodesk-full.reg from the Windows hive files directly,
# so no Autodesk data needs to be committed to the repo.
#
# Requires: hivex (sudo pacman -S hivex)
# Usage:    bash scripts/export-registry.sh [/mnt/windows]

set -euo pipefail

WINDOWS="${1:-/mnt/windows}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT="$SCRIPT_DIR/../registry/autodesk-full.reg"

# Verify hivex is available
if ! command -v hivexregedit &>/dev/null; then
    echo "ERROR: hivexregedit not found. Install hivex:"
    echo "  sudo pacman -S hivex"
    exit 1
fi

# Verify Windows partition is mounted
if [ ! -d "$WINDOWS/Windows" ]; then
    echo "ERROR: Windows partition not found at $WINDOWS"
    echo "  Mount it first, or pass the path as an argument:"
    echo "  bash scripts/export-registry.sh /path/to/windows"
    exit 1
fi

# Detect first non-system Windows user profile
WIN_USER=$(ls "$WINDOWS/Users/" 2>/dev/null \
    | grep -vxE 'Public|Default|Default User|All Users' \
    | head -1)

if [ -z "$WIN_USER" ]; then
    echo "ERROR: No user profile found under $WINDOWS/Users/"
    exit 1
fi

SOFTWARE_HIVE="$WINDOWS/Windows/System32/config/SOFTWARE"
NTUSER_HIVE="$WINDOWS/Users/$WIN_USER/NTUSER.DAT"

echo "=== Autodesk Registry Exporter ==="
echo "  Windows:  $WINDOWS"
echo "  User:     $WIN_USER"
echo "  Output:   $OUTPUT"
echo ""

for hive in "$SOFTWARE_HIVE" "$NTUSER_HIVE"; do
    if [ ! -f "$hive" ]; then
        echo "ERROR: Registry hive not found: $hive"
        exit 1
    fi
done

mkdir -p "$(dirname "$OUTPUT")"

{
    printf 'Windows Registry Editor Version 5.00\r\n\r\n'

    echo "[1/2] Exporting HKLM\\SOFTWARE\\Autodesk..." >&2
    if hivexregedit --export "$SOFTWARE_HIVE" '\Autodesk' 2>/dev/null \
            | sed 's|^\[\\|[HKEY_LOCAL_MACHINE\\SOFTWARE\\|'; then
        echo "      OK" >&2
    else
        echo "      WARNING: HKLM Autodesk keys not found or export failed" >&2
    fi

    echo "[2/2] Exporting HKCU\\Software\\Autodesk..." >&2
    if hivexregedit --export "$NTUSER_HIVE" '\Software\Autodesk' 2>/dev/null \
            | sed 's|^\[\\Software\\|[HKEY_CURRENT_USER\\Software\\|'; then
        echo "      OK" >&2
    else
        echo "      WARNING: HKCU Autodesk keys not found or export failed" >&2
    fi

} > "$OUTPUT"

LINE_COUNT=$(wc -l < "$OUTPUT")
echo ""
echo "=== Export complete ==="
echo "  $LINE_COUNT lines written to $OUTPUT"
echo ""
echo "Next: run scripts/rebuild-prefix.sh"
