#!/usr/bin/env python3
"""List the PA19 delta patches in a folder (e.g. a patch cabinet unpacked with
7z) and what Wine's mspatcha needs to apply them.

Usage: pa19-scan.py DIR

Columns: old size, new size, flags, rebase (present = 32-bit executable
handling), "special" pair count (the part Wine does not implement), name.
"""
import os
import struct
import sys

NO_REBASE = 0x00040000
NO_TIMESTAMP = 0x00800000
EXTRA_FLAGS = 0x80000000
INTERLEAVE = 0x40000000
LZX_LARGE = 0x00000004


class R:
    def __init__(self, b):
        self.b, self.p = b, 0

    def u32(self):
        v = struct.unpack_from("<I", self.b, self.p)[0]
        self.p += 4
        return v

    def byte(self):
        v = self.b[self.p]
        self.p += 1
        return v

    def uvli(self):
        # 7 bits per byte, little-endian, the LAST byte has bit 7 set
        v, i, c = 0, 0, 0
        while c < 0x80:
            c = self.b[self.p + i]
            v |= (c & 0x7F) << (7 * i)
            i += 1
        self.p += i
        return v

    def svli(self):
        # sign in bit 6 of the FIRST byte, 6 value bits there, then 7 per byte
        first = self.b[self.p]
        v, i = first & 0x3F, 1
        c = first
        while c < 0x80:
            c = self.b[self.p + i]
            v |= (c & 0x7F) << (7 * i - 1)
            i += 1
        self.p += i
        return -v if first & 0x40 else v


def scan(path):
    b = open(path, "rb").read()
    if b[:4] != b"PA19":
        return None
    r = R(b)
    r.p = 4
    flags = r.u32()
    if flags & EXTRA_FLAGS:
        r.u32()
    if flags & NO_TIMESTAMP:
        r.u32()
    rebase = None
    if not flags & NO_REBASE:
        rebase = r.uvli()
    new_size = r.uvli()
    r.u32()
    n = r.byte()
    old_size = new_size + r.svli()
    r.u32()
    for _ in range(r.byte()):
        r.svli(); r.uvli()
    for _ in range(r.byte()):
        r.svli(); r.svli(); r.uvli()
    special = r.uvli()
    return old_size, new_size, flags, rebase, special, n


def main():
    d = sys.argv[1]
    rows = []
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        if not os.path.isfile(p):
            continue
        try:
            s = scan(p)
        except (IndexError, struct.error):
            s = ("?",) * 6
        if s:
            rows.append(s + (f,))
    special = [x for x in rows if x[4] not in (0, "?")]
    big = [x for x in rows if isinstance(x[0], int) and x[0] > (32 << 20 if x[2] & LZX_LARGE else 8 << 20)]
    print("%d PA19 patches, %d need 32-bit special processing, %d have an old file larger than the window"
          % (len(rows), len(special), len(big)))
    for x in special:
        print("special %3s  old %9s new %9s flags %08x rebase %s  %s" % (x[4], x[0], x[1], x[2], x[3], x[6]))
    for x in big:
        print("big          old %9s new %9s flags %08x  %s" % (x[0], x[1], x[2], x[6]))


if __name__ == "__main__":
    main()
