#!/usr/bin/env python3
"""Copy the per-user file type icons Inventor registers to the machine classes.

Inventor registers its document types per user on start
(HKCU\\Software\\Classes\\Inventor.PartDocument\\DefaultIcon -> SrvRes.dll,N),
while its installer left the old "I" icons (Inventor.exe,N) in
HKLM\\Software\\Classes. On Windows HKEY_CLASSES_ROOT shows the per-user
value; Wine's shell32 reads HKLM, so the New dialog showed the old icons.

Usage: sync-class-icons.py PREFIX OUT.reg
Writes OUT.reg with the HKLM DefaultIcon values that differ (nothing if all
match) and prints how many.
"""
import re
import sys

KEY = re.compile(r'^\[Software\\\\Classes\\\\([^\]]+?)\\\\DefaultIcon\]', re.I)


def default_icons(path):
    icons, cur = {}, None
    try:
        f = open(path, encoding="utf-8", errors="surrogateescape")
    except OSError:
        return icons
    with f:
        for line in f:
            if line.startswith("["):
                m = KEY.match(line)
                cur = m.group(1) if m else None
            elif cur is not None and line.startswith('@="'):
                icons[cur.lower()] = (cur, line.rstrip("\n"))
    return icons


def main():
    prefix, out = sys.argv[1], sys.argv[2]
    user = default_icons(prefix + "/user.reg")
    machine = default_icons(prefix + "/system.reg")
    lines = []
    for low, (name, value) in sorted(user.items()):
        if not re.search(r"autodesk|inventor", value, re.I):
            continue
        if machine.get(low, (None, None))[1] == value:
            continue
        lines.append("[HKEY_LOCAL_MACHINE\\Software\\Classes\\%s\\DefaultIcon]\r\n%s\r\n\r\n"
                     % (name.replace("\\\\", "\\"), value))
    if lines:
        with open(out, "w", encoding="utf-8", newline="") as f:
            f.write("Windows Registry Editor Version 5.00\r\n\r\n")
            f.writelines(lines)
    print(len(lines))


if __name__ == "__main__":
    main()
