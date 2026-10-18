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
#               mspatcha  - delta patches of 32-bit PE files (.NET assemblies) and
#                           of files larger than the LZXD window (8 MB) - needed
#                           by Autodesk's MSP updates
#                           (patches/mspatcha-pa19-32bit-and-large-files.patch)
#               comctl32  - TB_SETROWS keeps its wrap points on a TBSTYLE_WRAPABLE
#                           toolbar, so the symbol palette of the dimension text
#                           editor is a grid, not one column
#                           (patches/comctl32-toolbar-setrows-wrapable.patch)
#               server    - wineserver, not a DLL: a mouse move for the window under
#                           the cursor when a window is shown or hidden (Windows does
#                           this; Inventor redraws the sketch after a dimension edit
#                           only on a mouse move) (patches/server-mousemove-on-show-hide.patch)
#                           Close all Wine programs before --install.
#               winex11   - X11 driver (native winex11.so): windows shaped with SetWindowRgn
#                           get an ARGB visual under Xwayland and transparent pixels
#                           outside the shape - Xwayland ignores the X shape, so
#                           Inventor's sketch input boxes sat on a black rectangle
#                           (patches/winex11-shape-alpha-xwayland.patch); raw mouse
#                           buttons from a device XInput 1 cannot query (Xwayland,
#                           XI_BadDevice) no longer kill the process - crash on the
#                           Hole command (patches/winex11-xinput-bad-device.patch). Built in a
#                           separate source tree configured with X11 and Vulkan
#                           (needs vulkan-headers). Close all Wine programs before --install.
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
    server)   CHECK=''; TEST='' ;;
    winex11)  CHECK='shaped window under Xwayland'; TEST='' ;;
    comctl32) CHECK=''; TEST=toolbar ;;
    *) die "usage: $0 wbemprox|shell32|oleaut32|kernelbase|riched20|msi|mspatcha|server|winex11|comctl32 [--install] [--hook] [--restore] [--diag] [--test]" ;;
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
if [ "$DLL" = server ]; then
    # wineserver is a native program next to the wine binary, not a PE DLL
    SYS_DLL="$(readlink -f "$(command -v wineserver)")"; [ -x "$SYS_DLL" ] || die "can't find wineserver"
elif [ "$DLL" = winex11 ]; then
    # the X11 driver's code is the native winex11.so, next to the PE directory
    SYS_DLL="$(dirname "$PE_DIR")/x86_64-unix/winex11.so"; [ -f "$SYS_DLL" ] || die "can't find $SYS_DLL"
fi
BACKUP="$SYS_DLL.orig-$WV"

if [ "$DO_RESTORE" -eq 1 ]; then
    [ -f "$BACKUP" ] || die "no backup for Wine $WV at $BACKUP (reinstall the wine package instead)"
    sudo install -m 755 "$BACKUP" "$SYS_DLL"; ok "restored $SYS_DLL"; exit 0
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

