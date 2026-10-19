#!/bin/bash
# Install this project's Wine: vanilla Wine with the patches in patches/,
# built in public by the "Build Wine" GitHub workflow. It goes to
# ~/.local/share/inventor-on-linux/ - the system's Wine is not touched and no
# sudo is needed. Inventor's scripts use it from then on (INV_WINE=auto).
#
#   bash scripts/get-wine.sh            download the release named in wine/version.env
#   bash scripts/get-wine.sh --build    build it here instead (scripts/build-wine.sh, 1-2 hours)
#   bash scripts/get-wine.sh --remove   remove all of this project's Wine builds
#
# The download is checked against wine/SHA256SUMS (part of this repository),
# so a changed file on the release page is refused.

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

MODE=download
case "${1:-}" in
    "") ;;
    --build) MODE=build ;;
    --remove) MODE=remove ;;
    -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $1 (see --help)" ;;
esac

[ -n "$INV_WINE_VER" ] && [ -n "$INV_WINE_BUILD" ] || die "wine/version.env is missing or incomplete"
DEST="$INV_WINE_HOME/$INV_WINE_NAME"
INV_WINE_URL="${INV_WINE_URL:-https://github.com/Harvi654/Autodesk-Inventor-for-Linux/releases/download}"
TAG="wine-$INV_WINE_VER-$INV_WINE_BUILD"

if [ "$MODE" = remove ]; then
    pgrep -x wineserver >/dev/null && die "Wine is running - close Inventor first (or: wineserver -k)"
    rm -rf "$INV_WINE_HOME"/wine-inventor-*-x86_64
    ok "removed; Inventor's scripts use the system's Wine again"
    exit 0
fi

if [ -x "$DEST/bin/wine" ]; then
    ok "already installed: $DEST ($("$DEST/bin/wine" --version 2>/dev/null))"
    exit 0
fi
mkdir -p "$INV_WINE_HOME"
TMP="$(mktemp -d "$INV_WINE_HOME/.get-wine.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

if [ "$MODE" = build ]; then
    info "building $INV_WINE_NAME from source (1-2 hours)"
    bash "$SCRIPTS_DIR/build-wine.sh" "$TMP"
    TARBALL="$TMP/$INV_WINE_NAME.tar.xz"
else
    TARBALL="$TMP/$INV_WINE_NAME.tar.xz"
    info "downloading $INV_WINE_NAME (~80 MB)"
    curl -fL --retry 3 --progress-bar -o "$TARBALL" "$INV_WINE_URL/$TAG/$INV_WINE_NAME.tar.xz" \
        || die "download failed: $INV_WINE_URL/$TAG/$INV_WINE_NAME.tar.xz
    (no internet, or this Wine build is not published yet - then: bash $0 --build)"
    GOT="$(sha256sum "$TARBALL" | cut -d' ' -f1)"
    if [ -n "$INV_WINE_SHA256" ]; then
        [ "$GOT" = "$INV_WINE_SHA256" ] || die "checksum mismatch - refusing it
    expected $INV_WINE_SHA256 (wine/SHA256SUMS)
    got      $GOT"
        ok "SHA-256 matches wine/SHA256SUMS"
    else
        curl -fsSL --retry 3 -o "$TMP/sum" "$INV_WINE_URL/$TAG/$INV_WINE_NAME.tar.xz.sha256" || die "no checksum file on the release"
        [ "$GOT" = "$(cut -d' ' -f1 "$TMP/sum")" ] || die "checksum mismatch with the release's .sha256 - refusing it"
        warn "checked against the release's own .sha256 only (wine/SHA256SUMS has no entry for it yet)"
    fi
fi

tar -xJf "$TARBALL" -C "$TMP"
[ -x "$TMP/$INV_WINE_NAME/bin/wine" ] || die "unexpected archive layout"
# wine-mono / wine-gecko are in the archive since build 2; for older builds use
# the system's copies when there are some (Arch: wine-mono, wine-gecko).
for c in mono gecko; do
    if [ ! -e "$TMP/$INV_WINE_NAME/share/wine/$c" ] && [ -d "/usr/share/wine/$c" ]; then
        ln -s "/usr/share/wine/$c" "$TMP/$INV_WINE_NAME/share/wine/$c"
    fi
done
mv "$TMP/$INV_WINE_NAME" "$DEST"
ok "installed: $DEST"
"$DEST/bin/wine" --version 2>/dev/null | sed 's/^/    /' || true
OLD="$(ls -d "$INV_WINE_HOME"/wine-inventor-*-x86_64 2>/dev/null | grep -vxF "$DEST" || true)"
[ -z "$OLD" ] || info "older builds still there (remove with: rm -rf $(echo "$OLD" | tr '\n' ' '))"
