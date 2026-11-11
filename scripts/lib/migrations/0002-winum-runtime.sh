# shellcheck shell=bash
# Step 0002: bring the prefix to the Wine it now runs on (winum since
# winum-11.20-1) with `wineboot -u`, and record that Wine in the prefix's
# state ("runtime=", prefix_runtime_differs in common.sh). The launcher's own
# check compared only `wine --version`, which is "wine-11.20" for this
# project's wine-inventor-11.20-6 and for winum-11.20-1 alike, so it would
# not have noticed the change.
MIG_DESC="Wine runtime: update the prefix for the Wine in use (wineboot -u)"
# the registry (always saved) and Wine's markers; wineboot -u leaves the
# builtin DLL copies in system32/syswow64 as they are (measured with
# winum-11.20-1), files it may add are harmless if the step is undone
MIG_BACKUP=".update-timestamp .inventor-wine-version"

mig_needed() { prefix_runtime_differs; }

mig_apply() {
    local stamp
    stamp="$(cat "$WINEPREFIX/.update-timestamp" 2>/dev/null || true)"
    info "    wineboot -u with $(wine_runtime_id) - up to a minute"
    # Isolation: no Z:, so Wine reaches its own share/wine (wine-mono,
    # wine-gecko) only through the drive sandbox_fs links to it (WINE_DATA_DIR,
    # among the font drives). Before the update that drive still pointed at
    # the old Wine, and wineboot -u asked for a wine-mono package (seen on a
    # copy of a 2026 prefix from before winum) - so the drives first.
    wine_stop
    sandbox_fs
    wineboot -u >>"$LOGDIR/setup-wine.log" 2>&1
    # services the prefix starts never exit: end them instead of waiting
    wine_stop
    # isolation: the update must not bring Z: or the home links back, and
    # Wine must not update by itself (launch-inventor.sh does it)
    if [ "$INV_SANDBOX" = 1 ]; then
        sandbox_reg
        wine_stop
        sandbox_fs
    elif [ "$stamp" = disable ]; then
        echo disable > "$WINEPREFIX/.update-timestamp"
    fi
    wine --version > "$WINEPREFIX/.inventor-wine-version"
    # wineboot -u does not replace the builtin DLL copies in system32, so
    # what says "done" is the record
    mig_state_set runtime "$(wine_runtime_id)"
}
