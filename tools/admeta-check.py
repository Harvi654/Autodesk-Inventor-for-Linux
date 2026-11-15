#!/usr/bin/env python3
"""Check a prefix against the .admeta inventories of an ODIS image.

Every ADIX package of the image has a <name>.admeta (JSON) next to it,
listing the files it installs. Its "hash" field is not a hash of the file
content (tried 2026-11-15: md5/sha1/sha256/sha512/sha3/blake2s, hex and
base64, whole file and MSIX 64 KiB block hashes, also against the bytes in
the package), so the check compares each listed file in the prefix with the
same file inside the package (.adix next to the .admeta): present, same
size, same SHA-256.

Usage: admeta-check.py IMAGE PREFIX [--details OUT]
       admeta-check.py IMAGE PREFIX --probe   (the hash experiment)
Prints counts and paths only, never hashes or file contents.
"""
import argparse
import base64
import glob
import hashlib
import json
import os
import re
import sys
import urllib.parse
import zipfile

USER_RE = re.compile(r"(?i)(users/)(?!public/)[^/]+")


def prefix_user(drive_c):
    d = os.path.join(drive_c, "users")
    us = [u for u in os.listdir(d) if u.lower() not in ("public", "default")] if os.path.isdir(d) else []
    return us[0] if us else "user"


KNOWN = {   # placeholders in admeta paths -> folder under drive_c (filled in by probe)
    "programfilesx64": "Program Files", "programfilesx86": "Program Files (x86)",
    "programfilescommonx64": "Program Files/Common Files",
    "programfilescommonx86": "Program Files (x86)/Common Files",
    "common appdata": "ProgramData", "common documents": "users/Public/Documents",
    "fonts": "windows/Fonts", "systemx64": "windows/system32", "systemx86": "windows/syswow64",
    "system": "windows/system32", "windows": "windows",
}


def to_prefix(path, drive_c, user):
    p = path.replace("\\", "/")
    m = re.match(r"^\[?\{?([A-Za-z ]+?)\}?\]?/(.*)$", p)
    if m and m.group(1).lower() in KNOWN:
        return os.path.join(drive_c, KNOWN[m.group(1).lower()], m.group(2))
    if m and m.group(1).lower() == "appdata":
        return os.path.join(drive_c, "users", user, "AppData/Roaming", m.group(2))
    if m and m.group(1).lower() == "local appdata":
        return os.path.join(drive_c, "users", user, "AppData/Local", m.group(2))
    m = re.match(r"^(?i:vfs)/([^/]+)/(.*)$", p)
    if m and m.group(1).lower() in KNOWN:
        return os.path.join(drive_c, KNOWN[m.group(1).lower()], m.group(2))
    m = re.match(r"^[A-Za-z]:/(.*)$", p)
    if m:
        return os.path.join(drive_c, m.group(1))
    return None


def find_ci(path):
    """Case-insensitive lookup, as Windows would."""
    if os.path.exists(path):
        return path
    parts = path.split("/")
    cur = "/"
    for part in parts[1:]:
        if not part:
            continue
        try:
            names = {n.lower(): n for n in os.listdir(cur)}
        except OSError:
            return None
        n = names.get(part.lower())
        if n is None:
            return None
        cur = os.path.join(cur, n)
    return cur


def digests(path):
    algs = {n: hashlib.new(n) for n in ("md5", "sha1", "sha256", "sha512", "sha3_256", "blake2s")}
    blocks = hashlib.sha256()      # MSIX block map style: SHA-256 of each 64 KiB block
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            for h in algs.values():
                h.update(chunk)
            blocks.update(hashlib.sha256(chunk).digest())
    out = {"sha256-of-64k-block-hashes/base64": base64.b64encode(blocks.digest()).decode(),
           "sha256-of-64k-block-hashes/hex": blocks.hexdigest()}
    for n, h in algs.items():
        d = h.digest()
        out[n + "/hex"] = d.hex()
        out[n + "/base64"] = base64.b64encode(d).decode()
    return out


