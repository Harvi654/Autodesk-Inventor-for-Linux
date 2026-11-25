#!/usr/bin/env python3
"""Registry.reg next to Registry.dat in an ADIX package: does the .reg hold
keys or values the .dat does not?

install-from-image.py imports an ADIX package's Registry.dat (a hive, as in
MSIX) and lists other files at the package root as "not installed" - the
Material Library packages have a Registry.reg there too. This compares the
KEY NAMES and VALUE NAMES of both, never the data.

Usage: adix-registry-names.py PACKAGE.adix|IMAGE [...] [--details]
  PACKAGE  an ADIX file; IMAGE: every *.adix below it that has a
           Registry.reg at its root
  --details  list every name only on one side (default: counts and the
           first ones)
Prints names only; nothing else from the packages.
"""
import argparse
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "scripts", "lib"))
import regf  # noqa: E402

HIVES = {"hkey_local_machine": "HKLM", "hklm": "HKLM", "hkey_current_user": "HKCU", "hkcu": "HKCU",
         "hkey_classes_root": "HKLM\\software\\classes", "hkcr": "HKLM\\software\\classes",
         "hkey_users": "HKU", "hku": "HKU"}


def norm_key(k):
    k = k.strip().strip("\\")
    # MSIX layout, as in the hive itself: REGISTRY\MACHINE\..., and
    # REGISTRY\USER\<user token>\...
    parts = k.split("\\")
    if len(parts) >= 2 and parts[0].lower() == "registry":
        if parts[1].lower() == "machine":
            k = "\\".join(["HKLM"] + parts[2:])
        elif parts[1].lower() == "user" and len(parts) >= 3:
            k = "\\".join(["HKCU"] + parts[3:])
    first, _, rest = k.partition("\\")
    first = HIVES.get(first.lower(), first)
    return ("%s\\%s" % (first, rest) if rest else first).lower()


def names_from_dat(data):
    """{key: {value names}} of a package hive (regf), keys as install-from-
    image.py imports them (REGISTRY\\MACHINE -> HKLM)."""
    out = {}
    for path, vals in regf.Hive(data).walk():
        key = regf._map_root(path)
        if key is None or "\\" not in key:
            continue
        out.setdefault(norm_key(key), set()).update(n.lower() for n, _, _ in vals)
    return out


def decode(raw):
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    if b"\x00" in raw[:200]:
        return raw.decode("utf-16-le", "replace")
    return raw.decode("utf-8-sig", "replace")


def names_from_reg(text):
    """{key: {value names}} of a .reg file; deleted keys ([-...]) and
    deleted values ("x"=-) are reported separately."""
    out, deleted, cur = {}, [], None
    cont = False
    for line in text.splitlines():
        if cont:                       # continuation of a hex value
            cont = line.rstrip().endswith("\\")
            continue
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            k = s[1:-1]
            if k.startswith("-"):
                deleted.append(norm_key(k[1:]))
                cur = None
            else:
                cur = out.setdefault(norm_key(k), set())
            continue
        if cur is None or not s or s.startswith(";"):
            continue
        m = re.match(r'^(@|"((?:[^"\\]|\\.)*)")\s*=\s*(.*)$', s)
        if not m:
            continue
        name = "" if m.group(1) == "@" else re.sub(r"\\(.)", r"\1", m.group(2))
        if m.group(3).strip() == "-":
            deleted.append("%s -> %s" % (norm_key(k), name))
            continue
        cur.add(name.lower())
        cont = m.group(3).rstrip().endswith("\\")
    return out, deleted


def compare(dat, reg):
    """(keys only in .reg, values only in .reg, keys only in .dat,
    values only in .dat) - values as 'key -> name' ('' = default)."""
    def ancestors(keys):
        s = set(keys)
        for k in keys:
            parts = k.split("\\")
            s.update("\\".join(parts[:i]) for i in range(1, len(parts)))
        return s
    dk, rk = ancestors(dat), ancestors(reg)
    only_reg_k = sorted(k for k in reg if k not in dk)
    only_dat_k = sorted(k for k in dat if k not in rk)
    only_reg_v = sorted("%s -> %s" % (k, n or "(default)") for k, ns in reg.items() for n in ns
                        if n not in dat.get(k, set()))
    only_dat_v = sorted("%s -> %s" % (k, n or "(default)") for k, ns in dat.items() for n in ns
                        if n not in reg.get(k, set()))
    return only_reg_k, only_reg_v, only_dat_k, only_dat_v


def packages(paths):
    for p in paths:
        if os.path.isdir(p):
            for d, _, files in os.walk(p):
                for f in sorted(files):
                    if f.lower().endswith(".adix"):
                        yield os.path.join(d, f)
        else:
            yield p


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--details", action="store_true")
    a = ap.parse_args()
    found = 0
    for pkg in packages(a.paths):
        try:
            z = zipfile.ZipFile(pkg)
        except (zipfile.BadZipFile, OSError):
            continue
        root = {n.lower(): n for n in z.namelist() if "/" not in n}
        if "registry.reg" not in root:
            continue
        found += 1
        dat = names_from_dat(z.read(root["registry.dat"])) if "registry.dat" in root else {}
        reg, deleted = names_from_reg(decode(z.read(root["registry.reg"])))
        rk, rv, dk, dv = compare(dat, reg)
        print("## %s" % os.path.basename(pkg))
        print("Registry.dat: %d keys, %d value names; Registry.reg: %d keys, %d value names%s"
              % (len(dat), sum(map(len, dat.values())), len(reg), sum(map(len, reg.values())),
                 "" if "registry.dat" in root else " (no Registry.dat)"))
        verdict = "nothing the .dat does not have" if not (rk or rv or deleted) else "MORE than the .dat"
        print("Registry.reg holds %s" % verdict)
        limit = None if a.details else 10
        for title, items in (("keys only in Registry.reg", rk), ("value names only in Registry.reg", rv),
                             ("deletions in Registry.reg", deleted),
                             ("keys only in Registry.dat", dk), ("value names only in Registry.dat", dv)):
            if items:
                print("- %s: %d" % (title, len(items)))
                for it in items[:limit]:
                    print("    - %s" % it)
                if limit and len(items) > limit:
                    print("    - ... %d more (--details)" % (len(items) - limit))
        print()
    if not found:
        sys.exit("no ADIX package with a Registry.reg at its root")


if __name__ == "__main__":
    main()
