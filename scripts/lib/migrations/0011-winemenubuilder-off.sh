# shellcheck shell=bash
# Step 0011: Wine's menu builder off in the prefix itself:
# HKCU\Software\Wine\DllOverrides "winemenubuilder.exe" = "" - an empty
# load order, which Wine's loader reads as disabled (dlls/ntdll/unix/
# loadorder.c, parse_load_order; the module name keeps its .exe), the same
# as WINEDLLOVERRIDES=winemenubuilder.exe=d. Until now only that
# environment variable kept it off, which the installer and the launcher
# set (common.sh) but a plain `wine ...` in a terminal does not: in a fresh
# 2026 prefix, `wineserver -k` and then `wine reg query ...` by hand
# (2026-11-16) let wineboot run `winemenubuilder.exe -a -r`, which wrote 18
# entries into ~/.local/share/applications pointing at the prefix
# (wine-extension-ipt/iam/dwg/..., wine-protocol-adskidmgr/acad-acc) - file
# associations and the sign-in protocol that bypass the launcher.
# Then the menu entries of this prefix go, as install-desktop-integration.sh
# removes them (remove_wine_menu_entries). They are outside the prefix and
# not in the backup: Wine made them, and the registry backup holds the key.
# With the key set, wineboot logs "Error running cmd ...
# winemenubuilder.exe -a -r (126)" - expected (126: the module is
# disabled), as it already did under the environment variable.
MIG_DESC="Wine's menu builder off in the prefix (DllOverrides winemenubuilder.exe=\"\"), its menu entries removed"

mig_needed() {
    ! menubuilder_off && return 0
    local apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    grep -rqF -e "WINEPREFIX=$INV_PREFIX\"" -e "WINEPREFIX=\"$INV_PREFIX\"" "$apps" 2>/dev/null
}

mig_apply() {
    local n
    wine_reg_add 'HKCU\Software\Wine\DllOverrides' /v winemenubuilder.exe /t REG_SZ /d ""
    menubuilder_off || die "DllOverrides winemenubuilder.exe is not \"\" after setting it"
    ok "winemenubuilder.exe disabled in the prefix"
    n="$(remove_wine_menu_entries)"
    [ "$n" -eq 0 ] || ok "removed $n Wine menu entries and file types of $INV_PREFIX"
}
