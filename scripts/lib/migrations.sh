# shellcheck shell=bash
# Prefix migrations: numbered steps that bring a Wine prefix to what this
# project sets up today, so an existing installation gets a change without
# being reinstalled. Source after common.sh (and configure.sh).
#
#   scripts/lib/migrations/NNNN-<what>.sh   one step each; a change to the
#                                           prefix is always a new file,
#                                           never an edit of an old one
#   <prefix>/.inventor-on-linux/state       key=value: done.<id>=<date> <how>
#   <prefix>/.inventor-on-linux/backup/<id> what a step changes, saved first
#
# A step file sets MIG_DESC (one line) and defines mig_apply; optionally
#   mig_needed     return 1 when the prefix already has what the step does
#                  (it is then recorded as done without changing anything)
#   MIG_BACKUP     extra paths (relative to the prefix) saved before it runs;
#                  the registry files are always saved; "none" saves nothing
#   MIG_OPTIONAL=1 never run unless asked for by name (large changes)
# Every step runs in a subshell with set -Eeuo pipefail. If it fails, what
# was saved is put back and the run stops: a prefix is never left half
# changed by a step.
# Design: docs/drafts/prefix-migrations.md.

MIG_DIR="${INV_MIG_DIR:-$COMMON_DIR/migrations}"   # INV_MIG_DIR: tests only
MIG_REGISTRY_FILES=(system.reg user.reg userdef.reg)

mig_state_dir() { echo "$WINEPREFIX/.inventor-on-linux"; }
mig_state_file() { echo "$(mig_state_dir)/state"; }

mig_state_get() {   # KEY -> value ("" when not set)
    local f; f="$(mig_state_file)"
    [ -f "$f" ] || return 0
    sed -n "s/^$(printf '%s' "$1" | sed 's/[.[\*^$/]/\\&/g')=//p" "$f" | tail -1
}

mig_state_set() {   # KEY VALUE
    local f tmp; f="$(mig_state_file)"
    mkdir -p "$(mig_state_dir)"
    tmp="$f.tmp.$$"
    { [ -f "$f" ] && grep -v "^$(printf '%s' "$1" | sed 's/[.[\*^$/]/\\&/g')=" "$f" || true
      printf '%s=%s\n' "$1" "$2"; } > "$tmp"
    mv -f "$tmp" "$f"
}

mig_files() {   # all step files, in order
    local f
    for f in "$MIG_DIR"/[0-9][0-9][0-9][0-9]-*.sh; do
        [ -f "$f" ] && echo "$f"
    done | sort
}

mig_id() { basename "$1" .sh; }

mig_is_optional() { grep -q '^MIG_OPTIONAL=1' "$1"; }

mig_done() { [ -n "$(mig_state_get "done.$1")" ]; }

# A prefix installed before migrations existed has no state: finish-install.sh
# ran its whole setup, which is step 0001. Record that, nothing else.
mig_adopt() {
    [ -f "$(mig_state_file)" ] && return 0
    [ -n "$(inventor_year_in_prefix "$WINEPREFIX")" ] || return 0
    mig_state_set schema 1
    mig_state_set "done.0001-base-setup" "$(date -u +%Y-%m-%dT%H:%M:%SZ) adopted (installed before migrations)"
    info "prefix from before migrations: recorded as having the base setup (0001)"
}

mig_pending() {   # ids of the steps this prefix has not had (optional ones left out)
    local f
    while IFS= read -r f; do
        mig_done "$(mig_id "$f")" && continue
        mig_is_optional "$f" && continue
        mig_id "$f"
    done < <(mig_files)
}

# A Windows program running in this prefix (Inventor, its services)? From
# /proc: WINEPREFIX in the environment and a Windows path ("C:\...") as the
# first word of the command line - this script and its parents have the
# same WINEPREFIX but are not Windows programs. Prints the first one found.
mig_prefix_busy() {
    local p want="WINEPREFIX=$WINEPREFIX" first
    for p in /proc/[0-9]*; do
        [ -r "$p/environ" ] || continue
        { tr '\0' '\n' < "$p/environ"; } 2>/dev/null | grep -qxF "$want" || continue
        first="$({ tr '\0' '\n' < "$p/cmdline"; } 2>/dev/null | head -1)"
        case "$first" in [A-Za-z]:\\*) echo "$first"; return 0 ;; esac
    done
    return 1
}

