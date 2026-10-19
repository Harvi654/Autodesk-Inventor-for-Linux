#!/bin/bash
# Phase 0: install system prerequisites.
#
#   Arch Linux and derivatives (pacman): official repositories only, no AUR.
#   Debian / Ubuntu and derivatives (apt), Fedora (dnf): only the libraries
#   this project's own Wine needs, plus the tools the scripts use - Wine itself
#   comes from get-wine.sh, not from the distribution.
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

if [ "$INV_DISTRO" = debian ] || [ "$INV_DISTRO" = fedora ]; then
    _STEPS=2
    # Libraries this project's Wine (WoW64, 64-bit host only) loads, found
    # with ldd/dlopen names on Ubuntu 24.04; tools used by the scripts.
    if [ "$INV_DISTRO" = debian ]; then
        t64() { if apt-cache show "${1}t64" >/dev/null 2>&1; then echo "${1}t64"; else echo "$1"; fi; }
        PKGS=(
            libx11-6 libxext6 libxcomposite1 libxcursor1 libxfixes3 libxi6 libxinerama1
            libxrandr2 libxrender1 libxxf86vm1 libxkbcommon0 libxkbregistry0
            libvulkan1 mesa-vulkan-drivers vulkan-tools libegl1 libgl1 libwayland-client0 libwayland-egl1
            libfreetype6 libfontconfig1 "$(t64 libgnutls30)" "$(t64 libasound2)" libpulse0 libdbus-1-3
            libkrb5-3 libgssapi-krb5-2 libgstreamer1.0-0 libgstreamer-plugins-base1.0-0
            libsdl2-2.0-0 libudev1 libusb-1.0-0 "$(t64 libcups2)" libpcsclite1 "$(t64 libv4l-0)"
            python3 p7zip-full rsync curl xz-utils zstd cabextract unzip imagemagick
            xdg-utils desktop-file-utils libnotify-bin git
            fonts-liberation fonts-noto-core fonts-dejavu-core
        )
        step "Installing packages (apt)..."
        sudo apt-get update
        sudo apt-get install -y --no-install-recommends "${PKGS[@]}"
    else
        PKGS=(
            libX11 libXext libXcomposite libXcursor libXfixes libXi libXinerama libXrandr libXrender
            libXxf86vm libxkbcommon vulkan-loader mesa-vulkan-drivers vulkan-tools mesa-libEGL mesa-libGL
            libwayland-client libwayland-egl freetype fontconfig gnutls alsa-lib pulseaudio-libs dbus-libs
            krb5-libs gstreamer1 gstreamer1-plugins-base SDL2 systemd-libs libusb1 cups-libs pcsc-lite-libs libv4l
            python3 p7zip p7zip-plugins rsync curl xz zstd cabextract unzip ImageMagick
            xdg-utils desktop-file-utils libnotify git
            liberation-fonts google-noto-sans-fonts dejavu-sans-fonts
        )
        step "Installing packages (dnf)..."
        sudo dnf install -y "${PKGS[@]}"
    fi
    if lspci 2>/dev/null | grep -Ei 'vga|3d|display' | grep -qi nvidia; then
        warn "NVIDIA GPU: install the proprietary driver with your distribution's tool"
        warn "(Ubuntu: sudo ubuntu-drivers install) - Mesa's Vulkan does not cover it"
    fi
    step "Summary"
    command -v vulkaninfo >/dev/null && info "$(vulkaninfo --summary 2>/dev/null | grep -m3 -E 'deviceName|driverName' | sed 's/^ *//' | tr '\n' ' ')"
    info "Wine: this project's own (scripts/get-wine.sh)"
    exit 0
fi
[ "$INV_DISTRO" = arch ] || die "unsupported distribution (supported: Arch, Debian/Ubuntu, Fedora) - see /etc/os-release"

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
