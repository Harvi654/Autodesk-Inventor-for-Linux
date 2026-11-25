#!/bin/bash
# Build a complete Wine with this project's patches into a relocatable
# tarball: wine-inventor-<version>-<build>-x86_64.tar.xz (+ .sha256).
#
# The release workflow (.github/workflows/build-wine.yml) runs this in an Arch
# Linux container; you can run it yourself too, to check a release or to build
# without downloading. It does not install anything and needs no sudo.
#
#   bash scripts/build-wine.sh [OUTDIR]          (default OUTDIR: ./dist)
#
# Version: wine/version.env (WINE_VERSION, WINE_BUILD), overridable from the
# environment. Needs Wine's build dependencies (see the workflow for the Arch
# package list), mingw-w64-gcc, about 10 GB of disk and 1-2 hours on 2 cores.
#
# The result is a pure WoW64 Wine (--enable-archs=x86_64,i386, like Arch's own
# package): 64-bit host libraries only. It runs from any directory.

set -euo pipefail
HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
# shellcheck disable=SC1091
source "$HERE/wine/version.env"
WINE_VERSION="${WINE_VER_OVERRIDE:-$WINE_VERSION}"
OUTDIR="$(mkdir -p "${1:-$HERE/dist}" && cd "${1:-$HERE/dist}" && pwd)"
WORK="${WORK:-${XDG_CACHE_HOME:-$HOME/.cache}/inventor-on-linux/wine-build}"
NAME="wine-inventor-$WINE_VERSION-$WINE_BUILD-x86_64"
JOBS="${JOBS:-$(nproc)}"

say() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

for t in curl tar xz patch make x86_64-w64-mingw32-gcc i686-w64-mingw32-gcc bison flex; do
    command -v "$t" >/dev/null || die "missing build tool: $t"
done

mkdir -p "$WORK"
SRC="$WORK/wine-$WINE_VERSION"

say "Wine $WINE_VERSION source"
rm -rf "$SRC"
case "$WINE_VERSION" in *.0|*.0.*) SUB="${WINE_VERSION%%.*}.0" ;; *) SUB="${WINE_VERSION%%.*}.x" ;; esac
TARBALL="${WINE_SOURCE_TARBALL:-$WORK/wine-$WINE_VERSION.tar.xz}"
[ -s "$TARBALL" ] || curl -fL --retry 3 -o "$TARBALL" "https://dl.winehq.org/wine/source/$SUB/wine-$WINE_VERSION.tar.xz"
tar -xf "$TARBALL" -C "$WORK"
[ -f "$SRC/configure" ] || die "unexpected source layout in $TARBALL"
SRC_SHA="$(sha256sum "$TARBALL" | cut -d' ' -f1)"

say "Applying patches/"
# also writes PATCHES.txt and the LGPL change notices (end of each changed file);
# scripts/make-wine-source.sh publishes exactly this tree as the release's source
# shellcheck disable=SC1091
source "$HERE/scripts/lib/wine-patches.sh"
wine_apply_patches "$SRC" "$HERE/patches" "$HERE" HEAD || die "patches do not apply to Wine $WINE_VERSION"
cd "$SRC"

say "Configuring"
mkdir -p build && cd build
../configure --prefix=/usr --libdir=/usr/lib --sysconfdir=/etc \
    --enable-archs=x86_64,i386 --disable-tests \
    --with-x --with-wayland --with-vulkan --with-opengl --with-freetype --with-fontconfig \
    --with-gnutls --with-pulse --with-alsa --with-gstreamer --with-dbus --with-krb5 \
    > "$WORK/configure.log" 2>&1 || { tail -40 "$WORK/configure.log"; die "configure failed"; }
# features Inventor needs - fail loudly instead of shipping a Wine without them
MISSING=""
for D in SONAME_LIBX11 SONAME_LIBXI SONAME_LIBXRANDR SONAME_LIBXRENDER SONAME_LIBXCURSOR \
         SONAME_LIBXCOMPOSITE SONAME_LIBVULKAN SONAME_LIBFREETYPE SONAME_LIBFONTCONFIG \
         SONAME_LIBGNUTLS SONAME_LIBEGL; do
    grep -q "^#define $D " include/config.h || MISSING+=" $D"
done
[ -z "$MISSING" ] || { grep -iE "^configure: (WARNING|error)" "$WORK/configure.log" | head -30; die "Wine would lack:$MISSING"; }

say "Building with $JOBS jobs (this takes a while)"
make -j"$JOBS" > "$WORK/build.log" 2>&1 || { tail -60 "$WORK/build.log"; die "build failed"; }

