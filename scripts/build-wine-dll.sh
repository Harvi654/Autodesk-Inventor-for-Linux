#!/bin/bash
# Build one Wine DLL with this project's patch for the INSTALLED Wine version,
# and optionally install it system-wide (original backed up).
#
# Usage: bash scripts/build-wine-dll.sh DLL [--install] [--hook] [--restore] [--test]
#   DLL         wbemprox  - Win32_TimeZone class (patches/wbemprox-timezone.patch)
#               shell32   - IShellItemImageFactory::GetImage: file icons and thumbnails
#                           instead of an empty 1x1 bitmap (patches/shell32-getimage.patch);
#                           IFolderView2 selection methods, double-click in Inventor's
#                           Open/Place dialog (patches/shell32-folderview-selection.patch)
#               oleaut32  - MSFT typelib: pointer to a simple type with VT_ARRAY
#                           (or out of range) indexed past std_typedesc -> garbage
#                           parameter type, IDispatch calls fail with E_INVALIDARG
#                           (Design Accelerator shaft, patches/oleaut32-typedesc-pointee.patch);
#                           --diag adds detail when ITypeInfo::Invoke can't convert a parameter
#               msi       - transforms: a row whose binary (stream) field is NULL
#                           was dropped; MSP updates lose their Patch rows that
#                           use MsiPatchHeaders -> files not updated
#                           (patches/msi-transform-null-stream.patch)
#               mspatcha  - delta patches of files larger than the LZXD window
#                           (8 MB) failed: "interleaved LZXD decompression is not
#                           supported" (patches/mspatcha-large-old-file.patch)
#               All patches/DLL-*.patch are applied; with --diag also
#               patches/debug/DLL-*.patch (diagnostic output, not for upstream).
#   --install   copy the built DLL over the system one (sudo, original backed up)
#   --hook      add a pacman hook that reminds you to rerun this after Wine updates
#   --restore   put the original system DLL back
#   --diag      include the diagnostic patches from patches/debug/
#   --test      also build the DLL's Wine tests and run the patched test file
#               (in a throw-away prefix; run after --install)
#
# Needs: mingw-w64-gcc flex bison (scripts/phase0-setup.sh installs them)

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

DLL="${1:-}"; shift || true
case "$DLL" in
    wbemprox) CHECK=Win32_TimeZone;  TEST=query ;;
    shell32)  CHECK='supports neither IInitializeWithStream'; TEST=shlfolder ;;
    oleaut32) CHECK='pointee index %lu out of range'; TEST=typelib ;;
    kernelbase) CHECK=''; TEST=security; TESTDLL=advapi32 ;;
    riched20) CHECK='paragraph needs rewrap'; TEST=editor ;;
    msi)      CHECK='no stream, NULL'; TEST=patch ;;
    mspatcha) CHECK='old file larger than the window'; TEST=apply_patch ;;
    *) die "usage: $0 wbemprox|shell32|oleaut32|kernelbase|riched20|msi|mspatcha [--install] [--hook] [--restore] [--diag] [--test]" ;;
esac

DO_INSTALL=0; DO_HOOK=0; DO_RESTORE=0; DO_TEST=0; DO_DIAG=0
for a in "$@"; do
    case "$a" in
        --install) DO_INSTALL=1 ;; --hook) DO_HOOK=1 ;; --restore) DO_RESTORE=1 ;; --test) DO_TEST=1 ;; --diag) DO_DIAG=1 ;;
        *) die "unknown option: $a" ;;
    esac
done

WV="$(wine_version)"; [ -n "$WV" ] || die "wine not installed"
PE_DIR="$(wine_pe_dir)"; [ -n "$PE_DIR" ] || die "can't find Wine's PE DLL directory"
SYS_DLL="$PE_DIR/$DLL.dll"
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
    warn "you run wine-staging; building $DLL from vanilla $WV source"
fi

