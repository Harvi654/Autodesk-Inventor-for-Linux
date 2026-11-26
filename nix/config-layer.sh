# The configuration layer, separate from Inventor's installation. It holds the
# settings that do not depend on the installed files, so a change here
# rebuilds this small layer and the launcher, never the installation. Where
# the script installer has code for a setting (scripts/lib/common.sh,
# scripts/linux-fonts.sh), this script uses it.
#
# Runs in the layer's build with WINEPREFIX and PROJECT set. PROJECT is a copy
# of the project with scripts/, wine/ and a config.env that names the font
# folders.
set -euo pipefail

: "${WINEPREFIX:?}" "${PROJECT:?}"
export INV_PREFIX="$WINEPREFIX" INV_WINE=system INV_SANDBOX=0 INV_DATA_DIR="" INV_FONTS=linux
# common.sh requires a release, but nothing here depends on it.
export INV_YEAR="${INV_YEAR:-2027}"
set +u
# shellcheck source=../scripts/lib/common.sh
source "$PROJECT/scripts/lib/common.sh"
set -u

# Fonts and family replacements (migration 0001's fonts step).
bash "$PROJECT/scripts/linux-fonts.sh"

# WebView2 under Wine: Windows 7 and wined3d for msedgewebview2.exe, and
# browser switches set by policy (migration 0001's WebView2 step).
webview2_reg

# Migration 0003: the X11 driver for Inventor.exe - GLX, no XRender drawing.
wine_reg_add 'HKCU\Software\Wine\AppDefaults\Inventor.exe\X11 Driver' /v UseEGL /t REG_SZ /d N
wine_reg_add 'HKCU\Software\Wine\AppDefaults\Inventor.exe\X11 Driver' /v ClientSideWithRender /t REG_SZ /d N

# Migration 0011: turn Wine's menu builder off in the prefix itself, not only
# in the launcher's WINEDLLOVERRIDES, so that a plain `wine` in the composed
# prefix does not write menu entries and file associations either.
wine_reg_add 'HKCU\Software\Wine\DllOverrides' /v winemenubuilder.exe /t REG_SZ /d ""

# Font smoothing as on Windows by default: ClearType with RGB subpixels. The
# win32u-font-smoothing patch of winum (since 11.22-3) follows these desktop
# values for normal text such as Tahoma's; Wine's own default is grayscale
# (FontSmoothingType 1).
wine_reg_add 'HKCU\Control Panel\Desktop' /v FontSmoothing /t REG_SZ /d 2
wine_reg_add 'HKCU\Control Panel\Desktop' /v FontSmoothingType /t REG_DWORD /d 2
wine_reg_add 'HKCU\Control Panel\Desktop' /v FontSmoothingOrientation /t REG_DWORD /d 1

wine_stop
test -s "$WINEPREFIX/drive_c/windows/Fonts/NotoSans.ttf"
test -s "$WINEPREFIX/drive_c/windows/Fonts/LiberationSans-Regular.ttf"
test -s "$WINEPREFIX/drive_c/windows/Fonts/DejaVuSans.ttf"
