#!/usr/bin/env python3
"""Which process wrote a registry key or file, from a Process Monitor capture.

Prints, for the first matching write events: time, operation, the path
(user names and SIDs masked), the process, its command line and its parent
chain. Observation from outside only (what was called with which arguments).

Usage: pml-who-wrote.py CAPTURE.PML [CAPTURE-1.PML ...] --path REGEX [--max N]
Needs the procmon-parser package (pip install procmon-parser).
"""
import argparse
import re
import struct
import sys

from procmon_parser import ProcmonLogsReader

WRITES = {"RegSetValue", "RegCreateKey", "WriteFile", "CreateFile", "SetRenameInformationFile"}


def mask(s):
    s = re.sub(r"S-1-5-21(-\d+){3,4}", "SID", s or "")
    s = re.sub(r"(?i)(\\users\\)(?!public\\|default\\)[^\\\" ]+", r"\1USER", s)
    s = re.sub(r"\b[0-9A-Fa-f]{16,}\b", "HEX", s)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pml", nargs="+")
    ap.add_argument("--path", required=True, help="regular expression, case-insensitive")
    ap.add_argument("--max", type=int, default=10)
    a = ap.parse_args()
    rx = re.compile(a.path, re.I)
    found, procs = 0, {}
    for p in a.pml:
        with open(p, "rb") as f:
            reader = ProcmonLogsReader(f, should_get_stacktrace=False, should_get_details=True)
            bad = 0
            print("%s: %d events, %d processes" % (p.rsplit("/", 1)[-1], len(reader), len(reader.processes())), file=sys.stderr)
            for i in range(len(reader)):
                try:
                    ev = reader[i]
                except (KeyError, IndexError, ValueError, struct.error):
                    bad += 1    # an event whose process is not in this file's table
                    continue
                pr = ev.process
                procs.setdefault(pr.pid, pr)
                op = ev.operation.name if hasattr(ev.operation, "name") else str(ev.operation)
                if op not in WRITES or not rx.search(ev.path or ""):
                    continue
                if op == "CreateFile" and "Write" not in str((ev.details or {}).get("Desired Access", "")):
                    continue
                chain, cur, seen = [], procs.get(pr.parent_pid), set()
                while cur is not None and cur.pid not in seen and len(chain) < 6:
                    seen.add(cur.pid)
                    chain.append("%s(%d)" % (cur.process_name, cur.pid))
                    cur = procs.get(cur.parent_pid)
                print("%s %s %s" % (ev.date() if callable(getattr(ev, "date", None)) else "", op, mask(ev.path)))
                print("    process: %s(%d)  parents: %s" % (pr.process_name, pr.pid, " <- ".join(chain) or "?"))
                print("    command: %s" % mask(pr.command_line)[:400])
                found += 1
                if found >= a.max:
                    return
            if bad:
                print("%s: %d events skipped (unreadable or process not in the table)" % (p.rsplit("/", 1)[-1], bad), file=sys.stderr)
    if not found:
        print("no write matched", file=sys.stderr)


if __name__ == "__main__":
    main()
