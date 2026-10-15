#!/bin/bash
# Phase 0: install system prerequisites on Arch Linux (and derivatives).
#
# Run as your normal user (NOT with sudo) - it calls sudo for pacman itself,
# and AUR helpers refuse to run as root.
#
# Usage: bash scripts/phase0-setup.sh [--staging]
#   --staging   install wine-staging instead of wine

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

[ "$EUID" -ne 0 ] || die "run this as your normal user, not root/sudo"

WINE_PKG=wine
[ "${1:-}" = "--staging" ] && WINE_PKG=wine-staging

_STEPS=4

step "Checking [multilib]..."
grep -qE '^\[multilib\]' /etc/pacman.conf \
    || die "enable [multilib] in /etc/pacman.conf (uncomment the [multilib] section), then run: sudo pacman -Syu"
ok "multilib enabled"

step "Installing packages from the official repos..."
PKGS=(
    "$WINE_PKG" wine-mono wine-gecko winetricks   # Wine + .NET Framework replacement + HTML engine
    rsync hivex imagemagick zstd cabextract unzip # copying, registry export, icon, archives
    xdg-utils desktop-file-utils                  # adskidmgr:// protocol handler
    vulkan-icd-loader lib32-vulkan-icd-loader vulkan-tools
    mingw-w64-gcc base-devel flex bison           # building the patched wbemprox.dll
)
# Vulkan driver for the GPU(s) present. Skipped for NVIDIA if any nvidia utils
# package is already installed (nvidia-open / -beta / -470xx setups differ).
GPU="$(lspci 2>/dev/null | grep -Ei 'vga|3d|display' || true)"
info "GPU: ${GPU:-unknown}"
if grep -qi nvidia <<<"$GPU" && ! pacman -Qq 2>/dev/null | grep -qE '^nvidia.*utils'; then
    PKGS+=(nvidia-utils lib32-nvidia-utils)
fi
grep -qiE 'amd|radeon' <<<"$GPU" && PKGS+=(vulkan-radeon lib32-vulkan-radeon)
grep -qi intel <<<"$GPU" && PKGS+=(vulkan-intel lib32-vulkan-intel)
sudo pacman -S --needed "${PKGS[@]}"

step "Installing DXVK (AUR: dxvk-bin, provides setup_dxvk)..."
if command -v setup_dxvk >/dev/null; then
    ok "setup_dxvk already available ($(command -v setup_dxvk))"
else
    AUR=""
    for h in paru yay; do command -v "$h" >/dev/null && { AUR="$h"; break; }; done
    if [ -n "$AUR" ]; then
        "$AUR" -S --needed dxvk-bin
    else
        warn "no AUR helper (paru/yay) found. Install DXVK manually:"
        info "  git clone https://aur.archlinux.org/dxvk-bin.git && cd dxvk-bin && makepkg -si"
    fi
fi

step "Summary"
info "$(wine --version 2>/dev/null || echo 'wine: not found')"
if command -v setup_dxvk >/dev/null; then ok "setup_dxvk"; else warn "setup_dxvk still missing"; fi
info "Next: bash scripts/check-system.sh"