def match(h, ds):
    h = (h or "").strip()
    for k, v in ds.items():
        if h.lower() == v.lower() or h == v:
            return k
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("prefix")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--details")
    a = ap.parse_args()
    drive_c = os.path.join(a.prefix, "drive_c")
    user = prefix_user(drive_c)
    metas = sorted(glob.glob(os.path.join(a.image, "**", "*.admeta"), recursive=True))
    if not metas:
        sys.exit("no .admeta in the image")
    if a.probe:
        roots = {}
        for m in metas:
            j = json.load(open(m, encoding="utf-8-sig"))
            for e in j.get("files", [])[:400]:
                r = re.split(r"[\\/]", e["path"])[0]
                roots[r] = roots.get(r, 0) + 1
        print("path roots in the admeta files:", ", ".join("%s(%d)" % kv for kv in sorted(roots.items())))
        tried = 0
        for m in metas:
            for e in json.load(open(m, encoding="utf-8-sig")).get("files", []):
                t = to_prefix(e["path"], drive_c, user)
                f = find_ci(t) if t else None
                if not f or os.path.getsize(f) == 0:
                    continue
                k = match(e.get("hash"), digests(f))
                print("%s: %d bytes, hash length %d -> %s" % (os.path.basename(m), os.path.getsize(f), len(e.get("hash") or ""), k or "no match"))
                tried += 1
                if tried >= 8:
                    return
        print("no listed file found in the prefix to probe with (path format?)")
        return
    total = ok = missing = differ = unknown = nopkg = 0
    lines = []
    for m in metas:
        pk = os.path.basename(m)
        stem = os.path.splitext(pk)[0].lower()
        sib = [q for q in glob.glob(os.path.join(os.path.dirname(m), "*"))
               if q.lower().endswith((".adix", ".appx", ".msix")) and os.path.isfile(q)]
        sib.sort(key=lambda q: os.path.splitext(os.path.basename(q))[0].lower() != stem)
        z = zipfile.ZipFile(sib[0]) if sib else None
        names = {urllib.parse.unquote(n).replace("\\", "/").lower(): n for n in z.namelist()} if z else {}
        files = json.load(open(m, encoding="utf-8-sig")).get("files", [])
        pm = pd = 0
        for e in files:
            total += 1
            rel = e["path"].replace("\\", "/")
            t = to_prefix(e["path"], drive_c, user)
            f = find_ci(t) if t else None
            shown = USER_RE.sub(r"\1USER", rel)
            if t is None:
                unknown += 1
                lines.append("%s\tunknown path root\t%s" % (pk, shown))
                continue
            if not f:
                missing += 1
                pm += 1
                lines.append("%s\tmissing\t%s" % (pk, shown))
                continue
            n = names.get(rel.lower())
            if n is None:
                nopkg += 1
                lines.append("%s\tnot in the package\t%s" % (pk, shown))
                continue
            info = z.getinfo(n)
            same = os.path.getsize(f) == info.file_size
            if same:
                h = hashlib.sha256()
                with z.open(n) as src:
                    for chunk in iter(lambda: src.read(1 << 20), b""):
                        h.update(chunk)
                hp = hashlib.sha256()
                with open(f, "rb") as dst:
                    for chunk in iter(lambda: dst.read(1 << 20), b""):
                        hp.update(chunk)
                same = h.digest() == hp.digest()
            if same:
                ok += 1
            else:
                differ += 1
                pd += 1
                lines.append("%s\tdifferent\t%s" % (pk, shown))
        print("%-32s files %5d  missing %4d  different %4d%s" % (pk, len(files), pm, pd, "" if z else "  (no package next to it)"))
    print("total %d: same %d, missing %d, different %d, not in package %d, unknown path %d"
          % (total, ok, missing, differ, nopkg, unknown))
    if a.details:
        with open(a.details, "w") as f:
            f.write("\n".join(lines) + "\n")

if __name__ == "__main__":
    main()
