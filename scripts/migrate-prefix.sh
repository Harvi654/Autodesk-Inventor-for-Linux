#!/bin/bash
# Bring an existing Inventor prefix up to date without reinstalling: runs
# the prefix migrations (scripts/lib/migrations/) it has not had yet, each
# with a backup that is put back if it fails.
#
#   bash scripts/migrate-prefix.sh              pending steps for INV_PREFIX / INV_YEAR
#   bash scripts/migrate-prefix.sh --status     what this prefix has had, nothing changed
#   bash scripts/migrate-prefix.sh --dry-run    what would run
#   bash scripts/migrate-prefix.sh --all        every installed release, one after another
#   bash scripts/migrate-prefix.sh --run ID     one step by name (also an optional one,
#                                               or again)
#   bash scripts/migrate-prefix.sh --restore ID put back the backup taken before step ID
#
# Close Inventor first. The prefix is the one common.sh chooses
# (config.env, INV_PREFIX, INV_YEAR) - say which with INV_PREFIX=... INV_YEAR=...
set -Eeuo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"
source "$COMMON_DIR/configure.sh"
source "$COMMON_DIR/migrations.sh"

MODE=run ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --status) MODE=status ;;
        --dry-run) MODE=dry ;;
        --all) MODE=all ;;
        --run) MODE=one; ARGS+=("${2:?--run needs a step}"); shift ;;
        --restore) MODE=restore; ARGS+=("${2:?--restore needs a step}"); shift ;;
        -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "unknown option: $1 (see --help)" ;;
    esac
    shift
done

if [ "$MODE" = all ]; then
    rc=0 n=0
    while IFS=$'\t' read -r y p; do
        [ -n "$p" ] || continue
        n=$((n + 1))
        echo "== Inventor $y in $p"
        env INV_YEAR="$y" INV_PREFIX="$p" bash "$0" || rc=1
    done < <(inventor_installs)
    [ "$n" -gt 0 ] || info "no installed Inventor found"
    exit "$rc"
fi

echo "Inventor $INV_YEAR in $WINEPREFIX (prefix: $INV_PREFIX_SOURCE)"
[ -n "$(inventor_year_in_prefix "$WINEPREFIX")" ] || die "no Inventor in $WINEPREFIX"
: >> "$LOGDIR/setup-wine.log"
case "$MODE" in
    status) mig_status ;;
    dry) run_migrations --dry-run ;;
    one) run_migrations "${ARGS[@]}" ;;
    restore)
        if busy="$(mig_prefix_busy)"; then die "$busy is running in $WINEPREFIX - close it first"; fi
        mig_restore "${ARGS[0]}"
        ;;
    run) run_migrations ;;
esac
