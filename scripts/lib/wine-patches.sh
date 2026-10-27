# Shared by scripts/build-wine.sh and scripts/make-wine-source.sh: apply this
# project's Wine patches and leave the notices the LGPL asks for (2a: modified
# files carry a notice that they were changed, and when).
#
#   wine_apply_patches SRC PATCHDIR [GITDIR COMMIT]
#
# SRC      unpacked vanilla Wine source tree
# PATCHDIR directory with the top-level *.patch files (subdirectories are not
#          applied, same rule as nix/wine.nix)
# GITDIR, COMMIT  where the date of each patch comes from (last commit that
#          touched patches/<name> up to COMMIT); without them "unknown"
#
# Writes SRC/PATCHES.txt and appends a short comment to the end of every
# changed C/IDL/spec/Makefile file (at the end, so line numbers in messages
# such as asserts stay the same as in the patched code). Sets PATCH_LIST
# (sha256 prefix + name per line) for BUILDINFO.

wine_patch_date() {   # name -> YYYY-MM-DD of the last change of the patch
    local name="$1"
    [ -n "${_WP_GITDIR:-}" ] || { echo unknown; return; }
    git -C "$_WP_GITDIR" log -1 --format=%cs "$_WP_COMMIT" -- "patches/$name" 2>/dev/null | grep . || echo unknown
}

wine_apply_patches() {
    local src="$1" pdir="$2" p name sum date f
    _WP_GITDIR="${3:-}" _WP_COMMIT="${4:-HEAD}"
    PATCH_LIST=""
    declare -A _wp_files=()
    local patches=()
    while IFS= read -r p; do patches+=("$p"); done < <(LC_ALL=C ls -1 "$pdir"/*.patch 2>/dev/null)
    [ "${#patches[@]}" -gt 0 ] || { echo "no patches in $pdir" >&2; return 1; }

    {
        echo "Patches applied to this Wine source by Autodesk-Inventor-for-Linux"
        echo "https://github.com/Harvi654/Autodesk-Inventor-for-Linux"
        echo
        echo "The patches were written with AI help (Claude by Anthropic) and tested by"
        echo "people on real machines. They are not part of Wine."
        [ -f "$pdir/wbemprox-timezone.patch" ] && \
            echo "wbemprox-timezone.patch comes from https://github.com/cakelesscoder/inventor-on-linux."
        echo "License: LGPL 2.1 or later, like the files they change (COPYING.LIB)."
        echo
        echo "Order of application, SHA-256, date of the last change, files changed:"
        echo
    } > "$src/PATCHES.txt"

    for p in "${patches[@]}"; do
        name="$(basename "$p")"
        (cd "$src" && patch -p1 -s -N --no-backup-if-mismatch < "$p") || { echo "$name does not apply" >&2; return 1; }
        echo "    $name"
        sum="$(sha256sum "$p" | cut -d' ' -f1)"
        date="$(wine_patch_date "$name")"
        PATCH_LIST+="${sum:0:16}  $name"$'\n'
        {
            echo "$name"
            echo "    sha256 $sum"
            echo "    date   $date"
            sed -n 's#^+++ b/\([^[:space:]]*\).*#    file   \1#p' "$p"
            echo
        } >> "$src/PATCHES.txt"
        while IFS= read -r f; do
            [ -n "$f" ] && _wp_files["$f"]+="${_wp_files[$f]:+, }$name ($date)"
        done < <(sed -n 's#^+++ b/\([^[:space:]]*\).*#\1#p' "$p")
    done

    for f in "${!_wp_files[@]}"; do
        [ -f "$src/$f" ] || continue
        case "$f" in
            *.c|*.h|*.idl|*.rc|*.y|*.l)
                printf '\n/* Modified by Autodesk-Inventor-for-Linux: %s.\n * See PATCHES.txt at the top of this source tree. */\n' \
                    "${_wp_files[$f]}" >> "$src/$f" ;;
            *.spec|*Makefile.in)
                printf '\n# Modified by Autodesk-Inventor-for-Linux: %s.\n# See PATCHES.txt at the top of this source tree.\n' \
                    "${_wp_files[$f]}" >> "$src/$f" ;;
            *) ;;   # other file types: listed in PATCHES.txt only
        esac
    done
}
