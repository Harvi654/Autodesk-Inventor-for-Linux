# Sets the release and its persistent state directory for the other launch
# scripts (launch-services.sh keeps the licensing database there). There is
# no lock here: nix-overlayfs takes one per writable layer before it touches
# the state (registry merge, mount) and keeps it out of Wine's processes. A
# second launch of the same release exits with status 75. A lock taken here
# came too late, and Wine inherited it (an orphaned process kept holding it).
inventor_year="${INVENTOR_YEAR:-2026}"
inventor_state_dir="${XDG_DATA_HOME:-$HOME/.local/share}/autodesk-inventor-$inventor_year/.nix-overlayfs"
mkdir -p "$inventor_state_dir" || exit 1
