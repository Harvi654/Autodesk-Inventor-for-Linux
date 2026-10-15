#!/usr/bin/env python3
"""Small helpers for .reg files exported by hivexregedit (used by import-file-types.sh).

  filter EXPORT OUT GUIDS YEAR
      From a full UsrClass.dat export (HKCU\\Software\\Classes of the Windows user)
      keep the Inventor file types: every extension whose ProgID starts with
      "Inventor.", those ProgIDs, and the CLSID keys they point to (shell
      extensions for icons/thumbnails/property pages). Shell verbs
      (shell\\open\\command, protocol\\...) are left out: they hold 8.3 paths of
      the Windows disk, and Inventor registers working ones itself under Wine.
      Writes the referenced GUIDs to GUIDS (one per line).
  fix EXPORT PREFIX OUT YEAR
      Re-root a hivexregedit export under PREFIX and fix paths.

Both turn hex(1) strings into plain "strings" and replace Windows 8.3 path
parts (PROGRA~1, ...) with long names, which Wine does not know.
"""
import re
import sys

GUID = re.compile(r"\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}")


def read_sections(path):
    """[(keypath, [value lines])] with continuation lines joined."""
    sections, cur, buf = [], None, ""
    for raw in open(path, encoding="utf-8", errors="replace"):
        line = buf + raw.rstrip("\r\n")
        if line.endswith("\\") and not line.startswith("["):
            buf = line[:-1].strip()
            continue
        buf = ""
        if line.startswith("[") and line.endswith("]"):
            cur = (line[1:-1].lstrip("\\"), [])
            sections.append(cur)
        elif cur is not None and line.strip():
            cur[1].append(line)
    return sections


def split_value(line):
    """'"name"=data' or '@=data' -> (name or None, data)."""
    if line.startswith("@="):
        return None, line[2:]
    m = re.match(r'^"((?:[^"\\]|\\.)*)"=(.*)$', line)
    return (m.group(1), m.group(2)) if m else (None, None)


def decode_hex1(data):
    if not data.startswith("hex(1):"):
        return None
    hexs = data[7:].replace(" ", "")
    b = bytes(int(x, 16) for x in hexs.split(",") if x)
    return b.decode("utf-16-le", "replace").rstrip("\0")


def fix_paths(s, year):
    for short, long in (("PROGRA~1", "Program Files"), ("PROGRA~2", "Program Files (x86)"),
                        ("COMMON~1", "Common Files"), ("INVENT~1", f"Inventor {year}")):
        s = re.sub(re.escape(short), long, s, flags=re.I)
    return s


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def fix_line(line, year):
    name, data = split_value(line)
    if data is None:
        return line
    text = decode_hex1(data)
    if text is None:
        return line
    lhs = "@" if name is None else f'"{name}"'
    return f'{lhs}="{esc(fix_paths(text, year))}"'


def default_value(lines):
    for l in lines:
        name, data = split_value(l)
        if name is None and data is not None:
            return decode_hex1(data) or ""
    return ""


def write(out, sections, prefix, year):
    with open(out, "w", encoding="utf-8") as f:
        f.write("Windows Registry Editor Version 5.00\r\n\r\n")
        for key, lines in sections:
            f.write(f"[{prefix}\\{key}]\r\n" if key else f"[{prefix}]\r\n")
            for l in lines:
                f.write(fix_line(l, year) + "\r\n")
            f.write("\r\n")


def cmd_filter(export, out, guids_out, year):
    secs = read_sections(export)
    top = lambda k: k.split("\\", 1)[0].lower()
    progids = set()
    exts = set()
    for key, lines in secs:
        if "\\" not in key and key.startswith("."):
            v = default_value(lines)
            if v.lower().startswith("inventor."):
                exts.add(key.lower())
                progids.add(v.lower())
    for key, lines in secs:
        if "\\" not in key and key.lower().startswith("inventor."):
            progids.add(key.lower())
    skip = re.compile(r"\\(shell|protocol)(\\|$)", re.I)
    kept = [(k, l) for k, l in secs
            if top(k) in exts | progids and not skip.search(k)]
    guids = set()
    for k, lines in kept:
        guids.update(g.upper() for g in GUID.findall(k))
        for l in lines:
            _, data = split_value(l)
            t = decode_hex1(data) if data else None
            if t:
                guids.update(g.upper() for g in GUID.findall(t))
    # shell-extension interface IDs used as ShellEx key names are not classes
    iface = {"{00021500-0000-0000-C000-000000000046}", "{BB2E617C-0920-11D1-9A0B-00C04FC2D6C1}",
             "{E357FCCD-A995-4576-B01F-234630154E96}", "{8895B1C6-B41F-4C1C-A562-0D564250836F}"}
    guids -= iface
    for k, l in secs:
        parts = k.split("\\")
        for i in range(len(parts) - 1):
            if parts[i].lower() == "clsid" and parts[i + 1].upper() in guids and \
                    all(p.lower() == "wow6432node" for p in parts[:i]):
                kept.append((k, l))
                break
    write(out, kept, "HKEY_CURRENT_USER\\Software\\Classes", year)
    open(guids_out, "w").write("\n".join(sorted(guids)) + "\n")
    print(f"{len(exts)} extensions, {len(progids)} ProgIDs, {len(guids)} classes, {len(kept)} keys")


def cmd_fix(export, prefix, out, year):
    write(out, read_sections(export), prefix, year)


if __name__ == "__main__":
    if sys.argv[1] == "filter":
        cmd_filter(*sys.argv[2:6])
    elif sys.argv[1] == "fix":
        cmd_fix(*sys.argv[2:6])
    else:
        sys.exit("usage: regfilter.py filter EXPORT OUT GUIDS YEAR | fix EXPORT PREFIX OUT YEAR")
