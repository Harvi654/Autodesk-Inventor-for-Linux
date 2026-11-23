# Reports user-level desktop entries that hide or compete with the NixOS
# module's Inventor entries: a file in $XDG_DATA_HOME/applications with the
# same name as a module entry wins over the system one, so clicking the menu
# item starts whatever that file names (for example an older launcher, which
# then misses the current one's checks). Run by a systemd user service at the
# start of a graphical session, independently of any menu entry. Changes
# nothing: it names each file and what it starts, and leaves it in place.
#
# Usage: desktop-check.sh MODULE_ENTRY... -- CURRENT_LAUNCHER...
#   MODULE_ENTRY      desktop file names the module installs
#   CURRENT_LAUNCHER  the launchers the module's entries start
# Exit code 0 always; findings go to stderr (the journal) and, when
# notify-send is available, to one desktop notification.
set -u

entries=()
launchers=()
while [ $# -gt 0 ] && [ "$1" != -- ]; do entries+=("$1"); shift; done
[ "${1:-}" = -- ] && shift
launchers=("$@")

apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
[ -d "$apps" ] || exit 0

# What the entry starts: the program of its Exec line, resolved. Handles a
# double-quoted program path (spaces) and an `env [VAR=value...] program`
# wrapper; when the program cannot be found, the raw Exec line is shown.
exec_target() {
    local line rest target word
    line=$(grep -m1 '^Exec=' "$1" 2>/dev/null) || { echo "(no Exec line)"; return; }
    rest=${line#Exec=}
    next_word() {   # sets word to the first word of rest, rest to the remainder
        rest=${rest#"${rest%%[! ]*}"}
        if [ "${rest:0:1}" = '"' ]; then
            rest=${rest:1}
            word=${rest%%\"*}
            rest=${rest#*\"}
        else
            word=${rest%% *}
            if [ "$word" = "$rest" ]; then rest=""; else rest=${rest#* }; fi
        fi
    }
    next_word
    target=$word
    if [ "${target##*/}" = env ]; then
        while next_word; [ -n "$word" ]; do
            case "$word" in -*|*=*) continue ;; esac
            target=$word
            break
        done
    fi
    if [ -n "$target" ] && [ -e "$target" ]; then
        readlink -f -- "$target"
    elif [ -n "$target" ] && [ "${target#/}" = "$target" ] && command -v -- "$target" >/dev/null 2>&1; then
        readlink -f -- "$(command -v -- "$target")"
    else
        echo "${target:-?} (missing; $line)"
    fi
}

is_current() {
    local l
    for l in "${launchers[@]}"; do
        [ "$1" = "$(readlink -f -- "$l")" ] && return 0
    done
    return 1
}

findings=()
report() {
    local file="$1" why="$2" target
    target=$(exec_target "$file")
    is_current "$target" && [ "$why" != shadows ] && return 0
    case "$why" in
        shadows) findings+=("$file hides the system entry of the same name; it starts $target") ;;
        *) findings+=("$file ($why) starts $target") ;;
    esac
}

for name in "${entries[@]}"; do
    [ -e "$apps/$name" ] && report "$apps/$name" shadows
done
for file in "$apps"/autodesk-inventor*-wayland.desktop; do
    [ -e "$file" ] && report "$file" "an old Wayland entry"
done
for file in "$apps"/inventor*-nix-overlayfs-url-handler.desktop "$apps"/adskidmgr-handler.desktop; do
    [ -e "$file" ] && report "$file" "an adskidmgr handler outside the module"
done

[ ${#findings[@]} -gt 0 ] || exit 0
{
    echo "Autodesk Inventor: user desktop entries that may start an old launcher:"
    printf '  %s\n' "${findings[@]}"
    echo "Remove or rename them to use the NixOS module's entries; nothing was changed."
} >&2
if command -v notify-send >/dev/null 2>&1; then
    notify-send --app-name="Autodesk Inventor" "Autodesk Inventor: old desktop entries" \
        "$(printf '%s\n' "${findings[@]}")" 2>/dev/null || true
fi
exit 0
