#!/usr/bin/env python3
"""Shrink a recorded fuzz.exe operation list (FZREC) to the shortest list
that still shows PATTERN in fuzz.exe's output (delta debugging).

Usage: WINE=/path/to/wine WINEPREFIX=... python3 ddmin.py IN.txt OUT.txt PATTERN
PATTERN is a plain string, e.g. a function name from the crash backtrace
(TransactedSnapshotImpl_StreamLink) or "fuzz.stg dir" with FZDUMP=1 set
(a storage that lists the file name as its own child = broken tree)."""
import os, subprocess, sys

here = os.path.dirname(os.path.abspath(__file__))
wine = os.environ.get('WINE', 'wine')
work = os.path.join(here, 'ddmin-current.txt')
env = dict(os.environ, WINEDEBUG='-all',
           FZREP=subprocess.run([wine, 'winepath', '-w', work], capture_output=True, text=True).stdout.strip())

def bad(lines):
    open(work, 'w').write(''.join(lines))
    try:
        r = subprocess.run([wine, 'fuzz.exe', '0', '1', '100000'], cwd=here, env=env,
                           capture_output=True, text=True, timeout=40)
    except subprocess.TimeoutExpired:
        subprocess.run([os.path.join(os.path.dirname(wine), 'wineserver') if os.sep in wine else 'wineserver', '-k'])
        return False
    return sys.argv[3] in r.stdout + r.stderr

lines = open(sys.argv[1]).readlines()
assert bad(lines), 'the input does not reproduce the pattern'
n = 2
while len(lines) >= 2:
    chunk = max(1, len(lines) // n)
    for i in range(0, len(lines), chunk):
        candidate = lines[:i] + lines[i + chunk:]
        if bad(candidate):
            lines = candidate; n = max(n - 1, 2); print(len(lines), flush=True); break
    else:
        if chunk == 1: break
        n = min(len(lines), n * 2)
open(sys.argv[2], 'w').write(''.join(lines))
print('final', len(lines))
