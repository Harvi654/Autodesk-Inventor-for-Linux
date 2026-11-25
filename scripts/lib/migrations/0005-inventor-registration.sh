# shellcheck shell=bash
# Step 0005: Inventor's own registration, `Inventor.exe /install 0`, once.
# On Windows the Windows Installer service starts it during the install,
# once Inventor's files are in place; it registers the COM server
# Inventor.Application (add-ins, iLogic, Vault, external programs), the
# document types Inventor.PartDocument, .AssemblyDocument, ... and type
# libraries (docs/installer-completeness-review.md, "Needed" 1). Our
# installer never ran it before 2026-11-16; install-from-image.py runs it
# now for a new installation, this step for an existing prefix.
#
# It shows no window and ends by itself (measured on the maintainer's
# reference prefix, 2026-11-15); helper processes it starts keep the
# wineserver alive, so the prefix is stopped afterwards (wine_stop:
# wineserver -k). winemenubuilder stays off (common.sh): run by hand with it
# on, the registration created 13 wine-extension/-protocol .desktop files.
#
# Inventor runs without these keys (it did until now), so a registration
# that does not finish is a warning, not a failed step: a failed step would
# stop the launcher at every start. Try again with
#   bash scripts/migrate-prefix.sh --run 0005
MIG_DESC="Inventor's registration: Inventor.exe /install 0 (COM server Inventor.Application, document types)"

_mig_reg_has() {   # KEY under HKCU\Software\Classes, from user.reg ("[Software\\Classes\\X]" or a fake's "...\Classes\X|")
    grep -qiE "Classes\\\\+$1([]\\\\|]|$)" "$WINEPREFIX/user.reg" 2>/dev/null
}

mig_needed() {
    [ -f "$P_INV/Bin/Inventor.exe" ] || return 1   # nothing to register
    ! { _mig_reg_has 'Inventor\.Application' && _mig_reg_has 'Inventor\.PartDocument'; }
}

_mig_desktop_files() {
    ls -1 "${XDG_DATA_HOME:-$HOME/.local/share}/applications"/wine-*.desktop 2>/dev/null | sort || true
}

mig_apply() {
    local before after new rc=0
    before="$(_mig_desktop_files)"
    info "    Inventor.exe /install 0 - no window, up to 10 minutes"
    wine_stop
    # winemenubuilder.exe=d is in WINEDLLOVERRIDES (common.sh); say it again
    # here so that this step never depends on where it is run from
    WINEDLLOVERRIDES="${WINEDLLOVERRIDES:+$WINEDLLOVERRIDES;}winemenubuilder.exe=d" \
        timeout --kill-after=10 600 wine "C:\\Program Files\\Autodesk\\Inventor $INV_YEAR\\Bin\\Inventor.exe" /install 0 \
        >>"$LOGDIR/setup-wine.log" 2>&1 || rc=$?
    # its helper processes never end by themselves
    wine_stop
    after="$(_mig_desktop_files)"
    new="$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | sed '/^$/d')"
    if [ -n "$new" ]; then
        warn "    new Linux menu entries after the registration (not expected): $(printf '%s ' $new)"
    fi
    if mig_needed; then
        warn "    Inventor's registration did not finish (exit code $rc; Inventor.Application/Inventor.PartDocument"
        warn "    not in user.reg) - Inventor runs without it. Try again: bash scripts/migrate-prefix.sh --run 0005"
    else
        info "    registered: Inventor.Application, Inventor.PartDocument, ..."
    fi
}
