#!/usr/bin/env python3
"""DWG TrueView's per-user registry seed as a .reg file for Wine's regedit
(migration 0013, scripts/lib/migrations/0013-trueview-user-seed.sh).

  trueview-seed.py EXPORT USER OUT [KEY]

EXPORT is `hivexregedit --export <TrueView>/UserDataCache/User.dat '\\'`:
the hive Autodesk's installer leaves next to dwgviewr.exe with the keys of
HKEY_CURRENT_USER\\Software that every Windows user gets when the viewer
starts for the first time (UserData.ini: `Registry=HKCU\\Software\\Autodesk\\
DWG TrueView\\R25`). The viewer loads it with RegLoadAppKey, which Wine
does not implement, so under Wine the first start crashes instead.

The hive's strings hold the installer's folder tokens ([{AppData}],
[{ProgramFilesX64}], ...), which Windows fills in at that first start; this
does the same for the Wine prefix of the Wine user USER. hex(1) strings
become plain "strings"; the keys are re-rooted under HKEY_CURRENT_USER.
Prints the number of keys written - 0 when KEY (HKCU\\Software\\...,
the key UserData.ini names) is given and the hive has no CurVer under it,
so the caller knows this is not the viewer's seed.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from odis import FOLDER_TOKENS   # noqa: E402  (the installer's token table)
from regfilter import read_sections, split_value, decode_hex1, esc   # noqa: E402

TOKEN = re.compile(r"\[\{([^}]+)\}\]")


def folder_tokens(user):
    """The installer's machine-wide tokens plus the per-user ones."""
    u = r"C:\users\%s" % user
    t = dict(FOLDER_TOKENS)
    t.update({"appdata": u + r"\AppData\Roaming", "local appdata": u + r"\AppData\Local",
              "documents": u + r"\Documents", "personal": u + r"\Documents",
              "desktop": u + r"\Desktop", "favorites": u + r"\Favorites", "templates": u + r"\Templates"})
    return t


def expand(text, tokens, unknown):
    def one(m):
        name = m.group(1).lower()
        if name in tokens:
            return tokens[name]
        unknown.add(m.group(1))
        return m.group(0)
    return TOKEN.sub(one, text)


def main(export, user, out, want_key=None):
    tokens = folder_tokens(user)
    unknown = set()
    sections = read_sections(export)
    want = want_key.lower().split("\\", 1)[1] if want_key and "\\" in want_key else None   # without HKCU\
    n = 0
    seen_curver = False
    with open(out, "w", encoding="utf-8") as f:
        f.write("Windows Registry Editor Version 5.00\r\n\r\n")
        for key, lines in sections:
            if not key and not lines:
                continue   # the hive's root without values: HKEY_CURRENT_USER itself
            f.write("[HKEY_CURRENT_USER\\%s]\r\n" % key if key else "[HKEY_CURRENT_USER]\r\n")
            n += 1
            for line in lines:
                name, data = split_value(line)
                if want is not None and key.lower() == want and name == "CurVer":
                    seen_curver = True
                text = decode_hex1(data) if data is not None else None
                if text is None:
                    # dword, binary, ...: as exported. REG_EXPAND_SZ/REG_MULTI_SZ
                    # (hex(2), hex(7)) would keep a token: say so (none in 2027's hive)
                    if data is not None and data.startswith(("hex(2):", "hex(7):")) and \
                            TOKEN.search(decode_hex1("hex(1):" + data[7:]) or ""):
                        print("folder token left in %s value %s of %s" % (data[:6], name or "@", key), file=sys.stderr)
                    f.write(line + "\r\n")
                    continue
                lhs = "@" if name is None else '"%s"' % name
                f.write('%s="%s"\r\n' % (lhs, esc(expand(text, tokens, unknown))))
            f.write("\r\n")
    for t in sorted(unknown):
        print("unknown folder token left as it is: [{%s}]" % t, file=sys.stderr)
    print(0 if want is not None and not seen_curver else n)


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5):
        sys.exit(__doc__)
    main(*sys.argv[1:5])
