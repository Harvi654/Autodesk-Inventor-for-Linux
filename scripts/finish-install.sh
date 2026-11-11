#!/bin/bash
# Make a prefix that install-from-image.py filled ready to run Inventor:
# the same Wine-specific setup rebuild-prefix.sh does, without copying
# anything from a Windows installation (Autodesk's installers already put
# the files and registry entries in place).
#
# Usage: INV_PREFIX=~/.wine-invtest bash scripts/finish-install.sh [--data-dir PATH] [--no-sandbox]
#
# Fonts: free Linux fonts with replacements for the Windows families
# (linux-fonts.sh). INV_FONTS=windows copies them from a mounted Windows
# partition at WIN_ROOT instead (windows-fonts.sh).

set -Eeuo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"
source "$COMMON_DIR/configure.sh"
trap 'err "failed at line $LINENO: $BASH_COMMAND (see $LOGDIR/setup-wine.log)"' ERR

while [ $# -gt 0 ]; do
    case "$1" in
        --data-dir) INV_DATA_DIR="$2"; shift ;;
        --no-sandbox) INV_SANDBOX=0 ;;
        *) die "unknown option: $1" ;;
    esac
    shift
done
: > "$LOGDIR/setup-wine.log"
_STEPS=13

step "Checking the installation in $WINEPREFIX..."
if [ ! -f "$P_INV/Bin/Inventor.exe" ]; then
    _other="$(inventor_year_in_prefix "$WINEPREFIX")"
    [ -z "$_other" ] || die "$WINEPREFIX holds Inventor $_other, not Inventor $INV_YEAR - run again with INV_YEAR=$_other"
    die "no Inventor in $P_INV - run install-from-image.py first"
fi
[ "$(readlink -f "$WINEPREFIX")" != "$(readlink -f "$HOME/.wine-inventor$INV_YEAR")" ] \
    || [ "${INV_FINISH_MAIN:-0}" = 1 ] \
    || die "this is your working prefix - set INV_FINISH_MAIN=1 if you really mean it"
wine_stop

# Everything else is the prefix migrations (scripts/lib/migrations/): the
# base setup (0001, which this script runs again every time) and the steps
# this prefix has not had yet.
source "$COMMON_DIR/migrations.sh"
run_migrations --with-base || die "prefix setup stopped - see above"
wine --version > "$WINEPREFIX/.inventor-wine-version"

echo
ok "Prefix ready: $WINEPREFIX ($(du -sh "$WINEPREFIX" | cut -f1))"
info "Start it with: INV_PREFIX=$WINEPREFIX bash scripts/launch-inventor.sh"
