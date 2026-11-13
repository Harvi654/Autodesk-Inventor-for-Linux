#!/usr/bin/env python3
"""Registry keys and value names that a Windows .reg export has and a Wine
prefix does not (names only, no data - exports can hold serial numbers).

Usage: regdiff.py WINDOWS.reg PREFIX/system.reg [filter-regex]
The Windows export may be UTF-16 (regedit default) or UTF-8."""
import re
import sys


def read_text(path):
    raw = open(path, 'rb').read()
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return raw.decode('utf-16')
    return raw.decode('utf-8', 'replace')


VAL = re.compile(r'^\s*(@|"((?:[^"\\]|\\.)*)")\s*=')


def parse(text, wine):
    keys = {}
    cur = None
    for line in text.splitlines():
        if line.startswith('['):
            name = line[1:line.index(']')] if ']' in line else line[1:]
            if wine:
                name = 'HKEY_LOCAL_MACHINE\\' + name.replace('\\\\', '\\')
            cur = keys.setdefault(name.lower(), (name, set()))[1]
            continue
        if cur is None:
            continue
        m = VAL.match(line)
        if m:
            v = '(Default)' if m.group(1) == '@' else m.group(2).replace('\\\\', '\\')
            cur.add(v.lower())
    return keys


win = parse(read_text(sys.argv[1]), False)
lin = parse(read_text(sys.argv[2]), True)
flt = re.compile(sys.argv[3], re.I) if len(sys.argv) > 3 else None
USER_RE = re.compile(r'(?i)(\\Users\\)[^\\]+')

present = set()
for k in lin:
    parts = k.split('\\')
    for i in range(1, len(parts) + 1):
        present.add('\\'.join(parts[:i]))

missing_keys, missing_vals = [], []
for k, (name, vals) in sorted(win.items()):
    if flt and not flt.search(name):
        continue
    if k not in present:
        missing_keys.append(name)
        continue
    for v in sorted(vals - (lin[k][1] if k in lin else set())):
        missing_vals.append('%s  ->  %s' % (name, v))

# Report only the top of each missing subtree.
tops = []
for name in missing_keys:
    if not any(name.lower().startswith(t.lower() + '\\') for t in tops):
        tops.append(name)
print('== keys missing in the prefix (top of each subtree): %d' % len(tops))
for t in tops:
    print(USER_RE.sub(r'\1USER', t))
print('\n== values missing in keys both have: %d' % len(missing_vals))
for line in missing_vals:
    print(USER_RE.sub(r'\1USER', line))
