#!/bin/bash
# Run fuzz.exe for a range of seeds; print one line per seed that crashed,
# hung or broke the directory tree.
# Usage: WINE=/path/to/wine WINEPREFIX=... bash run-seeds.sh FIRST COUNT STEPS
WINE="${WINE:-wine}"
export WINEDEBUG=-all FZCHECK=1
cd "$(dirname "$(readlink -f "$0")")"
for ((s = $1; s < $1 + $2; s++)); do
    out=$(timeout 20 "$WINE" fuzz.exe "$s" 1 "$3" 2>&1); rc=$?
    if ! grep -q '^done' <<<"$out"; then
        why=$(grep -m1 -oE 'Assertion failed.*|Unhandled [a-z ]*|TREE BROKEN.*' <<<"$out")
        [ $rc = 124 ] && why="HANG $why"
        echo "seed $s: ${why:-exit code $rc}"
        "${WINE%/*}/wineserver" -k 2>/dev/null || wineserver -k 2>/dev/null
    fi
done
