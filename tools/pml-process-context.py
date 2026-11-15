#!/usr/bin/env python3
"""What a process was working on when it started another one, from a
Process Monitor capture: the installer files (.msi, .mst, .msp, .admeta,
.xml) its parent had opened before the child was created, and the child's
command line. Answers "which package's action started this program".

Usage: pml-process-context.py CAPTURE.PML --child Inventor.exe [--last 15]
Needs the procmon-parser package. Paths are printed with user names and SIDs
masked; nothing else from the files.
"""
import argparse
import collections
import re
import struct
import sys

from procmon_parser import ProcmonLogsReader

INTEREST = re.compile(r"\.(msi|mst|msp|admeta|adix|xml|json)$", re.I)


def mask(s):
    s = re.sub(r"S-1-5-21(-\d+){3,4}", "SID", s or "")
    s = re.sub(r"(?i)(\\users\\)(?!public\\|default\\)[^\\\" ]+", r"\1USER", s)
    return re.sub(r"\b[0-9A-Fa-f]{16,}\b", "HEX", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pml", nargs="+")
    ap.add_argument("--child", required=True, help="image name of the started program, e.g. Inventor.exe")
    ap.add_argument("--cmd", default="", help="regular expression its command line must match")
    ap.add_argument("--last", type=int, default=15)
    a = ap.parse_args()
    # 1. the child processes and their parents, from the process tables
    children = {}
    for p in a.pml:
        with open(p, "rb") as f:
            r = ProcmonLogsReader(f, should_get_stacktrace=False, should_get_details=False)
            for pr in r.processes():
                if (pr.process_name or "").lower() == a.child.lower() and re.search(a.cmd, pr.command_line or "", re.I):
                    children[pr.pid] = pr
    if not children:
        sys.exit("no %s process in the captures" % a.child)
    parents = {pr.parent_pid for pr in children.values()}
    for pr in children.values():
        print("== %s(%d) parent pid %d: %s" % (pr.process_name, pr.pid, pr.parent_pid, mask(pr.command_line)[:200]))
    # 2. installer files the parents opened before the child's first event
    opened = collections.defaultdict(lambda: collections.deque(maxlen=a.last))
    first = {}
    for p in a.pml:
        with open(p, "rb") as f:
            r = ProcmonLogsReader(f, should_get_stacktrace=False, should_get_details=False)
            for i in range(len(r)):
                try:
                    ev = r[i]
                except Exception:
                    continue
                pid = ev.process.pid
                if pid in children and pid not in first:
                    first[pid] = True
                    pp = children[pid].parent_pid
                    print("-- first event of pid %d; installer files parent %d opened before (oldest first):" % (pid, pp))
                    for e in opened[pp]:
                        print("     " + e)
                    if len(first) == len(children):
                        return
                elif pid in parents:
                    op = ev.operation.name if hasattr(ev.operation, "name") else str(ev.operation)
                    path = ev.path or ""
                    if op == "CreateFile" and INTEREST.search(path):
                        entry = mask(path)
                        if not opened[pid] or opened[pid][-1] != entry:
                            opened[pid].append(entry)


if __name__ == "__main__":
    main()
