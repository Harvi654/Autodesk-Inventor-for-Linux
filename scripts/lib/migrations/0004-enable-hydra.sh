# shellcheck shell=bash
# Step 0004: EnableHydra=1 (DWORD) under
# HKCU\Software\Autodesk\Inventor\RegistryVersion<NN>.0\System\Preferences\Driver,
# NN by release (2026 -> 30, 2027 -> 31): the setting GPU ray tracing needs
# (docs/arch-hyprland.md, "GPU ray tracing").
# OPTIONAL - run only by name (migrate-prefix.sh --run 0004), never by the
# launcher or an update: on a card without ray tracing hardware (RX 580,
# measured by the maintainer on 2026-10-21, PR #3) it switches Inventor to
# Hydra/USD and ray tracing runs on the CPU at about 1200 % CPU. Waits for a
# GPU check and an L4 on a ray tracing card before it can be a normal step.
MIG_OPTIONAL=1
MIG_DESC="Inventor driver preference EnableHydra=1 (RegistryVersion$INV_REGMAJOR.0) - only for a GPU with ray tracing hardware"

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
