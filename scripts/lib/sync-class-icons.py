#!/usr/bin/env python3
"""Copy the per-user file type registration Inventor writes to the machine classes.

Inventor registers its document types per user on start:
HKCU\\Software\\Classes\\.idw -> Inventor.DrawingDocument and
HKCU\\Software\\Classes\\Inventor.PartDocument\\DefaultIcon -> SrvRes.dll,N.
Its installer left the old "I" icons (Inventor.exe,N) in HKLM\\Software\\Classes,
and some extensions (.idw) have no class there at all. On Windows
HKEY_CLASSES_ROOT shows the per-user values; Wine's shell32 reads HKLM, so the
New dialog showed old or blank icons.

Copied: DefaultIcon values that mention Autodesk/Inventor, and the class of
file extensions that point to an Inventor/Autodesk/AutoCAD class.

Usage: sync-class-icons.py PREFIX OUT.reg
         Writes OUT.reg with the HKLM values that differ (nothing if all match)
         and prints how many.
       sync-class-icons.py --list PREFIX
         Prints "subkey<TAB>value" (subkey below Software\\Classes) for a check
         while Inventor runs: it writes the old icons to HKCR again on start.
"""
import re
import sys

KEY = re.compile(r'^\[Software\\\\Classes\\\\([^\]]+?)\]', re.I)
ICON = re.compile(r"autodesk|inventor", re.I)
CLASS = re.compile(r'^@="(Inventor\.|Autodesk\.|AutoCAD\.)', re.I)


def wanted(path):
    """{lower subkey: (subkey, raw @= line)} of the values we copy."""
    found, cur = {}, None
    try:
        f = open(path, encoding="utf-8", errors="surrogateescape")
    except OSError:
        return found
    with f:
        for line in f:
            if line.startswith("["):
                m = KEY.match(line)
                cur = m.group(1) if m else None
            elif cur is not None and line.startswith('@="'):
                value = line.rstrip("\n")
                low = cur.lower()
                if (low.endswith("\\\\defaulticon") and ICON.search(value)) or \
                   (low.startswith(".") and "\\\\" not in low and CLASS.match(value)):
                    found[low] = (cur, value)
    return found


def unescape(value):
    v = value[3:-1] if value.startswith('@="') and value.endswith('"') else value
    return v.replace('\\\\', '\\').replace('\\"', '"')


def main():
    if sys.argv[1] == "--list":
        for low, (name, value) in sorted(wanted(sys.argv[2] + "/user.reg").items()):
            print("%s\t%s" % (name.replace("\\\\", "\\"), unescape(value)))
        return
    prefix, out = sys.argv[1], sys.argv[2]
    user = wanted(prefix + "/user.reg")
    machine = {}
    try:
        with open(prefix + "/system.reg", encoding="utf-8", errors="surrogateescape") as f:
            cur = None
            for line in f:
                if line.startswith("["):
                    m = KEY.match(line)
                    cur = m.group(1).lower() if m else None
                elif cur in user and line.startswith('@="'):
                    machine[cur] = line.rstrip("\n")
    except OSError:
        pass
    lines = []
    for low, (name, value) in sorted(user.items()):
        if machine.get(low) == value:
            continue
        lines.append("[HKEY_LOCAL_MACHINE\\Software\\Classes\\%s]\r\n%s\r\n\r\n"
                     % (name.replace("\\\\", "\\"), value))
    if lines:
        with open(out, "w", encoding="utf-8", newline="") as f:
            f.write("Windows Registry Editor Version 5.00\r\n\r\n")
            f.writelines(lines)
    print(len(lines))


if __name__ == "__main__":
    main()
