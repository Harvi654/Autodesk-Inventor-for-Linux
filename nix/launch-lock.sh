# Hold this descriptor through the launcher and its Wine wrapper. Separate Wine
# namespaces must not run Autodesk services against the same writable state.
inventor_year="${INVENTOR_YEAR:-2026}"
inventor_state_dir="${XDG_DATA_HOME:-$HOME/.local/share}/autodesk-inventor-$inventor_year/.nix-overlayfs"
mkdir -p "$inventor_state_dir" || exit 1
exec {inventor_session_lock}>"$inventor_state_dir/inventor.lock"
if ! flock -n "$inventor_session_lock"; then
    echo "Inventor: this user state is already in use; close the existing session first" >&2
    exit 1
fi
