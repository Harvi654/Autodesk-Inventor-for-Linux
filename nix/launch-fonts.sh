# Runs in the composed prefix. Earlier launchers mapped Tahoma to Segoe UI in
# FontSubstitutes when a real Segoe UI was installed, because Tahoma's
# small-size GASP instructions turned off grayscale smoothing in Wine. Since
# winum 11.22-3, text follows the desktop font smoothing values, which
# launch-services.sh sets to ClearType, and Tahoma renders smoothly itself.
# The mapping stays in the writable state of existing users, so it is
# removed here. Only that exact value is removed: a substitution to another
# family is the user's own.
inventor_font_key='HKLM\Software\Microsoft\Windows NT\CurrentVersion\FontSubstitutes'
if inventor_tahoma=$(wine reg query "$inventor_font_key" /v Tahoma 2>/dev/null) &&
    printf '%s\n' "$inventor_tahoma" |
        grep -Eq '^[[:space:]]*Tahoma[[:space:]]+REG_SZ[[:space:]]+Segoe UI[[:space:]]*$'; then
    wine reg delete "$inventor_font_key" /v Tahoma /f || exit 1
fi
unset inventor_font_key inventor_tahoma