step "Applying patches/$DLL-*.patch..."
cd "$SRC"
shopt -s nullglob
# Without --diag, take diagnostic patches from an earlier --diag build out
# again (newest first; they sit on top of the real patches).
if [ "$DO_DIAG" -eq 0 ]; then
    DIAG=("$PROJECT_DIR/patches/debug/$DLL-"*.patch)
    for ((k = ${#DIAG[@]} - 1; k >= 0; k--)); do
        if patch -p1 -R --dry-run -s -f < "${DIAG[k]}" >/dev/null 2>&1; then
            patch -p1 -R -s < "${DIAG[k]}" && ok "removed diagnostic $(basename "${DIAG[k]}")"
        fi
    done
fi
PATCHES=("$PROJECT_DIR/patches/$DLL-"*.patch)
[ "$DO_DIAG" -eq 1 ] && PATCHES+=("$PROJECT_DIR/patches/debug/$DLL-"*.patch)
shopt -u nullglob
[ ${#PATCHES[@]} -gt 0 ] || die "no patches for $DLL (diagnostic ones need --diag)"
for PATCH in "${PATCHES[@]}"; do
    if patch -p1 -R --dry-run -s -f < "$PATCH" >/dev/null 2>&1; then
        ok "$(basename "$PATCH") already applied"
    else
        patch -p1 -s < "$PATCH" || die "$(basename "$PATCH") does not apply to Wine $WV - please open an issue"
        ok "$(basename "$PATCH") applied"
    fi
done

step "Configuring (minimal, PE x86_64 only)..."
if [ ! -f Makefile ]; then
    ./configure --enable-archs=x86_64 \
        --without-x --without-freetype --without-fontconfig --without-gstreamer --without-vulkan \
        --without-opengl --without-alsa --without-pulse --without-cups --without-dbus --without-usb \
        --without-v4l2 --without-wayland --without-gnutls --without-krb5 --without-sdl --without-ffmpeg \
        --without-pcap --without-netapi --without-sane --without-gphoto --without-udev \
        > "$LOGDIR/wine-configure.log" 2>&1 || die "configure failed, see $LOGDIR/wine-configure.log"
fi
ok "configured"

step "Building dlls/$DLL..."
make -j"$(nproc)" -C "dlls/$DLL" > "$LOGDIR/$DLL-build.log" 2>&1 \
    || die "build failed, see $LOGDIR/$DLL-build.log"
BUILT="$SRC/dlls/$DLL/x86_64-windows/$DLL.dll"
[ -z "$CHECK" ] || { strings -a "$BUILT"; strings -a -el "$BUILT"; } | grep -cF "$CHECK" >/dev/null || die "built DLL lacks the patch?!"
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

if [ "$DO_TEST" -eq 1 ]; then
    info "building and running Wine's $DLL:$TEST tests in a throw-away prefix..."
    make -j"$(nproc)" -C "dlls/${TESTDLL:-$DLL}/tests" > "$LOGDIR/$DLL-tests-build.log" 2>&1 \
        || die "test build failed, see $LOGDIR/$DLL-tests-build.log"
    TP="$(mktemp -d)"
    WINEPREFIX="$TP" WINEDEBUG=-all wineboot -i >/dev/null 2>&1 || true
    WINEPREFIX="$TP" WINEDEBUG=-all wine "dlls/${TESTDLL:-$DLL}/tests/x86_64-windows/${TESTDLL:-$DLL}_test.exe" "$TEST" \
        > "$LOGDIR/$DLL-test.log" 2>&1 || true
    WINEPREFIX="$TP" wineserver -k 2>/dev/null || true
    rm -rf "$TP"
    tail -1 "$LOGDIR/$DLL-test.log"
    grep -a 'Test failed' "$LOGDIR/$DLL-test.log" | head -10 || true
    info "full output: $LOGDIR/$DLL-test.log"
fi

if [ "$DO_HOOK" -eq 1 ]; then
    HOOK="/etc/pacman.d/hooks/inventor-$DLL.hook"
    sudo mkdir -p /etc/pacman.d/hooks
    sudo tee "$HOOK" >/dev/null <<EOF
[Trigger]
Operation = Install
Operation = Upgrade
Type = Package
Target = wine
Target = wine-staging

[Action]
Description = Inventor: Wine changed - patched $DLL.dll was replaced
When = PostTransaction
Exec = /usr/bin/sh -c 'echo ">>> Rerun: bash \"$SCRIPTS_DIR/build-wine-dll.sh\" $DLL --install"'
EOF
    ok "pacman hook: $HOOK"
fi
