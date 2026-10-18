#!/bin/bash
# Make WebView2 render under Wine (App Home page, licensing dialog).
# See webview2_reg in lib/common.sh for what it sets and why.
# rebuild-prefix.sh does this already; use this script for an existing prefix.
#
# Usage: bash scripts/webview2-fix.sh            apply
#        bash scripts/webview2-fix.sh --revert   remove the settings again

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

[ -d "$P_C/windows" ] || die "no prefix at $WINEPREFIX"
wine_stop
if [ "${1:-}" = --revert ]; then
    wine_q reg delete 'HKCU\Software\Wine\AppDefaults\msedgewebview2.exe' /f || true
    wine_q reg delete 'HKLM\Software\Policies\Microsoft\Edge\WebView2' /f || true
    wine_q reg delete 'HKCU\Software\Policies\Microsoft\Edge\WebView2' /f || true
    ok "WebView2 settings removed"
else
    webview2_reg
    ok "WebView2: Windows 7 + wined3d for msedgewebview2.exe, switches: $INV_WEBVIEW2_ARGS (Inventor.exe: $INV_WEBVIEW2_ARGS_INVENTOR)"
fi
wine_stop
