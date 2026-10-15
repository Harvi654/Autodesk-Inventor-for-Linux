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

step "Summary"
info "$(wine --version 2>/dev/null || echo 'wine: not found')"
info "Next: bash scripts/check-system.sh"
