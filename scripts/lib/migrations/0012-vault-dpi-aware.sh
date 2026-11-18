# shellcheck shell=bash
# Step 0012: dpiAwareness=1 (DWORD, system DPI aware) for Connectivity.Vault.exe
# under HKLM\Software\Microsoft\Windows NT\CurrentVersion\Image File Execution
# Options, which Wine's user32 reads when the process starts. Vault Explorer
# (the Vault Basic client of the same year, installed into the Inventor prefix
# with install-from-image.py --app vbc) is DPI unaware: above 96 DPI Wine
# scales its window surface, and the CefSharp start page - a child window
# owned by the browser subprocess, drawn unscaled straight to the X window -
# lands in the wrong place while its own place stays black. System DPI aware,
# Vault scales itself and Wine scales nothing. Set for every prefix: the value
# only applies when a program of that name runs, so a prefix without the Vault
# client is unchanged in effect, and one that gets the client later is ready.
# docs/arch-hyprland.md, "Vault Basic 2027 client".
MIG_DESC="Vault Explorer (Connectivity.Vault.exe) system DPI aware: dpiAwareness=1"

_MIG_IFEO_KEY='HKLM\Software\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\Connectivity.Vault.exe'

mig_needed() {
    case "$(mig_reg_get "$_MIG_IFEO_KEY" dpiAwareness)" in 0x1|0x00000001|1) return 1 ;; esac
    return 0
}

mig_apply() {
    wine_reg_add "$_MIG_IFEO_KEY" /v dpiAwareness /t REG_DWORD /d 1
    wine_stop
    ! mig_needed || { err "dpiAwareness did not stick"; return 1; }
}
