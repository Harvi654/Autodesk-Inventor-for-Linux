#!/bin/bash
# Build wbemprox.dll with the Win32_TimeZone patch for the INSTALLED Wine
# version, and optionally install it system-wide.
#
# Usage: bash scripts/build-wbemprox.sh [--install] [--hook] [--restore]
#   --install   copy the built DLL over the system one (sudo, original backed up)
#   --hook      add a pacman hook that reminds you to rerun this after Wine updates
#   --restore   put the original system wbemprox.dll back
#
# Needs: mingw-w64-gcc flex bison (scripts/phase0-setup.sh installs them)

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

DO_INSTALL=0; DO_HOOK=0; DO_RESTORE=0
for a in "$@"; do
    case "$a" in
        --install) DO_INSTALL=1 ;; --hook) DO_HOOK=1 ;; --restore) DO_RESTORE=1 ;;
        *) die "unknown option: $a" ;;
    esac
done

PATCH="$PROJECT_DIR/patches/wbemprox-timezone.patch"
WV="$(wine_version)"; [ -n "$WV" ] || die "wine not installed"
PE_DIR="$(wine_pe_dir)"; [ -n "$PE_DIR" ] || die "can't find the system wbemprox.dll"
SYS_DLL="$PE_DIR/wbemprox.dll"
BACKUP="$SYS_DLL.orig-$WV"

if [ "$DO_RESTORE" -eq 1 ]; then
    [ -f "$BACKUP" ] || die "no backup for Wine $WV at $BACKUP (reinstall the wine package instead)"
    sudo cp "$BACKUP" "$SYS_DLL"; ok "restored $SYS_DLL"; exit 0
fi

SRC_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/inventor-on-linux"
SRC="$SRC_ROOT/wine-$WV"
_STEPS=5

step "Wine $WV source..."
if [ ! -d "$SRC" ]; then
    mkdir -p "$SRC_ROOT"
    # x.0 / x.0.y are stable releases, everything else is a development release
    case "$WV" in *.0|*.0.*) SUB="${WV%%.*}.0" ;; *) SUB="${WV%%.*}.x" ;; esac
    URL="https://dl.winehq.org/wine/source/$SUB/wine-$WV.tar.xz"
    info "downloading $URL"
    if curl -fL --retry 3 -o "$SRC_ROOT/wine-$WV.tar.xz" "$URL"; then
        tar -xf "$SRC_ROOT/wine-$WV.tar.xz" -C "$SRC_ROOT" && rm -f "$SRC_ROOT/wine-$WV.tar.xz"
    else
        info "tarball not available, trying git tag wine-$WV"
        git clone --depth 1 --branch "wine-$WV" https://gitlab.winehq.org/wine/wine.git "$SRC"
    fi
fi
ok "$SRC"
if wine --version | grep -ci staging >/dev/null; then
    warn "you run wine-staging; building wbemprox from vanilla $WV source (staging rarely touches wbemprox)"
fi

step "Applying Win32_TimeZone patch..."
cd "$SRC"
if patch -p1 -R --dry-run -s -f < "$PATCH" >/dev/null 2>&1; then
    ok "already applied"
else
    patch -p1 -s < "$PATCH" || die "patch does not apply to Wine $WV - please open an issue"
    ok "applied"
fi

step "Configuring (minimal, PE x86_64 only)..."
if [ ! -f Makefile ]; then
    ./configure --enable-archs=x86_64 \
        --without-x --without-freetype --without-fontconfig --without-gstreamer --without-vulkan \
        --without-opengl --without-alsa --without-pulse --without-cups --without-dbus --without-usb \
        --without-v4l2 --without-wayland --without-gnutls --without-krb5 --without-sdl --without-ffmpeg \
        --without-pcap --without-netapi --without-sane --without-gphoto --without-udev \
        > "$LOGDIR/wbemprox-configure.log" 2>&1 || die "configure failed, see $LOGDIR/wbemprox-configure.log"
fi
ok "configured"

step "Building dlls/wbemprox..."
make -j"$(nproc)" -C dlls/wbemprox > "$LOGDIR/wbemprox-build.log" 2>&1 \
    || die "build failed, see $LOGDIR/wbemprox-build.log"
BUILT="$SRC/dlls/wbemprox/x86_64-windows/wbemprox.dll"
strings -el "$BUILT" | grep -cx Win32_TimeZone >/dev/null || die "built DLL has no Win32_TimeZone?!"
ok "$BUILT"

step "Install..."
if [ "$DO_INSTALL" -eq 1 ]; then
    [ -f "$BACKUP" ] || sudo cp "$SYS_DLL" "$BACKUP"
    sudo cp "$BUILT" "$SYS_DLL"
    ok "installed to $SYS_DLL (original: $BACKUP)"
    info "Wine loads builtin DLLs from that directory, so prefixes use it on their next start."
else
    info "not installed (rerun with --install)"
fi

if [ "$DO_HOOK" -eq 1 ]; then
    HOOK=/etc/pacman.d/hooks/inventor-wbemprox.hook
    sudo mkdir -p /etc/pacman.d/hooks
    sudo tee "$HOOK" >/dev/null <<EOF
[Trigger]
Operation = Install
Operation = Upgrade
Type = Package
Target = wine
Target = wine-staging

[Action]
Description = Inventor: Wine changed - patched wbemprox.dll (Win32_TimeZone) was replaced
When = PostTransaction
Exec = /usr/bin/sh -c 'echo ">>> Rerun: bash \"$SCRIPTS_DIR/build-wbemprox.sh\" --install"'
EOF
    ok "pacman hook: $HOOK"
fi
