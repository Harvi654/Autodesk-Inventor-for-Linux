#!/usr/bin/env python3
"""What a process found on Windows (Process Monitor capture) that a Wine
prefix does not have, and the other way round - registry keys, values and
files, up to a given event.

Usage: pml-vs-prefix.py CAPTURE.PML PREFIX [--process acad.exe]
                        [--until N] [--user LINUXUSER] > report.txt

Only existence is compared from the capture (keys, values, files the process
opened successfully or got NAME/PATH NOT FOUND for); for values both sides
have, REG_DWORD and short REG_SZ data are compared too. Names that may hold
secrets (serial, token, password, mail) never have their data printed; user
names, SIDs and the Windows computer name are masked.
"""
import argparse
import os
import re
import sys

from procmon_parser import ProcmonLogsReader
from procmon_parser.consts import get_error_message

ap = argparse.ArgumentParser()
ap.add_argument('pml')
ap.add_argument('prefix')
ap.add_argument('--process', default='acad.exe')
ap.add_argument('--until', type=int, default=None, help='stop at this event index')
ap.add_argument('--user', default=os.environ.get('USER', ''))
a = ap.parse_args()

USER_RE = re.compile(r'(?i)(\\Users\\)[^\\]+')
SID_RE = re.compile(r'S-1-5-21-[0-9-]+')
HOST_RE = re.compile(r'(?i)DESKTOP-[A-Z0-9]+')
SECRET = re.compile(r'(?i)serial|token|passw|mail|secret|licensekey|\bsn\b')
INTEREST = re.compile(r'(?i)autodesk|acad|adsk|adlm|odis|upi|licens|identity|\.pit\b')


def mask(s):
    return HOST_RE.sub('HOST', SID_RE.sub('SID', USER_RE.sub(r'\1USER', s)))


# --- Wine registry files ----------------------------------------------------
def unescape(s):
    return s.replace('\\\\', '\x00').replace('\\"', '"').replace('\x00', '\\')


VALUE_RE = re.compile(r'^(@|"((?:[^"\\]|\\.)*)")=(.*)$')


def load_wine_reg(path):
    keys, cur = {}, None
    lines = open(path, encoding='utf-8', errors='replace').read().split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        while line.endswith('\\') and i + 1 < len(lines):   # hex continuation
            i += 1
            line = line[:-1] + lines[i].strip()
        i += 1
        if line.startswith('['):
            name = unescape(line[1:line.rindex(']')]).lower()
            cur = keys.setdefault(name, {})
            continue
        if cur is None:
            continue
        m = VALUE_RE.match(line)
        if m:
            vname = '(default)' if m.group(1) == '@' else unescape(m.group(2)).lower()
            cur[vname] = m.group(3)
    present = set()
    for k in keys:
        parts = k.split('\\')
        for j in range(1, len(parts) + 1):
            present.add('\\'.join(parts[:j]))
    return keys, present


HKLM, HKLM_P = load_wine_reg(os.path.join(a.prefix, 'system.reg'))
HKCU, HKCU_P = load_wine_reg(os.path.join(a.prefix, 'user.reg'))


def wine_data(raw):
    """Wine's stored value -> comparable (type, data) for SZ and DWORD."""
    if raw.startswith('"'):
        return 'REG_SZ', unescape(raw[1:-1])
    if raw.startswith('str(2):"'):
        return 'REG_EXPAND_SZ', unescape(raw[8:-1])
    if raw.startswith('dword:'):
        return 'REG_DWORD', int(raw[6:], 16)
    return None, None


def candidates(path):
    """Windows registry path -> list of (hive dict, present set, key) to try."""
    p = path.split('\\')
    root, rest = p[0].upper(), '\\'.join(p[1:])
    rest = re.sub(r'(?i)^system\\currentcontrolset', r'System\\ControlSet001', rest).lower()
    if root == 'HKLM':
        return [(HKLM, HKLM_P, rest)]
    if root == 'HKCU':
        return [(HKCU, HKCU_P, rest)]
    if root == 'HKCR':
        return [(HKCU, HKCU_P, 'software\\classes\\' + rest if rest else 'software\\classes'),
                (HKLM, HKLM_P, 'software\\classes\\' + rest if rest else 'software\\classes')]
    if root == 'HKU' and len(p) > 1:
        sid = p[1]
        sub = '\\'.join(p[2:]).lower()
        if sid.startswith('S-1-5-21') and sid.endswith('_Classes'):
            return [(HKCU, HKCU_P, 'software\\classes' + ('\\' + sub if sub else ''))]
        if sid.startswith('S-1-5-21'):
            return [(HKCU, HKCU_P, sub)]
    return []


def key_in_prefix(path):
    c = candidates(path)
    if not c:
        return None
    return any(k in pres for _, pres, k in c)


