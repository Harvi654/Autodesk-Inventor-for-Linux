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

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "lib"))
import odis  # noqa: E402


def image_expander(image, prefix="/nonexistent"):
    """expand(text) with the variables install-from-image.py uses for this
    image (its folders, setup.xml properties and settings) - for the
    targets of the packages' InstallPathMappings."""
    import argparse
    import importlib.util
    spec = importlib.util.spec_from_file_location("install_from_image",
                                                  os.path.join(HERE, "..", "scripts", "install-from-image.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # the prefix itself: an update's setup.xml finds INV_INSTALL_PATH with
    # a RegistrySearch in the installed prefix (2027.2: no usable default),
    # and the Catalog Browser's mapping goes to that folder
    inst = mod.Installer(argparse.Namespace(image=image, prefix=prefix, lang="en-US", dry_run=True))
    inst.log = lambda msg: None
    inst.load_setup_properties(image)
    if os.path.isdir(os.path.join(image, "manifest")):
        inst.load_setup_ui_settings(odis.Image(image), [])
    return inst.expand


_PLAN = {}


def plan_mappings(image, lang):
    """{package file name (lower case): InstallPathMappings} from the plan
    install-from-image.py makes of this image - every application with
    optional packages for a product image, the bundle for an update - so
    the manifests are found however the image names and places them (the
    2027.2 update's are not pkg.*.xml next to the packages)."""
    if image not in _PLAN:
        out = {}
        try:
            img = odis.Image(image)
            if odis.image_kind(image) == "update":
                steps = odis.plan_bundle(img, odis.bundle_manifest(image), lang, include_all=True)[0]
            else:
                mdir = os.path.join(image, "manifest")
                apps = [f[4:-4] for f in os.listdir(mdir) if f.startswith("app.") and f.endswith(".xml")]
                steps = odis.plan(img, apps, lang, include_all=True)[0]
            for st in steps:
                if st.get("file"):
                    # the step too: its own <Properties> fill in the mapping
                    # targets, as in the installer (expand(..., step=s))
                    out[os.path.basename(st["file"].replace("\\", "/")).lower()] = (st.get("pathMappings") or {}, st)
        except (OSError, SystemExit, Exception) as e:  # noqa: BLE001 - fall back to the manifest search
            print("note: the installer's plan of this image failed (%s: %s) - looking for manifests instead"
                  % (type(e).__name__, e))
        _PLAN[image] = out
    return _PLAN[image]


_MANIFESTS = {}


def _manifests(image):
    """All pkg.*.xml of the image (searched once)."""
    if image not in _MANIFESTS:
        _MANIFESTS[image] = glob.glob(os.path.join(image, "**", "pkg.*.xml"), recursive=True)
    return _MANIFESTS[image]


def package_mappings(admeta, package, image=None):
    """InstallPathMappings of the manifest whose InstallFile is this
    package: pkg.*.xml next to the .admeta, else anywhere in the image (an
    update keeps its manifests apart from the packages - 2027.2's
    AceInvAddIn)."""
    import xml.etree.ElementTree as ET
    near = glob.glob(os.path.join(os.path.dirname(admeta), "pkg.*.xml"))
    far = list(_manifests(image)) if image else []
    for x in near + [f for f in far if f not in near]:
        try:
            root = ET.parse(x).getroot()
        except ET.ParseError:
            continue
        inst = root.find("m:Configuration/m:InstallFile", odis.NS)
        if inst is None or os.path.basename((inst.get("file") or "").replace("\\", "/")).lower() \
                != os.path.basename(package).lower():
            continue
        return {m.get("source"): m.get("target") for m in root.iterfind(
            "m:Configuration/m:AdditionalPackageInfo/m:Customizations/m:InstallPathMappings/m:InstallPathMapping",
            odis.NS)}
    return {}


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
    if m and m.group(1).lower() == "appdata":
        return os.path.join(drive_c, "users", user, "AppData/Roaming", m.group(2))
    if m and m.group(1).lower() == "local appdata":
        return os.path.join(drive_c, "users", user, "AppData/Local", m.group(2))
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


def disabled_copy(path):
    """The prefix setup (scripts/lib/configure.sh) turns some files off on
    purpose: add-ins move to <Inventor>/Addins.disabled/, other files get a
    .disabled suffix. Returns the moved file, or None."""
    f = find_ci(path + ".disabled")
    if f:
        return f
    m = re.match(r"^(.*/Inventor 20\d\d)/Bin/Addins/([^/]+)$", path, re.I)
    if m:
        return find_ci(os.path.join(m.group(1), "Addins.disabled", m.group(2)))
    m = re.match(r"^(.*/Inventor 20\d\d)/Bin/(?:[a-z]{2}-[A-Z]{2}/)?([^/]+\.dll)$", path)
    if m:   # crash sources moved to Addins.disabled/libs/ (cfg_crash_sources)
        return find_ci(os.path.join(m.group(1), "Addins.disabled", "libs", m.group(2)))
    return None


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
    ap.add_argument("--lang", default="en-US",
                    help="the language installed: .admeta files in a folder of another language "
                         "(x64/de-DE/...) are left out, as the installer leaves those packages out")
    a = ap.parse_args()
    drive_c = os.path.join(a.prefix, "drive_c")
    user = prefix_user(drive_c)
    metas = sorted(glob.glob(os.path.join(a.image, "**", "*.admeta"), recursive=True))
    other = [m for m in metas if any(odis.LOCALE.match(part) and part != a.lang
                                     for part in os.path.relpath(m, a.image).split(os.sep))]
    if other:
        print("left out: %d .admeta of other languages than %s" % (len(other), a.lang))
    metas = [m for m in metas if m not in other]
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
    total = ok = missing = differ = unknown = nopkg = off = 0
    lines = []
    expand = image_expander(a.image, a.prefix)
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
        # where ODIS puts them: the package's InstallPathMappings
        found = plan_mappings(a.image, a.lang).get(os.path.basename(sib[0]).lower()) if sib else None
        if found is not None:
            maps, step = found
        else:
            maps, step = (package_mappings(m, sib[0], a.image) if sib else {}), None
        mapper = odis.PathMapper(maps or {}, lambda v, step=step: expand(v, None, step))
        for e in files:
            total += 1
            rel = e["path"].replace("\\", "/")
            t = to_prefix(e["path"], drive_c, user)
            if t is not None and mapper.rules:
                win = "C:\\" + os.path.relpath(t, drive_c).replace("/", "\\")
                t = os.path.join(drive_c, *mapper.map(win)[3:].split("\\"))
            f = find_ci(t) if t else None
            shown = USER_RE.sub(r"\1USER", rel)
            if t is None:
                unknown += 1
                lines.append("%s\tunknown path root\t%s" % (pk, shown))
                continue
            if not f:
                if disabled_copy(t):
                    off += 1
                    lines.append("%s\tturned off by the prefix setup\t%s" % (pk, shown))
                    continue
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
        print("%-32s files %5d  missing %4d  different %4d%s%s" % (
            pk, len(files), pm, pd, "" if z else "  (no package next to it)",
            "  (path mappings: %d%s)" % (len(mapper.rules), ", not understood: %s" % "; ".join(
                "%s -> %s" % u for u in mapper.unread) if mapper.unread else "")
            if (mapper.rules or mapper.unread) else ""))
    print("total %d: same %d, turned off on purpose %d, missing %d, different %d, not in package %d, unknown path %d"
          % (total, ok, off, missing, differ, nopkg, unknown))
    if a.details:
        with open(a.details, "w") as f:
            f.write("\n".join(lines) + "\n")

if __name__ == "__main__":
    main()
