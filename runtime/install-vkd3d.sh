#!/usr/bin/env bash
# Install a Windows vkd3d-proton DLL build into an explicitly supplied prefix.
# No registry changes: the launcher selects these DLLs through its environment.
set -euo pipefail
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 VKD3D_WINDOWS_DIRECTORY WINEPREFIX" >&2
    exit 2
fi
source_dir=$1
prefix=$2
for dll in d3d12 d3d12core; do
    mapfile -t candidates < <(find "$source_dir" -type f -iname "$dll.dll")
    if [ "${#candidates[@]}" -ne 1 ]; then
        echo "Expected one x64 $dll.dll in $source_dir; found ${#candidates[@]}" >&2
        exit 1
    fi
    install -Dm644 "${candidates[0]}" "$prefix/drive_c/windows/system32/$dll.dll"
done
