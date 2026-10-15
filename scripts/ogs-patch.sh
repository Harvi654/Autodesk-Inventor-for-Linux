#!/bin/bash
# Apply / revert / inspect the OGSFactory.dll null-pointer patch.
#
# Usage: bash scripts/ogs-patch.sh status|apply|revert
#
# Why revert exists - hypothesis to test (see docs/arch-hyprland.md):
# Wine's IEnumWbemClassObject::Next() never returns S_OK with a NULL object;
# on an empty result it returns WBEM_S_FALSE (1), which OGS does not treat as
# a failure and then dereferences NULL. The empty result came from the missing
# Win32_TimeZone class. With the wbemprox patch installed the query returns one
# row, so the unpatched DLL may work - without the darker-materials side effect.

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

DLL="$P_INV/Bin/OGSFactory.dll"
ORIG="$DLL.original"
[ -f "$DLL" ] || die "not found: $DLL (build the prefix first)"

hexat() { od -v -An -tx1 -j "$1" -N "$2" "$DLL" | tr -d ' \n'; }
SITE1=$((0x56E5B)); SITE2=$((0x56EA8)); CAVE1=$((0x110A60)); CAVE2=$((0x110A76))
EXPECT_SITE="488b4c2470488b11"   # mov rcx,[rsp+0x70] ; mov rdx,[rcx]

state() {
    if [ "$(hexat $SITE1 5)" = "e9009c0b00" ] && [ "$(hexat $SITE2 5)" = "e9c99b0b00" ]; then echo patched
    elif [ "$(hexat $SITE1 8)" = "$EXPECT_SITE" ] && [ "$(hexat $SITE2 8)" = "$EXPECT_SITE" ] \
         && [[ "$(hexat $CAVE1 44)" =~ ^(00|cc)+$ ]]; then echo original
    else echo unknown; fi
}

wbemprox_ok() {
    local pe; pe="$(wine_pe_dir)"
    [ -n "$pe" ] && strings -el "$pe/wbemprox.dll" 2>/dev/null | grep -qx Win32_TimeZone
}

case "${1:-status}" in
    status)
        info "OGSFactory.dll: $(state)  ($DLL)"
        info "sha256: $(sha256sum "$DLL" | cut -d' ' -f1)"
        [ -f "$ORIG" ] && info "backup present: $ORIG"
        if wbemprox_ok; then ok "system wbemprox.dll has Win32_TimeZone"; else warn "system wbemprox.dll is unpatched"; fi
        ;;
    apply)
        case "$(state)" in
            patched) ok "already patched"; exit 0 ;;
            unknown) die "unknown OGSFactory.dll build - not patching (sha256 $(sha256sum "$DLL" | cut -d' ' -f1))" ;;
        esac
        [ -f "$ORIG" ] || cp "$DLL" "$ORIG"
        pb() { printf '%b' "$2" | dd of="$DLL" bs=1 seek="$1" conv=notrunc status=none; }
        pb $SITE1 '\xe9\x00\x9c\x0b\x00\x90\x90\x90'
        pb $CAVE1 '\x48\x8b\x4c\x24\x70\x48\x85\xc9\x0f\x84\x11\x64\xf4\xff\x48\x8b\x11\xe9\xed\x63\xf4\xff'
        pb $SITE2 '\xe9\xc9\x9b\x0b\x00\x90\x90\x90'
        pb $CAVE2 '\x48\x8b\x4c\x24\x70\x48\x85\xc9\x0f\x84\x48\x64\xf4\xff\x48\x8b\x11\xe9\x24\x64\xf4\xff'
        [ "$(state)" = patched ] || die "verification failed"
        ok "patched (backup: $ORIG)"
        ;;
    revert)
        [ -f "$ORIG" ] || die "no backup at $ORIG"
        cp "$ORIG" "$DLL"
        ok "restored original OGSFactory.dll"
        wbemprox_ok || warn "wbemprox.dll is unpatched - the original DLL WILL crash on Part creation"
        ;;
    *) die "usage: $0 status|apply|revert" ;;
esac