say "Installing into a staging directory"
STAGE="$WORK/stage"
rm -rf "$STAGE"
make install DESTDIR="$STAGE" > "$WORK/install.log" 2>&1 || { tail -40 "$WORK/install.log"; die "make install failed"; }
ROOT="$WORK/$NAME"
rm -rf "$ROOT"
mv "$STAGE/usr" "$ROOT"
rm -rf "$STAGE" "$ROOT/include" "$ROOT/share/man" "$ROOT/share/applications"
# strip host and PE binaries (several hundred MB less)
find "$ROOT" -type f \( -name '*.so' -o -path '*/bin/*' \) -exec strip --strip-unneeded {} + 2>/dev/null || true
find "$ROOT/lib/wine/x86_64-windows" -type f -exec x86_64-w64-mingw32-strip --strip-unneeded {} + 2>/dev/null || true
find "$ROOT/lib/wine/i386-windows" -type f -exec i686-w64-mingw32-strip --strip-unneeded {} + 2>/dev/null || true

# wine-mono (.NET Framework for Wine) and wine-gecko (HTML engine): Wine would
# otherwise ask to download them into every new prefix. Taken from the build
# system's packages when present (Arch: wine-mono, wine-gecko), like the
# system's Wine would use them.
# Both are free software published by the Wine project, unchanged here; their
# sources are listed in BUILDINFO (LGPL/MPL: say where the source is).
ADDONS=""
for c in mono gecko; do
    if [ -d "/usr/share/wine/$c" ]; then
        cp -a "/usr/share/wine/$c" "$ROOT/share/wine/$c"
        for f in "/usr/share/wine/$c"/*; do
            v="$(basename "$f" | sed -nE 's/^wine-(mono|gecko)-([0-9][0-9.]*[0-9]).*/\2/p')"
            ADDONS+="  $c: $(basename "$f")"$'\n'
            [ -n "$v" ] && ADDONS+="        source https://dl.winehq.org/wine/wine-$c/$v/"$'\n'
        done
        if command -v pacman >/dev/null && pacman -Q "wine-$c" >/dev/null 2>&1; then
            ADDONS+="        from the Arch package $(pacman -Q "wine-$c")"$'\n'
        fi
    fi
done
[ -n "$ADDONS" ] && ADDONS+="  licenses: wine-mono - those of Mono and its parts (mostly MIT), wine-gecko - MPL 2.0"$'\n'

cat > "$ROOT/BUILDINFO" <<INFO
Wine for Autodesk Inventor on Linux
https://github.com/Harvi654/Autodesk-Inventor-for-Linux

name:        $NAME
wine:        $WINE_VERSION (vanilla source, sha256 $SRC_SHA)
build:       $WINE_BUILD
project:     $(git -C "$HERE" rev-parse --short HEAD 2>/dev/null || echo unknown)
built:       $(date -u +%Y-%m-%dT%H:%M:%SZ) on $(. /etc/os-release && echo "$PRETTY_NAME")
configure:   --enable-archs=x86_64,i386 (WoW64)
add-ons (share/wine, unchanged):
${ADDONS:-  none}
patches (sha256 prefix, file; details in PATCHES.txt):
$PATCH_LIST
Wine is licensed under the LGPL 2.1 or later (COPYING.LIB). The complete
source of this build - vanilla Wine with the patches applied, PATCHES.txt and
the build files - is published next to this archive in the same GitHub
release, as wine-inventor-$WINE_VERSION-$WINE_BUILD-source.tar.xz
(made by scripts/make-wine-source.sh). Vanilla Wine: https://dl.winehq.org/wine/source/
INFO
cp "$SRC/COPYING.LIB" "$ROOT/COPYING.LIB"
cp "$SRC/PATCHES.txt" "$ROOT/PATCHES.txt"
# the exact build environment (compilers, libraries), for anyone rebuilding it
if command -v pacman >/dev/null; then pacman -Q > "$ROOT/BUILDENV"
elif command -v dpkg-query >/dev/null; then dpkg-query -W > "$ROOT/BUILDENV"
elif command -v rpm >/dev/null; then rpm -qa | sort > "$ROOT/BUILDENV"; fi

"$ROOT/bin/wine" --version >/dev/null 2>&1 || true   # needs no prefix; just a smoke test of the loader
say "Packing"
tar -C "$WORK" -cJf "$OUTDIR/$NAME.tar.xz" "$NAME"
(cd "$OUTDIR" && sha256sum "$NAME.tar.xz" > "$NAME.tar.xz.sha256")
du -h "$OUTDIR/$NAME.tar.xz" | cut -f1 | xargs printf '    %s  '
echo "$OUTDIR/$NAME.tar.xz"
cat "$OUTDIR/$NAME.tar.xz.sha256"