if [ "$DLL" = winex11 ]; then
    # the main tree is configured without X11; build the driver in its own
    # copy of the source, configured like a full Wine (X11, Vulkan, OpenGL)
    [ -x "$SRC/tools/winebuild/winebuild" ] || die "build any PE DLL first (e.g. $0 msi), the X11 tree reuses its tools"
    TOOLS="$SRC"
    SRC="$SRC_ROOT/wine-$WV-x11"
    if [ ! -d "$SRC" ]; then
        info "copying the source to $SRC"
        mkdir -p "$SRC"
        cp -a "$TOOLS/." "$SRC/"
        (cd "$SRC" && make distclean >/dev/null 2>&1) || true
        # take this project's patches to other DLLs out again (they live in the main tree)
        for P in "$PROJECT_DIR"/patches/*.patch; do
            patch -p1 -R --dry-run -s -f -d "$SRC" < "$P" >/dev/null 2>&1 && patch -p1 -R -s -d "$SRC" < "$P"
        done
    fi
    [ -f /usr/include/vulkan/vulkan.h ] || die "needs Vulkan headers: sudo pacman -S --needed vulkan-headers"
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
# Untouched copies of the files the patches change: from the main tree for
# winex11 (never patched there), otherwise from Wine's git for this version.
restore_pristine() {
    local F
    for F in $(sed -n 's|^+++ b/||p' "${PATCHES[@]}" | sort -u); do
        if [ "$DLL" = winex11 ]; then
            cp -f "$TOOLS/$F" "$F"
        else
            curl -fsSL --retry 3 -o "$F.pristine" \
                "https://gitlab.winehq.org/wine/wine/-/raw/wine-$WV/$F" \
                || die "could not download the original $F of Wine $WV"
            mv -f "$F.pristine" "$F"
        fi
    done
    find dlls server \( -name '*.rej' -o -name '*.orig' \) -delete 2>/dev/null || true
}
NEED_RESET=0
for PATCH in "${PATCHES[@]}"; do
    if patch -p1 -R --dry-run -s -f < "$PATCH" >/dev/null 2>&1; then
        ok "$(basename "$PATCH") already applied"
    elif patch -p1 --dry-run -s -f < "$PATCH" >/dev/null 2>&1; then
        patch -p1 -s < "$PATCH"
        ok "$(basename "$PATCH") applied"
    else
        NEED_RESET=1; break
    fi
done
if [ "$NEED_RESET" -eq 1 ]; then
    # an older version of a patch is applied: start again from the originals
    info "a patch changed since the last build - restoring the original files"
    restore_pristine
    for PATCH in "${PATCHES[@]}"; do
        patch -p1 -s < "$PATCH" || die "$(basename "$PATCH") does not apply to Wine $WV - please open an issue"
        ok "$(basename "$PATCH") applied"
    done
fi

if [ "$DLL" = winex11 ]; then
step "Configuring (X11, Vulkan, OpenGL)..."
if [ ! -f Makefile ]; then
    ./configure --with-wine-tools="$TOOLS" --enable-archs=x86_64 \
        --without-gstreamer --without-cups --without-sane --without-gphoto --without-pcap \
        --without-netapi --without-krb5 --without-v4l2 --without-capi --without-pcsclite \
        --without-ffmpeg --without-sdl --without-usb --without-alsa --without-pulse --without-oss \
        > "$LOGDIR/wine-x11-configure.log" 2>&1 || die "configure failed, see $LOGDIR/wine-x11-configure.log"
fi
MISSING=""
for D in SONAME_LIBX11 HAVE_LIBXSHAPE HAVE_LIBXXSHM SONAME_LIBXCOMPOSITE SONAME_LIBXI SONAME_LIBXRANDR \
         SONAME_LIBXRENDER SONAME_LIBXCURSOR SONAME_LIBXFIXES SONAME_LIBXEXT SONAME_LIBVULKAN; do
    grep -q "^#define $D " include/config.h || MISSING="$MISSING $D"
done
[ -z "$MISSING" ] || die "the X11 driver would lack:$MISSING - see $LOGDIR/wine-x11-configure.log (missing -devel/headers?)"
ok "configured"
else
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
fi

if [ "$DLL" = server ]; then
    step "Building wineserver..."
    make -j"$(nproc)" -C server > "$LOGDIR/$DLL-build.log" 2>&1 \
        || die "build failed, see $LOGDIR/$DLL-build.log"
    BUILT="$SRC/server/wineserver"
elif [ "$DLL" = winex11 ]; then
    step "Building dlls/winex11.drv..."
    make -j"$(nproc)" -C dlls/winex11.drv > "$LOGDIR/$DLL-build.log" 2>&1 \
        || die "build failed, see $LOGDIR/$DLL-build.log"
    BUILT="$SRC/dlls/winex11.drv/winex11.so"
else
step "Building dlls/$DLL..."
make -j"$(nproc)" -C "dlls/$DLL" > "$LOGDIR/$DLL-build.log" 2>&1 \
    || die "build failed, see $LOGDIR/$DLL-build.log"
BUILT="$SRC/dlls/$DLL/x86_64-windows/$DLL.dll"
fi
[ -z "$CHECK" ] || { strings -a "$BUILT"; strings -a -el "$BUILT"; } | grep -cF "$CHECK" >/dev/null || die "built DLL lacks the patch?!"
ok "$BUILT"

step "Install..."
if [ "$DO_INSTALL" -eq 1 ]; then
    if cmp -s "$BUILT" "$SYS_DLL"; then
        ok "already installed: $SYS_DLL"
        DO_INSTALL=2
    fi
fi
if [ "$DO_INSTALL" -eq 1 ]; then
    if { [ "$DLL" = server ] || [ "$DLL" = winex11 ]; } && pgrep -x wineserver >/dev/null; then
        die "a wineserver is running - close Inventor and all Wine programs (or: wineserver -k) and rerun"
    fi
    [ -f "$BACKUP" ] || sudo cp "$SYS_DLL" "$BACKUP"
    sudo install -m 755 "$BUILT" "$SYS_DLL"
    ok "installed to $SYS_DLL (original: $BACKUP)"
    info "Wine loads builtin DLLs from that directory, so prefixes use it on their next start."
elif [ "$DO_INSTALL" -eq 0 ]; then
    info "not installed (rerun with --install)"
fi

if [ "$DO_TEST" -eq 1 ] && [ -z "$TEST" ]; then
    warn "no Wine test set up for $DLL"
elif [ "$DO_TEST" -eq 1 ]; then
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
    # one hook for all parts (older versions made one per DLL)
    HOOK=/etc/pacman.d/hooks/inventor-wine.hook
    sudo mkdir -p /etc/pacman.d/hooks
    sudo rm -f /etc/pacman.d/hooks/inventor-{wbemprox,shell32,oleaut32,kernelbase,riched20,msi,mspatcha,server,winex11,comctl32}.hook
    sudo tee "$HOOK" >/dev/null <<EOF
[Trigger]
Operation = Install
Operation = Upgrade
Type = Package
Target = wine
Target = wine-staging

[Action]
Description = Inventor: Wine was updated, so its fixes were replaced
When = PostTransaction
Exec = /usr/bin/sh -c 'echo ">>> Before starting Inventor run: bash \"$SCRIPTS_DIR/rebuild-wine-fixes.sh\""'
EOF
    ok "pacman hook: $HOOK"
fi
