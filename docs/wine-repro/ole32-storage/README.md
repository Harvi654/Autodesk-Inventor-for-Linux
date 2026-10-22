# ole32 structured storage - reproducers

Small Windows programs used to find and check the two ole32 fixes behind
Frame Analysis (`patches/ole32-storage-thread-lock.patch`,
`patches/ole32-transacted-truncate-dirty.patch`). The full story is in
`docs/arch-hyprland.md`, section "Frame Analysis: Simulate crashes the solver".
None of them needs Inventor.

| File | What it does |
|---|---|
| `mt.c` | 4 threads write to one transacted file at once (what `rkernel.exe` does). Wine 11.20: `Assertion failed: blockIndex != nextBlock`. Fixed: `0 failures` |
| `trunc.c` | truncate a stream to 0 in a transacted storage, commit, check the tree. Wine 11.20: 8 failures (the file name shows up as an element). Fixed: `0 failures` |
| `fuzz.c` | random single-threaded operations (create/write/set size/read/destroy/commit/revert, nested transacted storages), record and replay |
| `run-seeds.sh` | runs `fuzz.exe` over many seeds, one line per bad seed |
| `ddmin.py` | shrinks a recorded run to the few steps that still fail |

## Build

Any MinGW-w64 cross compiler; the one used was
[llvm-mingw](https://github.com/mstorsjo/llvm-mingw) (no install, unpack and
put `bin/` in `PATH`). On Arch `mingw-w64-gcc` works too
(`x86_64-w64-mingw32-gcc`).

```bash
for p in mt trunc fuzz; do
    x86_64-w64-mingw32-clang -g -O1 -o $p.exe $p.c -lole32 -luuid
done
```

## Run

```bash
export WINEPREFIX=/tmp/ole32-test        # a throw-away prefix
wine mt.exe 3                            # threads
wine trunc.exe                           # truncate + commit
WINE=$(command -v wine) bash run-seeds.sh 1 300 1500   # fuzzing, ~5 min
```

To compare an unfixed and a fixed ole32 side by side, use two copies of the
Wine tree (only `lib/wine/x86_64-windows/ole32.dll` differs) and two prefixes,
and run each in its own directory - `fuzz.exe` and `mt.exe` write their files
into the current directory, two runs in one directory disturb each other.

A `WINEDLLOVERRIDES=ole32=n` with an `ole32.dll` next to the program does
**not** work: Wine's own DLLs (combase) then fail to delay-load it. Replace the
DLL in a copy of the Wine tree instead.

## Shrinking a failing seed

```bash
FZREC="$(wine winepath -w "$PWD/s26.txt")" wine fuzz.exe 26 1 1500   # record
FZREP="$(wine winepath -w "$PWD/s26.txt")" wine fuzz.exe 0 1 100000  # replay
WINE=$(command -v wine) python3 ddmin.py s26.txt min26.txt TransactedSnapshotImpl_StreamLink
```

The pattern is something from the output that marks the failure - a function
name from the backtrace (needs an `ole32.dll` with debug info, i.e. built from
source), or `fuzz.stg dir` together with `FZDUMP=1` for a broken tree. Seed 26
went from 1306 steps to 18, then (looking for the broken tree only) to 8.
