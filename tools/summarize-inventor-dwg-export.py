#!/usr/bin/env python3
# Original, AI-assisted (Codex), LGPL-2.1-or-later.
# Inventor export parser extracted from https://github.com/Harvi654/winum/commit/0768272ae305a7c7bf10e2cf6b3d1d8faca7909c
import argparse
from collections import Counter, defaultdict
from pathlib import Path
import re


LINE = re.compile(r'^([0-9a-f]+):([0-9a-f]+):(trace|warn|err|fixme):(\w+):(\w+) (.*)$', re.I)

LOADED = re.compile(r'Loaded L?"([^"\n]+)" at (?:0x)?([a-f0-9]+):', re.I)

REQUEST = re.compile(r'\bname=L"([^"\r\n]+)".*\bdisp=(\d+) options=([0-9a-f]+)\b', re.I)

FATAL = re.compile(r'^Unhandled exception code (?:0x)?([0-9a-f]{8})\b', re.I)

FILE_PATH = re.compile(r'L"([^"\r\n]+)"')

COM_CHANNELS = {'ole', 'combase', 'rpc', 'storage'}

RELAY_LINE = re.compile(r'^([a-f0-9]+):([a-f0-9]+):(Call|Ret)\s+([a-z0-9_.]+)\((.*)$', re.I)

RELAY_VALUE = re.compile(r'^\) retval=(?:0x)?([a-f0-9]{1,16})\b', re.I)

EXPORT_TARGET = re.compile(r'/winum-export-check/inventor-export[^/]*\.dwg$')

FILE_ACCESS = re.compile(r'\baccess=([a-f0-9]{1,8})\b', re.I)

RUNTIME_VERSION = re.compile(r'/dotnet/shared/microsoft\.netcore\.app/([0-9.]+)/coreclr\.dll$')

EXPORT_PROCESSES = {'inventor.exe', 'dwgviewr.exe'}

EXPORT_MODULES = {'coreclr.dll', 'combase.dll', 'ole32.dll', 'oleaut32.dll', 'rpcrt4.dll', 'shell32.dll'}

RELAY_APIS = {
    'comdlg32.getopenfilenamew', 'comdlg32.getsavefilenamew', 'kernelbase.movefilewithprogressw',
    'kernelbase.getfileattributesexw', 'ntdll.ntqueryfullattributesfile', 'ntdll.ntsetinformationfile',
    'combase.cocreateinstance', 'combase.cogetclassobject',
}

def basename(path):
    return re.split(r'[\\/]', path.lower())[-1]

def scan_inventor_export(work):
    output_dir = work / 'inventor-prefix/drive_c/winum-export-check'
    outputs = sorted(path for path in output_dir.glob('inventor-export*.dwg') if path.is_file())
    print(f'inventor_export_files={len(outputs)}')
    for path in outputs:
        with path.open('rb') as drawing:
            signature = drawing.read(6)
        version = signature.decode('ascii') if re.fullmatch(rb'AC[0-9]{4}', signature) else 'other'
        print(f'inventor_export_dwg={version} bytes={path.stat().st_size}')

    log = max((work / 'logs').glob('inventor-*.log'), key=lambda path: path.stat().st_mtime_ns, default=None)
    if log is None:
        print('inventor_export_trace=log_missing')
        return

    processes, modules, versions, anchor = {}, defaultdict(set), defaultdict(set), {}
    events, rename_requests, ole_messages, faults = Counter(), Counter(), Counter(), Counter()
    with log.open(encoding='utf-8', errors='replace') as stream:
        for line in stream:
            if relay := RELAY_LINE.match(line):
                pid, _, action, name, arguments = relay.groups()
                name = name.lower().replace('.dll.', '.')
                if (pid in anchor and name in RELAY_APIS and action == 'Ret' and
                        (returned := RELAY_VALUE.match(arguments))):
                    phase = 'after_rename_request' if rename_requests[pid] else 'after_write_request'
                    events[pid, phase, name, int(returned[1], 16) & 0xffffffff] += 1
                continue
            if not (match := LINE.match(line.rstrip('\r\n'))):
                continue
            pid, _, level, channel, function, message = match.groups()
            if channel == 'loaddll' and (loaded := LOADED.match(message)):
                path, _ = loaded.groups()
                name = basename(path)
                if name in EXPORT_PROCESSES:
                    processes[pid] = name
                elif name in EXPORT_MODULES:
                    modules[pid].add(name)
                    if version := RUNTIME_VERSION.search(re.sub(r'[\\/]+', '/', path).lower()):
                        versions[pid].add(version[1])
            if pid not in processes:
                continue
            if channel == 'file' and level == 'trace':
                if function == 'MoveFileWithProgressW' and len(paths := FILE_PATH.findall(message)) >= 2:
                    if EXPORT_TARGET.search(re.sub(r'[\\/]+', '/', paths[1]).lower()):
                        rename_requests[pid] += 1
                        anchor.setdefault(pid, 'rename_request')
                elif function == 'NtCreateFile' and (request := REQUEST.search(message)):
                    if (EXPORT_TARGET.search(re.sub(r'[\\/]+', '/', request[1]).lower()) and
                            (access := FILE_ACCESS.search(message)) and int(access[1], 16) & 0x40000006):
                        anchor.setdefault(pid, 'write_request')
            elif pid in anchor and channel in COM_CHANNELS:
                ole_messages[pid] += 1
            elif pid in anchor and channel == 'seh' and (fatal := FATAL.match(message)):
                faults[pid, fatal[1].lower()] += 1

    if not anchor:
        print('inventor_export_trace=no_target_request')
    for pid, first in anchor.items():
        print(f'inventor_export_trace={first} process={processes[pid]} '
              f'rename_requests={rename_requests[pid]} com_messages={ole_messages[pid]}')
        print(f'inventor_export_modules={",".join(sorted(modules[pid])) or "none"} '
              f'coreclr={",".join(sorted(versions[pid])) or "unconfirmed"}')
        returns = [(phase, name, status, count) for (process, phase, name, status), count in events.items()
                   if process == pid]
        for phase, name, status, count in sorted(returns)[:24]:
            print(f'inventor_export_return={name} phase={phase} retval=0x{status:08x} count={count}')
        if len(returns) > 24:
            print(f'inventor_export_omitted={len(returns) - 24}')
        for (process, code), count in faults.items():
            if process == pid:
                print(f'inventor_export_fault=0x{code} count={count}')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Summarize an Inventor DWG export trace.")
    parser.add_argument("work", type=Path, help="directory created by trace-inventor-dwg-export.sh")
    work = parser.parse_args().work
    for subdirectory in ("inventor-prefix/drive_c/winum-export-check", "logs"):
        if not (work / subdirectory).is_dir():
            parser.error(f"missing trace directory: {work / subdirectory}")
    scan_inventor_export(work)