def value_in_prefix(path):
    """Returns (exists or None if not comparable, raw wine data)."""
    if '\\' not in path:
        return None, None
    key, val = path.rsplit('\\', 1)
    c = candidates(key)
    if not c:
        return None, None
    v = val.lower()
    for hive, _, k in c:
        if k in hive and v in hive[k]:
            return True, hive[k][v]
    return False, None


# --- files ------------------------------------------------------------------
_listing = {}


def real_path(winpath):
    """Case-insensitive lookup of a C:\\ path in the prefix; None if absent,
    False if not comparable."""
    m = re.match(r'(?i)^c:\\(.*)$', winpath)
    if not m:
        return False
    parts = [x for x in m.group(1).split('\\') if x]
    if len(parts) >= 2 and parts[0].lower() == 'users' and parts[1].lower() not in ('public', 'default'):
        parts[1] = a.user
    cur = os.path.join(a.prefix, 'drive_c')
    for part in parts:
        if part in ('.', ''):
            continue
        if cur not in _listing:
            try:
                _listing[cur] = {n.lower(): n for n in os.listdir(cur)}
            except OSError:
                _listing[cur] = {}
        n = _listing[cur].get(part.lower())
        if n is None:
            return None
        cur = os.path.join(cur, n)
    return cur


# --- capture ----------------------------------------------------------------
seen = {}   # (kind, path) -> (first index, windows_found, details)
with open(a.pml, 'rb') as f:
    r = ProcmonLogsReader(f, should_get_stacktrace=False, should_get_details=True)
    end = min(len(r), a.until) if a.until else len(r)
    for i in range(end):
        if i % 200000 == 0:
            print('%d/%d' % (i, end), file=sys.stderr)
        try:
            e = r[i]
        except Exception:
            continue
        if (e.process.process_name or '').lower() != a.process.lower():
            continue
        op = e.operation.name if hasattr(e.operation, 'name') else str(e.operation)
        try:
            res = get_error_message(e.result)
        except Exception:
            res = str(e.result)
        path = e.path or ''
        found = {'SUCCESS': True, 'BUFFER OVERFLOW': True,
                 'NAME NOT FOUND': False, 'PATH NOT FOUND': False}.get(res)
        if found is None:
            continue
        if op in ('RegOpenKey', 'RegCreateKey'):
            kind = 'key'
            if op == 'RegCreateKey' and (e.details or {}).get('Disposition') == 'REG_CREATED_NEW_KEY':
                continue
        elif op == 'RegQueryValue':
            kind = 'value'
        elif op == 'CreateFile':
            kind = 'file'
            d = e.details or {}
            if found and d.get('OpenResult') in ('Created', 'Superseded', 'Overwritten'):
                continue
            if path.startswith('\\') or ':' not in path[:3]:
                continue
        else:
            continue
        k = (kind, path.lower())
        if k not in seen:
            seen[k] = (i, found, path, (e.details or {}) if kind == 'value' else {})

# --- compare ----------------------------------------------------------------
out = {'win_only': [], 'prefix_only': [], 'differs': []}
for (kind, _), (i, found, path, det) in sorted(seen.items(), key=lambda x: x[1][0]):
    if kind == 'key':
        have = key_in_prefix(path)
    elif kind == 'value':
        have, raw = value_in_prefix(path)
    else:
        rp = real_path(path)
        have = None if rp is False else rp is not None
    if have is None:
        continue
    tag = '%9d %-5s %s' % (i, kind, mask(path))
    if found and not have:
        out['win_only'].append(tag)
    elif not found and have:
        out['prefix_only'].append(tag)
    elif found and have and kind == 'value' and 'Data' in det:
        wt, wd = det.get('Type'), det.get('Data')
        lt, ld = wine_data(raw)
        if lt is None or wt not in ('REG_SZ', 'REG_EXPAND_SZ', 'REG_DWORD'):
            continue
        a_, b_ = (str(wd).rstrip('\x00'), str(ld).rstrip('\x00'))
        if wt == 'REG_DWORD' and isinstance(ld, int):
            a_, b_ = str(wd), str(ld)
        if a_.lower() != b_.lower():
            if SECRET.search(path):
                out['differs'].append(tag + '   (data not shown)')
            else:
                out['differs'].append('%s   win=%s  wine=%s' % (tag, mask(a_)[:80], mask(b_)[:80]))

titles = {'win_only': 'found on Windows, MISSING in the prefix',
          'prefix_only': 'NOT found on Windows, PRESENT in the prefix',
          'differs': 'present on both, data differs (SZ/DWORD)'}
for sec in ('win_only', 'prefix_only', 'differs'):
    rows = out[sec]
    hot = [x for x in rows if INTEREST.search(x)]
    rest = [x for x in rows if not INTEREST.search(x)]
    print('\n=== %s: %d (%d Autodesk-related)' % (titles[sec], len(rows), len(hot)))
    for x in hot:
        print(x)
    print('--- others')
    for x in rest:
        print(x)