# Registry value from the prefix, "" when not set (output captured first:
# no pipe that pipefail could fail)
mig_reg_get() {   # KEY VALUE
    local out
    out="$(WINEDEBUG=-all wine reg query "$1" /v "$2" 2>/dev/null)" || true
    printf '%s\n' "$out" | tr -d '\r' | awk -v v="$2" 'tolower($1) == tolower(v) && $2 ~ /^REG_/ { $1 = ""; $2 = ""; sub(/^ +/, ""); print; exit }'
}

mig_backup() {   # ID PATHS... (relative to the prefix)
    local dir="$(mig_state_dir)/backup/$1" p; shift
    rm -rf -- "${dir:?}"
    mkdir -p "$dir/files"
    : > "$dir/manifest"
    for p in "${MIG_REGISTRY_FILES[@]}" "$@"; do
        [ -n "$p" ] || continue
        if [ -e "$WINEPREFIX/$p" ] || [ -L "$WINEPREFIX/$p" ]; then
            mkdir -p "$dir/files/$(dirname "$p")"
            cp -a --reflink=auto -- "$WINEPREFIX/$p" "$dir/files/$p"
            printf 'saved\t%s\n' "$p" >> "$dir/manifest"
        else
            printf 'absent\t%s\n' "$p" >> "$dir/manifest"
        fi
    done
}

mig_restore() {   # ID - put back what mig_backup saved
    local dir="$(mig_state_dir)/backup/$1" how p
    [ -f "$dir/manifest" ] || { err "no backup of $1 in $dir"; return 1; }
    wine_stop
    while IFS=$'\t' read -r how p; do
        [ -n "$p" ] || continue
        rm -rf -- "${WINEPREFIX:?}/$p"
        if [ "$how" = saved ]; then
            mkdir -p "$WINEPREFIX/$(dirname "$p")"
            cp -a --reflink=auto -- "$dir/files/$p" "$WINEPREFIX/$p"
        fi
    done < "$dir/manifest"
    info "restored from $dir"
}

# Run FUNCTION of step FILE in a new bash with set -Eeuo pipefail. A new
# process, not a subshell: run from inside an `||` or `if` (as it is here),
# bash ignores set -e in a subshell, and a failing command in a step would
# not stop it. The INV_* settings go along; the child sources the libraries
# again for the same prefix.
mig_exec() {   # FILE FUNCTION
    (
        for _v in $(compgen -v INV_); do export "${_v?}"; done
        export INV_PREFIX="$WINEPREFIX" INV_LOGDIR="$LOGDIR" _STEP _STEPS
        exec bash -Eeuo pipefail -c '
            source "$0/common.sh"
            source "$0/configure.sh"
            source "$0/migrations.sh"
            source "$1"
            if [ "$2" = mig_needed ] && ! declare -F mig_needed >/dev/null; then exit 0; fi
            "$2"' "$COMMON_DIR" "$1" "$2"
    )
}

mig_run_one() {   # FILE [force] - 0 done, 1 failed (prefix restored)
    local f="$1" id desc backup optional needed=yes rc
    id="$(mig_id "$f")"
    desc="$(MIG_DESC=""; source "$f"; echo "$MIG_DESC")"
    backup="$(MIG_BACKUP=""; source "$f"; echo "$MIG_BACKUP")"
    if ! mig_exec "$f" mig_needed; then needed=no; fi
    if [ "$needed" = no ] && [ "${2:-}" != force ]; then
        mig_state_set "done.$id" "$(date -u +%Y-%m-%dT%H:%M:%SZ) already so"
        info "$id: $desc - already so"
        return 0
    fi
    info "$id: $desc"
    wine_stop
    if [ "$backup" != none ]; then
        # shellcheck disable=SC2086  # MIG_BACKUP is a word list
        mig_backup "$id" $backup
    fi
    rc=0; mig_exec "$f" mig_apply || rc=$?
    wine_stop
    if [ "$rc" -ne 0 ]; then
        err "$id failed (exit code $rc)"
        if [ "$backup" != none ]; then
            mig_restore "$id" && err "the prefix is as it was before $id"
        fi
        return 1
    fi
    mig_state_set "done.$id" "$(date -u +%Y-%m-%dT%H:%M:%SZ) applied"
    ok "$id done"
}

