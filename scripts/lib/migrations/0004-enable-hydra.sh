# shellcheck shell=bash
# Step 0004: EnableHydra=1 (DWORD) under
# HKCU\Software\Autodesk\Inventor\RegistryVersion<NN>.0\System\Preferences\Driver,
# NN by release (2026 -> 30, 2027 -> 31): the setting GPU ray tracing needs
# (docs/arch-hyprland.md, "GPU ray tracing"). Whether the card can do it is
# Inventor's check; with no ray tracing GPU the option stays unavailable.
MIG_DESC="Inventor driver preference EnableHydra=1 (RegistryVersion$INV_REGMAJOR.0)"

_mig_hydra_key() { echo "HKCU\\Software\\Autodesk\\Inventor\\RegistryVersion$INV_REGMAJOR.0\\System\\Preferences\\Driver"; }

mig_needed() {
    case "$(mig_reg_get "$(_mig_hydra_key)" EnableHydra)" in 0x1|0x00000001|1) return 1 ;; esac
    return 0
}

mig_apply() {
    wine_reg_add "$(_mig_hydra_key)" /v EnableHydra /t REG_DWORD /d 1
    wine_stop
    ! mig_needed || { err "EnableHydra did not stick"; return 1; }
}
