#!/bin/bash
# Collect what is needed to look into a problem into one text file, with
# e-mail addresses, sign-in tokens and your user name removed.
#
#   bash scripts/report.sh            newest Inventor log
#   bash scripts/report.sh --install  newest installation log instead
#
# Writes ~/inventor-report-<date>.txt. Read it before you send it anywhere.

set -uo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

KIND=inventor
[ "${1:-}" = --install ] && KIND=install
OUT="$HOME/inventor-report-$(date +%Y%m%d-%H%M%S).txt"
LINES="${INV_REPORT_LINES:-250}"

section() { printf '\n===== %s =====\n' "$*"; }
run() { "$@" 2>&1 || true; }

collect() {
    section "inventor-on-linux"
    run git -C "$PROJECT_DIR" log -1 --format='%h %cd %s' --date=short
    git -C "$PROJECT_DIR" status --porcelain --untracked-files=no 2>/dev/null | sed 's/^/changed: /'

    section "System"
    echo "distribution: $(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-?}")"
    echo "kernel:       $(uname -r)"
    echo "desktop:      ${XDG_CURRENT_DESKTOP:-?} (${XDG_SESSION_TYPE:-?})"
    command -v hyprctl >/dev/null && echo "hyprland:     $(hyprctl version 2>/dev/null | head -1)"
    command -v Xwayland >/dev/null && echo "xwayland:     $(pacman -Q xorg-xwayland 2>/dev/null)"
    echo "cpu:          $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ //')"
    echo "memory:       $(free -g | awk '/^Mem:/{print $2 " GB"}')"
    echo "free disk:    $(df -h --output=avail "$HOME" | tail -1 | tr -d ' ') in home"

    section "GPU"
    command -v lspci >/dev/null && lspci | grep -Ei 'vga|3d|display'
    if command -v vulkaninfo >/dev/null; then
        vulkaninfo --summary 2>/dev/null | grep -E 'deviceName|driverName|driverInfo|apiVersion' | sed 's/^\s*//'
    else
        echo "(vulkaninfo not installed: sudo pacman -S vulkan-tools)"
    fi
    pacman -Q 2>/dev/null | grep -E '^(nvidia|lib32-nvidia|vulkan-radeon|vulkan-intel|mesa|lib32-mesa) ' || true
    [ -n "$INV_GPU" ] && echo "INV_GPU=$INV_GPU"

    section "Wine"
    echo "wine: $(wine --version 2>/dev/null) ($(pacman -Qo "$(command -v wine)" 2>/dev/null | awk '{print $(NF-1), $NF}'))"
    local wv pe f sys
    wv="$(wine_version)"; pe="$(wine_pe_dir)"
    for f in "${WINE_FIX_PARTS[@]}"; do
        case "$f" in
            server)  sys="$(readlink -f "$(command -v wineserver)")" ;;
            winex11) sys="$(dirname "$pe")/x86_64-unix/winex11.so" ;;
            *)       sys="$pe/$f.dll" ;;
        esac
        if [ ! -f "$sys.orig-$wv" ]; then echo "  $f: NOT patched for Wine $wv"
        elif cmp -s "$sys" "$sys.orig-$wv"; then echo "  $f: original (patch removed?)"
        else echo "  $f: patched"; fi
    done

    section "Prefix"
    echo "prefix: $WINEPREFIX ($(du -sh "$WINEPREFIX" 2>/dev/null | cut -f1))"
    echo "Inventor.exe: $(inv_file_version "$P_INV/Bin/Inventor.exe")"
    [ -d "$P_ADDINS_OFF" ] && echo "add-ins off: $(find "$P_ADDINS_OFF" -maxdepth 1 -iname '*.addin' -printf '%f ' 2>/dev/null)"
    for f in "$PROJECT_DIR/config.env" "${XDG_CONFIG_HOME:-$HOME/.config}/inventor-on-linux/config.env"; do
        [ -f "$f" ] && { echo "config ($f):"; grep -vE '^\s*(#|$)' "$f" | sed 's/^/  /'; }
    done

    local log
    log="$(ls -t "$LOGDIR/$KIND-"*.log 2>/dev/null | head -1)"
    section "Log: ${log:-none} (last $LINES lines)"
    [ -n "$log" ] && tail -n "$LINES" "$log"
    if [ "$KIND" = inventor ] && [ -n "$log" ]; then
        section "Log: errors and crashes (whole file)"
        grep -nE 'X Error|Unhandled exception|page fault|wine: |backtrace|FailFast|err:seh|Assertion|fatal' "$log" | tail -40
    fi
}

# e-mails, bearer/OAuth tokens, long hex/base64 strings, URL query strings,
# user name and home folder
clean() {
    sed -E \
        -e "s#$HOME#~#g" \
        -e "s/\\b$USER\\b/<user>/g" \
        -e 's/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/<email>/g' \
        -e 's/(Bearer|Basic) +[^ ",]+/\1 <removed>/Ig' \
        -e 's/((access|refresh|id|auth)_?token|client_secret|password)([":= ]+)[^ ",&]+/\1\3<removed>/Ig' \
        -e 's#(https?://[^ ?"]*)\?[^ "]*#\1?<query removed>#g' \
        -e 's/[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{24,}(\.[A-Za-z0-9_-]+)?/<token>/g' \
        -e 's/[A-Za-z0-9+=_-]{40,}/<long string>/g'
}

collect | clean > "$OUT"
ok "report: $OUT ($(wc -l < "$OUT") lines)"
info "Please read it before sending - it should contain nothing private."
