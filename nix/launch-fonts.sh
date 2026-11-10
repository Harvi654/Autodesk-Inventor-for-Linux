# Runs in the composed prefix. Real Tahoma's small-size GASP instructions can
# disable grayscale smoothing in Wine. Prefer Segoe UI for system menu/status
# fonts only when the real family is available; Wine's replacement aliases and
# fc-match's fallback are not evidence that Segoe UI is installed.
inventor_has_segoe() {
    {
        fc-list --format '%{family}\n' ':family=Segoe UI'
        fc-scan --format '%{family}\n' "$WINEPREFIX/drive_c/windows/Fonts" 2>/dev/null || true
    } | tr ',' '\n' | grep -Fx 'Segoe UI' >/dev/null
}

inventor_font_key='HKLM\Software\Microsoft\Windows NT\CurrentVersion\FontSubstitutes'
if ! inventor_tahoma=$(wine reg query "$inventor_font_key" /v Tahoma 2>/dev/null); then
    inventor_tahoma=""
fi
if inventor_has_segoe; then
    # Leave explicit user substitutions to other families intact.
    if [ -z "$inventor_tahoma" ]; then
        wine reg add "$inventor_font_key" /v Tahoma /t REG_SZ /d 'Segoe UI' /f || exit 1
    fi
elif printf '%s\n' "$inventor_tahoma" |
        grep -Eq '^[[:space:]]*Tahoma[[:space:]]+REG_SZ[[:space:]]+Segoe UI[[:space:]]*$'; then
    # A Windows mount or user font may have disappeared since the last launch.
    wine reg delete "$inventor_font_key" /v Tahoma /f || exit 1
fi
unset inventor_font_key inventor_tahoma
unset -f inventor_has_segoe
