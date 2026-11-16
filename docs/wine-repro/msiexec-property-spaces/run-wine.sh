#!/bin/bash
# The msiexec quoting test under Wine: one MSI property value with a space,
# passed four ways. Run in a throwaway prefix:
#   export WINEPREFIX=/tmp/quotetest-prefix
#   bash run-wine.sh            (needs quotetest.msi next to it: wixl quotetest.wxs)
# Prints per form: msiexec's exit code (low byte) and where marker.txt landed.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
[ -f "$here/quotetest.msi" ] || { echo "build it first: (cd $here && echo marker > marker.txt && wixl quotetest.wxs)"; exit 1; }
wineboot -i >/dev/null 2>&1; wineserver -w
cp "$here/quotetest.msi" "$WINEPREFIX/drive_c/quotetest.msi"
c="$WINEPREFIX/drive_c"
check() {   # FORM-NAME RC
    local where="nowhere"
    for p in "quote test/a" "Program Files (x86)/QuoteTest" "Program Files/QuoteTest"; do
        [ -f "$c/$p/marker.txt" ] && where="C:\\${p//\//\\}"
    done
    printf '%-34s exit %-4s marker.txt in %s\n' "$1" "$2" "$where"
    wine msiexec /x 'C:\quotetest.msi' /qn >/dev/null 2>&1; wineserver -w
    rm -rf "$c/quote test"
}
# A: one argument, as install-from-image.py passed it until 2026-11-16
wine msiexec /i 'C:\quotetest.msi' /qn 'INSTALLDIR=C:\quote test\a'; check "A arg  INSTALLDIR=C:\\quote test\\a" $?
# B: the same with a trailing backslash (what ODIS's value looks like)
wine msiexec /i 'C:\quotetest.msi' /qn 'INSTALLDIR=C:\quote test\a\'; check "B arg  ...\\a\\ (trailing \\)" $?
# C: ODIS's form, NAME="value", reaching msiexec unchanged through a batch file
printf '@echo off\r\nmsiexec /i C:\\quotetest.msi /qn INSTALLDIR="C:\\quote test\\a\\"\r\nexit /b %%errorlevel%%\r\n' > "$c/q.cmd"
wine cmd /c 'C:\q.cmd'; check "C bat  INSTALLDIR=\"C:\\quote test\\a\\\"" $?
# D: no space (control)
wine msiexec /i 'C:\quotetest.msi' /qn 'INSTALLDIR=C:\quotetest'; rc=$?
[ -f "$c/quotetest/marker.txt" ] && w='C:\quotetest' || w=nowhere
printf '%-34s exit %-4s marker.txt in %s\n' "D arg  INSTALLDIR=C:\\quotetest" "$rc" "$w"
wine msiexec /x 'C:\quotetest.msi' /qn >/dev/null 2>&1
