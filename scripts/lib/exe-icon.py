#!/usr/bin/env python3
"""Save the largest image of an icon group in a Windows .exe as PNG.

Usage: exe-icon.py EXE OUT.png [GROUP]
GROUP defaults to the lowest-numbered icon group - the program's own icon
(Inventor.exe: 130, the "I PRO" logo; the others are document icons).
Needs 7z (to read the PE resources) and ImageMagick for icons not stored as PNG.
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile


def main():
    exe, out = sys.argv[1], sys.argv[2]
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["7z", "x", "-y", "-o" + tmp, exe, ".rsrc/*ICON*"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        groups = os.path.join(tmp, ".rsrc", "GROUP_ICON")
        names = sorted(os.listdir(groups), key=lambda n: (not n.isdigit(), int(n) if n.isdigit() else 0, n))
        group = sys.argv[3] if len(sys.argv) > 3 else names[0]
        data = open(os.path.join(groups, group), "rb").read()
        best = None
        for i in range(struct.unpack_from("<H", data, 4)[0]):
            w, _h, _c, _r, _p, bits, _size, nid = struct.unpack_from("<BBBBHHIH", data, 6 + 14 * i)
            key = (w or 256, bits)
            if best is None or key > best[0]:
                best = (key, nid)
        nid = best[1]
        icons = os.path.join(tmp, ".rsrc", "ICON")
        png, ico = os.path.join(icons, str(nid)), os.path.join(icons, "%d.ico" % nid)
        if os.path.exists(png):            # 256 px icons are stored as PNG
            shutil.copyfile(png, out)
        else:
            im = shutil.which("magick") or shutil.which("convert")
            subprocess.run([im, ico, out], check=True)
    print(out)


if __name__ == "__main__":
    main()
