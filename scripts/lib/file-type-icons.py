#!/usr/bin/env python3
"""Extract the icons Inventor registered for its file types as PNGs.

Usage: file-type-icons.py PREFIX OUTDIR NAME EXT [EXT ...]
Writes OUTDIR/NAME-EXT.png (e.g. autodesk-inventor-2026-ipt.png) for every
extension whose DefaultIcon could be found in the Wine prefix's registry and
prints "EXT ok" or "EXT -" per extension. Needs 7z (and ImageMagick for icons
not stored as PNG), like exe-icon.py.

Lookup, as Windows does it: HKCR\\.ext -> ProgID (default value, following
CurVer) -> ProgID\\DefaultIcon = "path,index". A negative index is a resource
id, a positive one the position among the file's icon groups.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def read_reg(path):
    """Wine .reg text -> {lower-case key: {lower-case value name: string}}."""
    keys, cur = {}, None
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return keys
    for line in text.splitlines():
        if line.startswith("["):
            m = re.match(r"\[(.*?)\]", line)
            cur = keys.setdefault(m.group(1).replace("\\\\", "\\").lower(), {}) if m else None
        elif cur is not None:
            m = re.match(r'^(@|"(?:[^"\\]|\\.)*")=(?:str\(\d\):)?"((?:[^"\\]|\\.)*)"$', line)
            if m:
                name = "" if m.group(1) == "@" else m.group(1)[1:-1]
                cur[name.lower()] = m.group(2).replace("\\\\", "\\").replace('\\"', '"')
    return keys


def lookup(regs, key, name=""):
    for prefix, reg in regs:
        v = reg.get((prefix + key).lower(), {}).get(name)
        if v:
            return v
    return None


def main():
    prefix, outdir, base, exts = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
    os.makedirs(outdir, exist_ok=True)
    regs = [("software\\classes\\", read_reg(os.path.join(prefix, "user.reg"))),
            ("software\\classes\\", read_reg(os.path.join(prefix, "system.reg")))]
    for ext in exts:
        ok = False
        progid = lookup(regs, "." + ext)
        for _ in range(3):                       # versioned ProgIDs: follow CurVer
            cur = progid and lookup(regs, progid + "\\CurVer")
            if not cur or cur == progid:
                break
            progid = cur
        icon = progid and lookup(regs, progid + "\\DefaultIcon")
        if icon:
            path, _, idx = icon.strip('"').rpartition(",")
            if not path:
                path, idx = icon.strip('"'), "0"
            path = os.path.expandvars(path.strip('"'))
            m = re.match(r"^([A-Za-z]):\\(.*)$", path)
            if m and m.group(1).lower() == "c":
                linux = os.path.join(prefix, "drive_c", *m.group(2).split("\\"))
                out = os.path.join(outdir, "%s-%s.png" % (base, ext))
                if linux.lower().endswith(".ico") and os.path.exists(linux):
                    # a plain .ico file: its largest image
                    im = shutil.which("magick") or shutil.which("convert")
                    if im:
                        tmpd = tempfile.mkdtemp()
                        subprocess.run([im, linux, os.path.join(tmpd, "i.png")],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        pngs = sorted(glob.glob(os.path.join(tmpd, "i*.png")), key=os.path.getsize)
                        if pngs:
                            shutil.copyfile(pngs[-1], out)
                            ok = True
                        shutil.rmtree(tmpd, ignore_errors=True)
                    print("%s %s %s" % (ext, "ok" if ok else "-", icon))
                    continue
                try:
                    n = int(idx)
                except ValueError:
                    n = 0
                group = None
                with tempfile.TemporaryDirectory() as tmp:
                    subprocess.run(["7z", "x", "-y", "-o" + tmp, linux, ".rsrc/GROUP_ICON"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    gdir = os.path.join(tmp, ".rsrc", "GROUP_ICON")
                    if os.path.isdir(gdir):
                        names = sorted(os.listdir(gdir),
                                       key=lambda s: (not s.isdigit(), int(s) if s.isdigit() else 0, s))
                        if n < 0 and str(-n) in names:
                            group = str(-n)
                        elif 0 <= n < len(names):
                            group = names[n]
                if group:
                    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "exe-icon.py"), linux, out, group],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    ok = r.returncode == 0 and os.path.exists(out)
        print("%s %s %s" % (ext, "ok" if ok else "-", icon or ""))


if __name__ == "__main__":
    main()
