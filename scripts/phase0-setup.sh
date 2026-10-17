#!/bin/bash
# Phase 0: install system prerequisites on Arch Linux (and derivatives).
#
# Only official Arch repositories are used - nothing from the AUR.
# DXVK is downloaded later by rebuild-prefix.sh from the official DXVK GitHub
# release and checked against a pinned SHA-256.
#
# Run as your normal user (NOT with sudo) - it calls sudo for pacman itself.
#
# Usage: bash scripts/phase0-setup.sh [--staging]
#   --staging   install wine-staging instead of wine

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

[ "$EUID" -ne 0 ] || die "run this as your normal user, not root/sudo"

WINE_PKG=wine
[ "${1:-}" = "--staging" ] && WINE_PKG=wine-staging

_STEPS=3

step "Checking [multilib]..."
grep -qE '^\[multilib\]' /etc/pacman.conf \
    || die "enable [multilib] in /etc/pacman.conf (uncomment the [multilib] section), then run: sudo pacman -Syu"
ok "multilib enabled"

step "Installing packages from the official repos..."
PKGS=(
    "$WINE_PKG" wine-mono wine-gecko winetricks   # Wine + .NET Framework replacement + HTML engine
    rsync hivex imagemagick zstd cabextract unzip # copying, registry export, icon, archives
    xdg-utils desktop-file-utils libnotify        # adskidmgr:// handler, launch notifications
    curl coreutils tar                            # DXVK/WebView2 download + checksum
    vulkan-icd-loader lib32-vulkan-icd-loader vulkan-tools
    mingw-w64-gcc base-devel flex bison           # building the patched Wine parts
    vulkan-headers libx11 libxext libxcomposite libxi libxrandr libxrender \
    libxcursor libxfixes libxinerama mesa         # ... the X11 driver (winex11.so)
    git                                           # updates of this project
    python 7zip                                   # install-from-image.py, Autodesk's .exe downloads
    ttf-liberation noto-fonts ttf-dejavu          # fonts instead of Windows' (linux-fonts.sh)
)
# Vulkan driver for the GPU(s) present. Skipped for NVIDIA if any nvidia utils
# package is already installed (nvidia-open / -beta / -470xx setups differ).
GPU="$(lspci 2>/dev/null | grep -Ei 'vga|3d|display' || true)"
if [ -n "$GPU" ]; then while IFS= read -r g; do info "GPU: ${g#*: }"; done <<<"$GPU"; else info "GPU: unknown"; fi
if grep -qi nvidia <<<"$GPU" && ! pacman -Qq 2>/dev/null | grep -cE '^nvidia.*utils' >/dev/null; then
    PKGS+=(nvidia-utils lib32-nvidia-utils)
fi
grep -qiE 'amd|radeon' <<<"$GPU" && PKGS+=(vulkan-radeon lib32-vulkan-radeon)
grep -qi intel <<<"$GPU" && PKGS+=(vulkan-intel lib32-vulkan-intel)
# -Syu: Arch does not support installing from an outdated package database
# (packages that were replaced on the mirrors give 404) - update the system
# together with the new packages.
info "updating the system together with the packages (pacman -Syu) - Arch needs both at once"
if pacman -Qq 2>/dev/null | grep -qE '^nvidia-[0-9]+xx-dkms$'; then
    warn "your NVIDIA driver comes from the AUR ($(pacman -Qq | grep -E '^nvidia-[0-9]+xx-dkms$')): if the kernel is updated,"
    warn "update the driver too (e.g. yay -Syu) and reboot - check with: nvidia-smi"
fi
sudo pacman -Syu --needed "${PKGS[@]}"

step "Summary"
info "$(wine --version 2>/dev/null || echo 'wine: not found')"
info "Next: bash scripts/check-system.sh"
