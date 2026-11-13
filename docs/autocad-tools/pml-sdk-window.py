#!/usr/bin/env python3
"""acad.exe events from the AdskLicensingSDK load until the first
AdskLicensingAgent start or connection to port 44447 (what the SDK does
before it decides). Usage: pml2.py file.PML start_index > out.txt"""
import re
import sys
from procmon_parser import ProcmonLogsReader
from procmon_parser.consts import get_error_message

PML, START = sys.argv[1], int(sys.argv[2])
USER_RE = re.compile(r'(?i)(\\Users\\)[^\\]+')
SID_RE = re.compile(r'S-1-5-21-[0-9-]+')
SKIP_OPS = re.compile(r'Thread_|Profiling|Statistics|IRP_MJ_CLOSE|FASTIO_|'
                      r'QueryOpen|CloseFile|RegCloseKey|RegQueryKey$|'
                      r'QueryStandardInformation|QueryBasicInformation')
NOISE_PATH = re.compile(r'(?i)\\fonts\\|\.mui$|\\winsxs\\|\\locale\\|\.nls$')

with open(PML, 'rb') as f:
    r = ProcmonLogsReader(f, should_get_stacktrace=False,
                          should_get_details=False)
    prev = None
    for i in range(START, min(len(r), START + 600000)):
        try:
            e = r[i]
        except Exception:
            continue
        if (e.process.process_name or '').lower() != 'acad.exe':
            continue
        op = e.operation.name if hasattr(e.operation, 'name') else str(e.operation)
        path = SID_RE.sub('SID', USER_RE.sub(r'\1USER', e.path or ''))
        if SKIP_OPS.search(op) or NOISE_PATH.search(path):
            continue
        if op == 'Load_Image' and '\\windows\\' in path.lower():
            continue
        try:
            res = get_error_message(e.result)
        except Exception:
            res = str(e.result)
        line = '%s %s %s' % (op, path, res)
        if line != prev:
            print('%9d tid=%s %s' % (i, e.tid, line))
            prev = line
        if ((op == 'Process_Create' and 'adsklicensingagent' in path.lower())
                or ':44447' in path):
            print('--- stop at', i)
            break