# run_migrations [--with-base] [--dry-run] [ID...]
#   no ID: every pending, non-optional step; --with-base also runs 0001 again
#   (finish-install.sh); ID: run exactly those (also optional or done ones)
run_migrations() {
    local with_base=0 dry=0 ids=() f id todo=()
    while [ $# -gt 0 ]; do
        case "$1" in
            --with-base) with_base=1 ;;
            --dry-run) dry=1 ;;
            *) ids+=("$1") ;;
        esac
        shift
    done
    local busy
    if busy="$(mig_prefix_busy)"; then
        err "$busy is running in $WINEPREFIX - close Inventor and run again (nothing open: WINEPREFIX=$WINEPREFIX wineserver -k)"
        return 1
    fi
    # finish-install.sh (--with-base) sets up the prefix now: nothing to adopt
    [ "$with_base" = 1 ] || mig_adopt
    mig_state_set schema 1
    if [ ${#ids[@]} -gt 0 ]; then
        for id in "${ids[@]}"; do
            f="$MIG_DIR/$id.sh"
            [ -f "$f" ] || f="$(mig_files | grep "/$id-[^/]*\.sh$" | head -1)"
            [ -n "$f" ] && [ -f "$f" ] || { err "no migration $id"; return 1; }
            todo+=("$f")
        done
    else
        while IFS= read -r f; do
            id="$(mig_id "$f")"
            if [ "$with_base" = 1 ] && [ "$id" = 0001-base-setup ]; then todo+=("$f"); continue; fi
            mig_done "$id" || mig_is_optional "$f" || todo+=("$f")
        done < <(mig_files)
    fi
    if [ ${#todo[@]} -eq 0 ]; then
        ok "prefix $WINEPREFIX is up to date - nothing to do"
        return 0
    fi
    for f in "${todo[@]}"; do
        if [ "$dry" = 1 ]; then info "would run $(mig_id "$f"): $(MIG_DESC=""; source "$f"; echo "$MIG_DESC")"; continue; fi
        if [ ${#ids[@]} -gt 0 ]; then mig_run_one "$f" force || return 1
        else mig_run_one "$f" || return 1; fi
    done
}

# One line per step: done/pending/optional and when.
mig_status() {
    local f id v adopted=0
    echo "prefix $WINEPREFIX (Inventor $INV_YEAR)"
    # read-only: a prefix from before migrations is shown as it would be adopted
    [ ! -f "$(mig_state_file)" ] && [ -n "$(inventor_year_in_prefix "$WINEPREFIX")" ] && adopted=1
    while IFS= read -r f; do
        id="$(mig_id "$f")"
        v="$(mig_state_get "done.$id")"
        [ -z "$v" ] && [ "$adopted" = 1 ] && [ "$id" = 0001-base-setup ] && v="before migrations - adopted on the first run"
        if [ -n "$v" ]; then printf '  done      %s (%s)\n' "$id" "$v"
        elif mig_is_optional "$f"; then printf '  optional  %s\n' "$id"
        else printf '  pending   %s\n' "$id"; fi
    done < <(mig_files)
}

# A prefix installed before the installer had the .NET Framework 4.8 step
# (2026-11-11) runs Inventor's .NET Framework programs on wine-mono: 3D PDF
# (Anark) and Import CAD's Property Mapping do not work there, and no
# migration adds .NET (it would replace wine-mono: a new installation is the
# way). Say so once per prefix (notice.dotnet48 in its state), not at every
# start. A prefix with .NET's clr.dll is left alone (the launcher has its own
# warning when that .NET is no longer complete).
dotnet48_notice_once() {
    [ -f "$P_C/windows/Microsoft.NET/Framework64/v4.0.30319/clr.dll" ] && return 0
    [ -z "$(mig_state_get notice.dotnet48)" ] || return 0
    info "This prefix has no .NET Framework 4.8 (installed before 2026-11-11): 3D PDF and"
    info "Import CAD's Property Mapping do not work in it. A new installation adds it - your"
    info "files in ${INV_DATA_DIR:-~/Inventor} (D:) stay. How: README, \"3D PDF and Property Mapping in an older"
    info "installation\" ($PROJECT_DIR/README.md). (Shown once.)"
    mig_state_set notice.dotnet48 "$(date -u +%Y-%m-%dT%H:%M:%SZ) shown"
}
