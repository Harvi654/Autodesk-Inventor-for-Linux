#!/bin/bash
# Complete corresponding source of one of this project's Wine releases
# (LGPL 2.1 sections 4 and 6), as a reproducible archive:
#
#   wine-inventor-<version>-<build>-source.tar.xz  (+ .sha256)
#
#   wine-<version>/          vanilla Wine source + this project's patches, as built,
#                            with PATCHES.txt and the change notices (scripts/lib/wine-patches.sh)
#   inventor-on-linux/       the build files at that release: patches/, wine/version.env,
#                            scripts/build-wine.sh (+ lib), the release workflow
#   README.txt               how to rebuild, where the add-on sources are
#
#   bash scripts/make-wine-source.sh [--ref GITREF] [OUTDIR]     (default: HEAD, ./dist)
#
# GITREF is a commit or tag of this repository, e.g. wine-11.20-6 for the
# source of that release. The archive is reproducible: same ref and same Wine
# source tarball give the same bytes (timestamps from the commit, sorted
# entries, numeric owner 0, single-threaded xz).
#
# The vanilla Wine tarball is downloaded from dl.winehq.org, or taken from
# WINE_SOURCE_TARBALL (a local copy, e.g. the one build-wine.sh cached).

set -euo pipefail
HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
REF=HEAD OUTDIR=""
while [ $# -gt 0 ]; do
    case "$1" in
        --ref) [ $# -ge 2 ] || { echo "--ref needs a value" >&2; exit 2; }; REF="$2"; shift 2 ;;
        -h|--help) sed -n '2,23p' "$0"; exit 0 ;;
        -*) echo "unknown option: $1" >&2; exit 2 ;;
        *) OUTDIR="$1"; shift ;;
    esac
done
say() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
for t in git curl tar xz patch sha256sum sed; do command -v "$t" >/dev/null || die "missing tool: $t"; done

COMMIT="$(git -C "$HERE" rev-parse --verify "$REF^{commit}")" || die "unknown git ref: $REF"
EPOCH="$(git -C "$HERE" log -1 --format=%ct "$COMMIT")"
OUTDIR="$(mkdir -p "${OUTDIR:-$HERE/dist}" && cd "${OUTDIR:-$HERE/dist}" && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/wine-source.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

say "Build files at $REF ($(git -C "$HERE" rev-parse --short "$COMMIT"))"
EXP="$WORK/inventor-on-linux"
mkdir -p "$EXP"
paths=()
for p in patches wine/version.env scripts/build-wine.sh scripts/lib/wine-patches.sh \
         scripts/make-wine-source.sh .github/workflows/build-wine.yml LICENSE; do
    git -C "$HERE" cat-file -e "$COMMIT:$p" 2>/dev/null && paths+=("$p")
done
git -C "$HERE" archive --format=tar "$COMMIT" -- "${paths[@]}" | tar -x -C "$EXP"
# subdirectories of patches/ (debug, drafts, libgsf) are not part of the Wine build
find "$EXP/patches" -mindepth 1 -maxdepth 1 -type d -exec rm -rf {} +
# shellcheck disable=SC1091
source "$EXP/wine/version.env"
[ -n "${WINE_VERSION:-}" ] && [ -n "${WINE_BUILD:-}" ] || die "no WINE_VERSION/WINE_BUILD at $REF"
NAME="wine-inventor-$WINE_VERSION-$WINE_BUILD-source"

