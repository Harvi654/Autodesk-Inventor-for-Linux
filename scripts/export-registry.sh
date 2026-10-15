#!/bin/bash
# Export Autodesk registry keys from a Windows installation into
# registry/autodesk-full.reg (gitignored), read directly from the hive files.
# rebuild-prefix.sh imports it and reads component versions from it.
#
# Requires: hivex (pacman -S hivex)
# Usage:    bash scripts/export-registry.sh [/mnt/windows]

set -euo pipefail
[ -n "${1:-}" ] && export WIN_ROOT="$1"
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

command -v hivexregedit >/dev/null || die "hivexregedit not found: sudo pacman -S hivex"
[ -d "$WIN_ROOT/Windows" ] || die "Windows partition not found at $WIN_ROOT"

WU="$(detect_win_user)"
[ -n "$WU" ] || die "no Windows user profile found (set WIN_USER=...)"
SOFTWARE_HIVE="$WIN_ROOT/Windows/System32/config/SOFTWARE"
NTUSER_HIVE="$WIN_ROOT/Users/$WU/NTUSER.DAT"
for h in "$SOFTWARE_HIVE" "$NTUSER_HIVE"; do [ -f "$h" ] || die "hive not found: $h"; done

echo "=== Autodesk registry export ==="
info "Windows: $WIN_ROOT   user: $WU"
info "Output:  $REG_FILE"
mkdir -p "$(dirname "$REG_FILE")"

# export <hive> <hive-path> <prefix-for-.reg>
export_key() {
    local out
    if out="$(hivexregedit --export "$1" "$2" 2>/dev/null)"; then
        # drop per-export headers; rewrite the hive-relative key names to full paths
        local repl="${3//\\/\\\\}\\\\"   # escape backslashes for sed
        grep -v '^Windows Registry Editor' <<<"$out" | sed "s|^\[\\\\|[$repl|"
        ok "$2" >&2
    else
        warn "$2 not found in $(basename "$1")" >&2
    fi
}

{
    printf 'Windows Registry Editor Version 5.00\r\n\r\n'
    export_key "$SOFTWARE_HIVE" '\Autodesk'             'HKEY_LOCAL_MACHINE\SOFTWARE'
    export_key "$SOFTWARE_HIVE" '\WOW6432Node\Autodesk' 'HKEY_LOCAL_MACHINE\SOFTWARE'
    export_key "$NTUSER_HIVE"   '\Software\Autodesk'    'HKEY_CURRENT_USER'
} > "$REG_FILE"

info "$(wc -l < "$REG_FILE") lines written"
CV="$(reg_value "Inventor\\RegistryVersion$INV_REGMAJOR.0" ClientVersion)"
info "Inventor ClientVersion: ${CV:-<not found>}"
info "IdentityManager versions: $(reg_idmgr_versions | tr '\n' ' ')"
info "Next: bash scripts/rebuild-prefix.sh"
