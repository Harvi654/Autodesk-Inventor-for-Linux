#!/usr/bin/env python3
"""Minimal reader for Windows registry hive files (regf), e.g. the
Registry.dat inside an MSIX/ADIX package, and a converter to .reg.

Only reading is supported, and only what hive files from packages use:
nk/vk records, lf/lh/li/ri subkey lists and "db" big-data values.

MSIX hives have the layout  REGISTRY\\MACHINE\\...  and
REGISTRY\\USER\\[{AppVCurrentUserSID}]\\...; to_reg() maps those to
HKEY_LOCAL_MACHINE / HKEY_CURRENT_USER and replaces the package's folder
tokens ([{ProgramFilesX64}] ...) in string values with real paths.

Usage: regf.py HIVE [OUT.reg]      (prints to stdout without OUT)
"""
import struct
import sys

REG_SZ, REG_EXPAND_SZ, REG_BINARY, REG_DWORD, REG_MULTI_SZ = 1, 2, 3, 4, 7

# MSIX folder tokens -> Windows paths inside the Wine prefix
TOKENS = {
    "[{ProgramFilesX64}]": r"C:\Program Files",
    "[{ProgramFilesX86}]": r"C:\Program Files (x86)",
    "[{ProgramFilesCommonX64}]": r"C:\Program Files\Common Files",
    "[{ProgramFilesCommonX86}]": r"C:\Program Files (x86)\Common Files",
    "[{Common AppData}]": r"C:\ProgramData",
    "[{SystemX64}]": r"C:\windows\system32",
    "[{SystemX86}]": r"C:\windows\syswow64",
    "[{System}]": r"C:\windows\system32",
    "[{Windows}]": r"C:\windows",
    "[{Fonts}]": r"C:\windows\Fonts",
}


class Hive:
    def __init__(self, data):
        if data[:4] != b"regf":
            raise ValueError("not a registry hive (no regf signature)")
        self.d = data
        self.root = struct.unpack_from("<I", data, 0x24)[0]

    def cell(self, off):
        """Data of the cell at hbin-relative offset off (without size field)."""
        pos = 0x1000 + off
        size = struct.unpack_from("<i", self.d, pos)[0]
        return self.d[pos + 4:pos + abs(size)]

    def subkeys(self, list_off):
        c = self.cell(list_off)
        sig, n = c[:2], struct.unpack_from("<H", c, 2)[0]
        if sig in (b"lf", b"lh"):
            return [struct.unpack_from("<I", c, 4 + 8 * i)[0] for i in range(n)]
        if sig == b"li":
            return [struct.unpack_from("<I", c, 4 + 4 * i)[0] for i in range(n)]
        if sig == b"ri":
            out = []
            for i in range(n):
                out += self.subkeys(struct.unpack_from("<I", c, 4 + 4 * i)[0])
            return out
        raise ValueError("unknown subkey list %r" % sig)

    def key(self, off):
        c = self.cell(off)
        if c[:2] != b"nk":
            raise ValueError("expected nk record")
        flags = struct.unpack_from("<H", c, 2)[0]
        nsub, = struct.unpack_from("<I", c, 0x14)
        sub_off, = struct.unpack_from("<I", c, 0x1C)
        nval, = struct.unpack_from("<I", c, 0x24)
        val_off, = struct.unpack_from("<I", c, 0x28)
        nlen, = struct.unpack_from("<H", c, 0x48)
        raw = c[0x4C:0x4C + nlen]
        name = raw.decode("latin-1") if flags & 0x20 else raw.decode("utf-16-le")
        return name, (self.subkeys(sub_off) if nsub else []), self.values(val_off, nval)

    def values(self, list_off, n):
        if not n:
            return []
        lst = self.cell(list_off)
        out = []
        for i in range(n):
            v = self.cell(struct.unpack_from("<I", lst, 4 * i)[0])
            if v[:2] != b"vk":
                continue
            nlen, size, doff, typ, flags = struct.unpack_from("<HIIIH", v, 2)
            raw = v[0x14:0x14 + nlen]
            name = raw.decode("latin-1") if flags & 1 else raw.decode("utf-16-le")
            if size & 0x80000000:                      # data inside the record
                data = struct.pack("<I", doff)[:size & 0x7FFFFFFF]
            elif size > 16344 and self.cell(doff)[:2] == b"db":
                db = self.cell(doff)
                cnt, seg_list = struct.unpack_from("<HI", db, 2)
                segs = self.cell(seg_list)
                data = b"".join(self.cell(struct.unpack_from("<I", segs, 4 * j)[0])[:16344]
                                for j in range(cnt))[:size]
            else:
                data = self.cell(doff)[:size]
            out.append((name, typ, data))
        return out

    def walk(self, off=None, path=""):
        """Yield (key path, [(name, type, data)]) for every key."""
        name, subs, vals = self.key(self.root if off is None else off)
        here = name if off is None else (path + "\\" + name if path else name)
        yield here, vals
        for s in subs:
            yield from self.walk(s, here)


def _map_root(path):
    """MSIX hive path -> .reg root path, or None to skip."""
    parts = path.split("\\")
    # parts[0] is the hive's own root key name; then REGISTRY\MACHINE|USER
    try:
        i = [p.upper() for p in parts].index("REGISTRY")
    except ValueError:
        return None
    rest = parts[i + 1:]
    if not rest:
        return None
    if rest[0].upper() == "MACHINE":
        return "\\".join(["HKEY_LOCAL_MACHINE"] + rest[1:])
    if rest[0].upper() == "USER" and len(rest) >= 2:
        return "\\".join(["HKEY_CURRENT_USER"] + rest[2:])
    return None


def _subst(s, tokens):
    for k, v in tokens.items():
        s = s.replace(k, v)
    return s


def _hex(typ, data):
    h = ",".join("%02x" % b for b in data)
    return ("hex:%s" % h) if typ == REG_BINARY else ("hex(%x):%s" % (typ, h))


def to_reg(hive_bytes, tokens=None):
    """Convert a package hive to the text of a .reg file."""
    tokens = dict(TOKENS, **(tokens or {}))
    h = Hive(hive_bytes)
    lines = ["Windows Registry Editor Version 5.00", ""]
    for path, vals in h.walk():
        key = _map_root(path)
        if key is None or key.count("\\") == 0:
            continue
        lines.append("[%s]" % key)
        for name, typ, data in vals:
            n = '@' if name == "" else '"%s"' % name.replace("\\", "\\\\").replace('"', '\\"')
            if typ in (REG_SZ, REG_EXPAND_SZ, REG_MULTI_SZ):
                text = _subst(data.decode("utf-16-le", "replace"), tokens)
                if typ == REG_SZ:
                    text = text.rstrip("\0")
                    lines.append('%s="%s"' % (n, text.replace("\\", "\\\\").replace('"', '\\"')))
                    continue
                data = text.encode("utf-16-le")
            if typ == REG_DWORD and len(data) == 4:
                lines.append("%s=dword:%08x" % (n, struct.unpack("<I", data)[0]))
            else:
                lines.append("%s=%s" % (n, _hex(typ, data)))
        lines.append("")
    return "\r\n".join(lines) + "\r\n"


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    with open(sys.argv[1], "rb") as f:
        text = to_reg(f.read())
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-16", newline="") as f:
            f.write(text)
    else:
        sys.stdout.write(text.replace("\r\n", "\n"))


if __name__ == "__main__":
    main()