say "Wine $WINE_VERSION source"
case "$WINE_VERSION" in *.0|*.0.*) SUB="${WINE_VERSION%%.*}.0" ;; *) SUB="${WINE_VERSION%%.*}.x" ;; esac
URL="https://dl.winehq.org/wine/source/$SUB/wine-$WINE_VERSION.tar.xz"
TARBALL="${WINE_SOURCE_TARBALL:-$WORK/wine-$WINE_VERSION.tar.xz}"
[ -s "$TARBALL" ] || curl -fL --retry 3 -o "$TARBALL" "$URL"
SRC_SHA="$(sha256sum "$TARBALL" | cut -d' ' -f1)"
STAGE="$WORK/stage"
mkdir -p "$STAGE"
tar -xf "$TARBALL" -C "$STAGE"
SRC="$STAGE/wine-$WINE_VERSION"
[ -f "$SRC/configure" ] || die "unexpected source layout in $TARBALL (expected wine-$WINE_VERSION/configure)"

say "Applying patches from $REF"
# shellcheck disable=SC1091
source "$HERE/scripts/lib/wine-patches.sh"
wine_apply_patches "$SRC" "$EXP/patches" "$HERE" "$COMMIT"

mv "$EXP" "$STAGE/inventor-on-linux"
has_notices=yes
git -C "$HERE" cat-file -e "$COMMIT:scripts/lib/wine-patches.sh" 2>/dev/null || has_notices=no
cat > "$STAGE/README.txt" <<INFO
Source of the Wine release wine-$WINE_VERSION-$WINE_BUILD of Autodesk-Inventor-for-Linux
https://github.com/Harvi654/Autodesk-Inventor-for-Linux (commit $COMMIT)

wine-$WINE_VERSION/
    Wine $WINE_VERSION, the official source tarball
    $URL
    (sha256 $SRC_SHA), with this project's patches applied.
    PATCHES.txt lists every patch, its date and the files it changes; the
    changed source files carry a short comment at their end that says so.
    License: GNU LGPL 2.1 or later, see wine-$WINE_VERSION/COPYING.LIB.

inventor-on-linux/
    The build files of this release: patches/*.patch, wine/version.env and
    scripts/build-wine.sh (the release was built by .github/workflows/build-wine.yml
    in an archlinux:base-devel container; the BUILDENV file in the binary
    release lists the exact build packages).

To rebuild: install Wine's build dependencies and mingw-w64, then
    cd inventor-on-linux && WINE_SOURCE_TARBALL=/path/to/wine-$WINE_VERSION.tar.xz bash scripts/build-wine.sh
or build wine-$WINE_VERSION/ as it is here, with the configure options from
inventor-on-linux/scripts/build-wine.sh (WoW64: --enable-archs=x86_64,i386).

The binary release also contains wine-mono and wine-gecko, unchanged, from
Arch Linux's wine-mono and wine-gecko packages (versions: share/wine/ and
BUILDINFO of the binary release). Their sources are published by the Wine
project next to the binaries:
    https://dl.winehq.org/wine/wine-mono/<version>/   (wine-mono-<version>-src.tar.xz)
    https://dl.winehq.org/wine/wine-gecko/<version>/  (wine-gecko-<version>-src.tar.xz)
INFO
if [ "$has_notices" = no ]; then
    cat >> "$STAGE/README.txt" <<INFO

Note: this release was built before the change notices were added to the
build. The only difference between this source and the one compiled for the
binary are the comments appended at the end of the changed files and
PATCHES.txt.
INFO
fi

say "Packing $NAME.tar.xz"
tar -C "$STAGE" --sort=name --mtime="@$EPOCH" --owner=0 --group=0 --numeric-owner \
    --pax-option=exthdr.name=%d/PaxHeaders/%f,delete=atime,delete=ctime \
    --transform "s#^#$NAME/#" -cf - README.txt "wine-$WINE_VERSION" inventor-on-linux \
    | xz -T1 -6 > "$OUTDIR/$NAME.tar.xz"
(cd "$OUTDIR" && sha256sum "$NAME.tar.xz" > "$NAME.tar.xz.sha256")
du -h "$OUTDIR/$NAME.tar.xz" | cut -f1 | xargs printf '    %s  '
echo "$OUTDIR/$NAME.tar.xz"
cat "$OUTDIR/$NAME.tar.xz.sha256"
