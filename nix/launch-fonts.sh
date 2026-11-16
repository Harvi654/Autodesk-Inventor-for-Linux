# Runs in the composed prefix after launch-lock.sh ($inventor_state_dir).
#
# Small Tahoma UI text is drawn without smoothing in Wine unless ClearType is
# in effect: Tahoma's gasp table turns greyscale off up to 16 ppem, and Wine,
# like Windows, applies that only to greyscale. Windows' default is ClearType,
# but Wine takes each face's smoothing type from fontconfig first, so a host
# with rgba "none" (or unset) gets greyscale whatever the prefix says. When the
# prefix asks for ClearType, give Wine a fontconfig file that sets rgba from
# the prefix's orientation. The host's own fontconfig is included unchanged.
inventor_desktop_key='HKCU\Control Panel\Desktop'
inventor_font_key='HKLM\Software\Microsoft\Windows NT\CurrentVersion\FontSubstitutes'
inventor_font_marker="$inventor_state_dir/font-smoothing-cleartype"

inventor_desktop=$(wine reg query "$inventor_desktop_key" 2>/dev/null || true)
inventor_desktop_value() {
    # wine reg prints CRLF line ends
    printf '%s\n' "$inventor_desktop" | awk -v name="$1" '{ sub(/\r$/, "") } $1 == name { print $3 }'
}
inventor_smoothing=$(inventor_desktop_value FontSmoothing)
inventor_smoothing_type=$(inventor_desktop_value FontSmoothingType)

# Once per release state: make ClearType the default, as on Windows (fresh Wine
# prefixes start with greyscale), and drop the former Tahoma=Segoe UI
# substitution this launcher added. A later change by the user is kept.
if [ ! -e "$inventor_font_marker" ]; then
    case "$inventor_smoothing_type" in
        0x2|2) ;;
        *)
            wine reg add "$inventor_desktop_key" /v FontSmoothingType /t REG_DWORD /d 2 /f || exit 1
            inventor_smoothing_type=0x2
            ;;
    esac
    if wine reg query "$inventor_font_key" /v Tahoma 2>/dev/null |
            grep -Eq '^[[:space:]]*Tahoma[[:space:]]+REG_SZ[[:space:]]+Segoe UI[[:space:]]*$'; then
        wine reg delete "$inventor_font_key" /v Tahoma /f || exit 1
    fi
    : > "$inventor_font_marker" || exit 1
fi

case "$inventor_smoothing:$inventor_smoothing_type" in
    0:*) ;;                                     # smoothing turned off
    *:0x2|*:2)
        case "$(inventor_desktop_value FontSmoothingOrientation)" in
            0x0|0) inventor_rgba=bgr ;;
            *) inventor_rgba=rgb ;;
        esac
        inventor_fc_conf="$inventor_state_dir/fonts-subpixel.conf"
        inventor_fc_base=${FONTCONFIG_FILE:-/etc/fonts/fonts.conf}
        [ "$inventor_fc_base" = "$inventor_fc_conf" ] && inventor_fc_base=/etc/fonts/fonts.conf
        if [ -r "$inventor_fc_base" ]; then
            inventor_fc_base=$(readlink -f "$inventor_fc_base")
            cat > "$inventor_fc_conf" <<EOF || exit 1
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<!-- Written by the Inventor launcher (nix/launch-fonts.sh) at each start. -->
<fontconfig>
  <include ignore_missing="no">$inventor_fc_base</include>
  <match target="pattern">
    <edit name="rgba" mode="assign"><const>$inventor_rgba</const></edit>
  </match>
</fontconfig>
EOF
            export FONTCONFIG_FILE="$inventor_fc_conf"
        fi
        ;;
esac

unset inventor_desktop_key inventor_font_key inventor_font_marker inventor_desktop
unset inventor_smoothing inventor_smoothing_type inventor_rgba
unset inventor_fc_conf inventor_fc_base
unset -f inventor_desktop_value
