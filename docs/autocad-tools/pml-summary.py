#!/usr/bin/env python3
"""Summarise acad.exe's first run from a Process Monitor capture (.PML).

Writes text files next to the output prefix:
  <out>-procs.txt     process tree (pid, parent, session, image, command line)
  <out>-window.txt    acad.exe operations before/after AdskLicensingSDK load
  <out>-lic.txt       every licensing-related path touched by any process
User names, SIDs and sign-in callback parameters (code=, state=) are masked;
the output still stays local (paths, machine names).
"""
import re
import sys
from collections import OrderedDict

from procmon_parser import ProcmonLogsReader
from procmon_parser.consts import get_error_message

PML, OUT = sys.argv[1], sys.argv[2]
BEFORE, AFTER = 400, 200

USER_RE = re.compile(r'(?i)(\\Users\\)[^\\]+')
SID_RE = re.compile(r'S-1-5-21-[0-9-]+')
CB_RE = re.compile(r'(?i)\b(code|state)=[^&"\s]+')
LIC_RE = re.compile(r'(?i)licens|adlm|adsk|genuine|\bags\b|agsservice|upi|\.pit\b|'
                    r'identity|idservices|clic|odis|programdata\\autodesk')
NOISE_OPS = {'Thread_Create', 'Thread_Exit', 'Thread_Profiling',
             'Process_Profiling', 'Process_Statistics'}
NOISE_PATH = re.compile(r'(?i)\\fonts\\|\.mui$|\\winsxs\\|\\prefetch\\|'
                        r'\\locale\\|\.nls$')


def clean(s):
    s = USER_RE.sub(r'\1USER', s or '')
    return CB_RE.sub(r'\1=<masked>', SID_RE.sub('SID', s))


def res(r):
    try:
        return get_error_message(r)
    except Exception:
        return str(r)


with open(PML, 'rb') as f:
    reader = ProcmonLogsReader(f, should_get_stacktrace=False,
                               should_get_details=False)

    with open(OUT + '-procs.txt', 'w') as o:
        for p in sorted(reader.processes(), key=lambda p: (p.start_time is None, str(p.start_time))):
            name = (p.process_name or '').lower()
            if (LIC_RE.search(p.image_path or '') or 'acad' in name
                    or name in ('services.exe', 'msiexec.exe')):
                o.write('pid=%s ppid=%s sess=%s 64=%s %s | %s\n' % (
                    p.pid, p.parent_pid, p.session, int(p.is_process_64bit),
                    clean(p.image_path), clean(p.command_line)))

    total = len(reader)
    acad = []            # (index, pid, op, path, result)
    lic = OrderedDict()  # (proc, op, path) -> (first index, result, count)
    sdk_at = None
    for i in range(total):
        try:
            e = reader[i]
        except Exception:
            continue
        if i % 500000 == 0:
            print('%d/%d' % (i, total), file=sys.stderr)
        pname = (e.process.process_name or '').lower()
        op = e.operation.name if hasattr(e.operation, 'name') else str(e.operation)
        path = clean(e.path)
        if pname == 'acad.exe' and op not in NOISE_OPS:
            if not NOISE_PATH.search(path):
                acad.append((i, e.process.pid, op, path, res(e.result)))
            if (sdk_at is None and op == 'Load_Image'
                    and 'adsklicensingsdk' in path.lower()):
                sdk_at = len(acad) - 1
        if LIC_RE.search(path) or op == 'Process_Create':
            key = (pname, op, path)
            if key in lic:
                a, r, n = lic[key]
                lic[key] = (a, r, n + 1)
            else:
                lic[key] = (i, res(e.result), 1)

with open(OUT + '-window.txt', 'w') as o:
    o.write('acad.exe events kept: %d, SDK load at kept index: %s\n'
            % (len(acad), sdk_at))
    if sdk_at is not None:
        lo, hi = max(0, sdk_at - BEFORE), min(len(acad), sdk_at + AFTER)
        prev = None
        for k in range(lo, hi):
            i, pid, op, path, r = acad[k]
            line = '%s %s %s' % (op, path, r)
            if line == prev:
                continue
            prev = line
            mark = '>>>' if k == sdk_at else '   '
            o.write('%s %9d pid=%s %s\n' % (mark, i, pid, line))

with open(OUT + '-lic.txt', 'w') as o:
    for (pname, op, path), (i, r, n) in lic.items():
        o.write('%9d %-22s %-20s %s %s x%d\n' % (i, pname, op, path, r, n))

print('done:', OUT + '-procs.txt', OUT + '-window.txt', OUT + '-lic.txt')
