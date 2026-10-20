#!/usr/bin/env bash
# Assemble a runtime from the Nix Wine wrapper layout and a matching OpenGL PE
# DLL. The supplied DLL must be built from the same Wine source and Unix ABI.
set -euo pipefail
wine_root=${1:?Wine package directory required}
opengl_dll=${2:?Patched opengl32.dll required}
runtime_root=${3:?New output directory required}

if [ -e "$runtime_root" ]; then
    echo "Wine runtime output must not already exist: $runtime_root" >&2
    exit 1
fi
mkdir -p "$runtime_root"
cp -rs "$wine_root"/. "$runtime_root/"
find "$runtime_root" -type d -exec chmod u+w {} +

# Wine uses realpath(/proc/self/exe) and dladdr(ntdll) to find its builtin
# directory before WINEDLLPATH. These bootstrap files must be physical copies.
for relative in bin/.wine lib/wine/x86_64-unix/wine \
    lib/wine/x86_64-unix/wine-preloader lib/wine/x86_64-unix/ntdll.so; do
    rm "$runtime_root/$relative"
    cp "$wine_root/$relative" "$runtime_root/$relative"
done

# Repoint the Nix launcher wrapper without changing its environment setup.
IFS= read -r first_line < "$wine_root/bin/wine"
case "$first_line" in
    '#!'*) ;;
    *) echo "Expected a Nix Wine launcher wrapper" >&2; exit 1 ;;
esac
rm "$runtime_root/bin/wine"
while IFS= read -r line || [ -n "$line" ]; do
    printf '%s\n' "${line//"$wine_root"/"$runtime_root"}"
done < "$wine_root/bin/wine" > "$runtime_root/bin/wine"
chmod +x "$runtime_root/bin/wine"

# Keep argv[0]-based helpers such as wineboot and winecfg on the new launcher.
for helper in "$wine_root"/bin/*; do
    name=$(basename "$helper")
    if [ "$name" != wine ] && [ "$(readlink -f "$helper")" = "$wine_root/bin/wine" ]; then
        rm "$runtime_root/bin/$name"
        ln -s wine "$runtime_root/bin/$name"
    fi
done
rm "$runtime_root/lib/wine/x86_64-windows/opengl32.dll"
ln -s "$opengl_dll" "$runtime_root/lib/wine/x86_64-windows/opengl32.dll"
