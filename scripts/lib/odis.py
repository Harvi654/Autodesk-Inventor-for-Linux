#!/usr/bin/env python3
"""Read an Autodesk ODIS install image and work out the install plan.

An ODIS image is what Autodesk's "Browser download" unpacks to (the folder
with Setup.exe, setup.xml, manifest/, x64/, 3rdParty/ ...). Its manifests
describe every package: the file to run (MSI/EXE/ZIP/7Z/ADIX), the
parameters ODIS passes, where it goes, and the packages it depends on.
plan() walks them the way ODIS does - dependencies first - so the packages
can be installed under Wine without Autodesk's installer UI
(scripts/install-from-image.py does that).

Run directly to print the plan:
  odis.py IMAGE_DIR [--app inventor] [--all] [--lang en-US] [--json]

  IMAGE_DIR  the image folder (contains manifest/app.*.xml). A copy of
             ProgramData/Autodesk/ODIS/metadata also works for planning:
             manifests are then looked up across its {GUID} folders.
  --app      application manifest(s) to install (default: inventor)
  --with N   also install optional package N (see "skipped"; repeatable)
  --all      include packages this project skips (telemetry, Genuine
             Service, Autodesk Access, the ODIS installer itself)
  --json     machine-readable plan
"""
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

NS = {"m": "https://emsfs.autodesk.com/schema/manifest/1/0"}

# Packages left out by default, by manifest name (case-insensitive): they
# phone home, watch for "non-genuine" installs, or are Autodesk's own
# installer/updater - none of them are needed to run Inventor.
SKIP = {
    "ags": "Autodesk Genuine Service (licence-compliance watcher)",
    "cer": "Customer Error Reporting (crash upload)",
    "access": "Autodesk Access (updater app)",
    "acc_connector": "Autodesk Access connector",
    "accessconnector": "Autodesk Access connector",
    "odis": "Autodesk installer (ODIS) itself",
}


LOCALE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")


def bundle_manifest(root):
    """Name of the Bundle manifest at the top of an image: bundleManifest.xml
    (ODIS metadata copy) or setup.xml (a downloaded update), or None."""
    for name in ("bundleManifest.xml", "setup.xml"):
        p = os.path.join(root, name)
        if os.path.isfile(p):
            try:
                if ET.parse(p).getroot().tag == "{%s}Bundle" % NS["m"]:
                    return name
            except ET.ParseError:
                pass
    return None


def image_kind(root):
    """'product' (full install image), 'update' (update bundle) or None."""
    mdir = os.path.join(root, "manifest")
    if os.path.isdir(mdir) and any(f.startswith("app.") for f in os.listdir(mdir)):
        return "product"
    if bundle_manifest(root):
        return "update"
    return None


def find_image(path, product_depth=4, update_depth=3):
    """The install image or update in PATH or a few folders below it (the same
    search scripts/install.sh does), or None."""
    path = os.path.abspath(path)
    if image_kind(path):
        return path
    if not os.path.isdir(path):
        return None
    base = path.rstrip(os.sep).count(os.sep)
    found_product, found_update = [], []
    for d, dirs, files in os.walk(path):
        depth = d.rstrip(os.sep).count(os.sep) - base
        if depth >= product_depth:
            dirs[:] = []
        dirs.sort()
        if os.path.basename(d) == "manifest" and "app.inventor.xml" in files:
            found_product.append(os.path.dirname(d))
        if depth < update_depth and ("setup.xml" in files or "bundleManifest.xml" in files):
            found_update.append(d)
    for d in found_product + found_update:
        if image_kind(d):
            return d
    return None


# Release year from download names: Inventor_Professional_2027_..., Inventor_2027.1_Update.exe
YEAR_NAME = re.compile(r"^Inventor(?:_Professional)?_(20\d\d)", re.I)
# ... and from manifest display names: "Inventor Core 2027", "Inventor 2027.1 Update"
YEAR_TEXT = re.compile(r"^(?:Autodesk\s+)?Inventor\b.*?\b(20\d\d)\b", re.I)


def _identity(path):
    """(DisplayName, BuildNumber) of a manifest file; ("", "") if unreadable."""
    try:
        r = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return "", ""
    return _text(r, "m:Identity/m:DisplayName"), _text(r, "m:Identity/m:BuildNumber")


def _year_from_build(build):
    """2027 for Inventor's build number 31.x (release = major + 1996, as INV_REGMAJOR)."""
    m = re.match(r"^(\d+)\.", build or "")
    if m and 25 <= int(m.group(1)) <= 60:
        return str(int(m.group(1)) + 1996)
    return None


def image_release(root):
    """Inventor release ('2027') of an install image or update, from its
    manifests; None when it cannot be told or the manifests disagree."""
    kind = image_kind(root)
    years = set()
    if kind == "update":
        name, _ = _identity(os.path.join(root, bundle_manifest(root)))
        m = YEAR_TEXT.match(name)
        return m.group(1) if m else None
    if kind != "product":
        return None
    img = Image(root)
    mdir = os.path.join(img.root, "manifest")
    apps = ["app.inventor.xml"] if os.path.isfile(os.path.join(mdir, "app.inventor.xml")) else \
        sorted(f for f in os.listdir(mdir) if f.startswith("app.") and f.endswith(".xml"))
    pending, seen = [], set()
    for app in apps:
        name, _ = _identity(os.path.join(mdir, app))
        m = YEAR_TEXT.match(name)
        if m:
            years.add(m.group(1))
        try:
            pending += [p.get("path") for p in ET.parse(os.path.join(mdir, app)).getroot()
                        .iter("{%s}Package" % NS["m"]) if p.get("path")]
        except (ET.ParseError, OSError):
            pass
    # Inventor's own packages (Inventor Core 2027, Inventor Pro 2027, ...) and
    # what they depend on; other products (RealDWG, VC++) are left out by name.
    while pending:
        rel = pending.pop()
        if rel.lower() in seen:
            continue
        seen.add(rel.lower())
        p = img.find(rel)
        if not p:
            continue
        name, build = _identity(p)
        if re.match(r"^(?:Autodesk\s+)?Inventor\b", name, re.I):
            m = YEAR_TEXT.match(name)
            y = m.group(1) if m else _year_from_build(build)
            if y:
                years.add(y)
        try:
            pending += [d.get("path") for d in ET.parse(p).getroot()
                        .findall("m:Dependencies/m:Package", NS) if d.get("path")]
        except (ET.ParseError, OSError):
            pass
    return years.pop() if len(years) == 1 else None


def release_of(path):
    """Inventor release of a download, an unpacked image or update, or a folder
    holding one of them; None when unknown or ambiguous."""
    m = YEAR_NAME.match(os.path.basename(os.path.abspath(path)))
    if m:
        return m.group(1)
    if not os.path.isdir(path):
        return None
    img = find_image(path)
    if img:
        return image_release(img)
    years = set()
    for f in os.listdir(path):
        m = YEAR_NAME.match(f)
        if m and f.lower().endswith((".exe", ".7z")):
            years.add(m.group(1))
    return years.pop() if len(years) == 1 else None


def bundle_id(root):
    """UPI2 + display name of an image's Bundle manifest (or None, None)."""
    name = bundle_manifest(root)
    if not name:
        return None, None
    r = ET.parse(os.path.join(root, name)).getroot()
    return _text(r, "m:Identity/m:UPI2"), _text(r, "m:Identity/m:DisplayName")


class Image:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self._index = None

    def find(self, rel):
        """Path of a manifest-relative file, or None."""
        if not rel:
            return None
        p = os.path.join(self.root, *rel.replace("\\", "/").split("/"))
        if os.path.exists(p):
            return p
        # metadata copy: same relative path below one of the {GUID} folders
        if self._index is None:
            self._index = {}
            for d, _, files in os.walk(self.root):
                for f in files:
                    self._index.setdefault(f.lower(), []).append(os.path.join(d, f))
        want = rel.replace("\\", "/").lower()
        for cand in self._index.get(os.path.basename(want), []):
            if cand.replace("\\", "/").lower().endswith("/" + want):
                return cand
        return None


def _text(el, path):
    x = el.find(path, NS)
    return x.text.strip() if x is not None and x.text else ""


def _step(root, name, install_as, rel, img, lang):
    cfg = root.find("m:Configuration", NS)
    inst = cfg.find("m:InstallFile", NS) if cfg is not None else None
    if inst is None:
        return None
    info = cfg.find("m:AdditionalPackageInfo", NS)
    attrs = cfg.find("m:Attributes", NS)
    props, mappings = {}, {}
    if info is not None:
        for p in info.findall("m:MsiTransform/m:MsiProperties/m:MsiProperty", NS):
            props[p.get("name")] = p.get("value", "")
        for m in info.findall("m:Customizations/m:InstallPathMappings/m:InstallPathMapping", NS):
            mappings[m.get("source")] = m.get("target")
    # <Property property="X" defaultValue="..."/> - ODIS variables the
    # manifest uses in paths and actions (searches for installed versions
    # are left out: we start from an empty prefix)
    properties = {pr.get("property"): pr.get("defaultValue", "")
                  for pr in cfg.findall("m:Properties/m:Property", NS) if pr.get("property")}
    actions = [{"type": a.get("type"), "path": a.get("path"), "params": a.get("params", "")}
               for a in cfg.findall("m:CustomCommands/m:Action", NS)]
    return {
        "name": name,
        "display": _text(root, "m:Identity/m:DisplayName"),
        "version": _text(root, "m:Identity/m:BuildNumber"),
        "installAs": install_as,
        "type": (inst.get("type") or "").upper(),
        "file": inst.get("file"),
        "params": (inst.get("installParams") or "").replace("%INV_LOCALE%", lang),
        "installLocation": info.get("installLocation") if info is not None else None,
        "msiProperties": props,
        "properties": properties,
        "pathMappings": mappings,
        "actions": actions,
        "ignoreFailure": attrs is not None and attrs.get("ignoreFailure") == "true",
        "manifest": rel,
        "present": bool(img.find(inst.get("file"))),
    }


def plan(img, apps=("inventor",), lang="en-US", include_all=False, extra=()):
    """Return (steps, skipped, missing) for the given application manifests.
    extra: names of optional packages to install too (e.g. Content Center
    libraries)."""
    return _plan(img, ["manifest/app.%s.xml" % a for a in apps], lang, include_all, extra)


def plan_bundle(img, manifest, lang="en-US", include_all=False):
    """Plan for a nested bundle (e.g. Shared Components) given its manifest
    file; falls back to the bundle's manifest/app.*.xml files."""
    roots = [manifest]
    p = img.find(manifest)
    if p is None or not any(e.get("path") for e in ET.parse(p).getroot().iter("{%s}Package" % NS["m"])):
        mdir = os.path.join(img.root, "manifest")
        roots = ["manifest/" + f for f in sorted(os.listdir(mdir))
                 if f.startswith("app.") and f.endswith(".xml")] if os.path.isdir(mdir) else []
    return _plan(img, roots, lang, include_all)


def _plan(img, roots, lang, include_all, extra=()):
    steps, seen, skipped, missing = [], set(), [], []
    extra = {e.lower() for e in extra}

    def visit(name, rel, install_as, chain):
        key = rel.lower()
        if key in seen:
            return
        seen.add(key)
        if not include_all and name.lower() in SKIP:
            skipped.append((name, SKIP[name.lower()]))
            return
        # language-specific packages (x64/de-DE/...) only for the chosen language
        other = [p for p in rel.replace("\\", "/").split("/") if LOCALE.match(p) and p != lang]
        if other:
            skipped.append((name, "language %s" % other[0]))
            return
        mpath = img.find(rel)
        if not mpath:
            missing.append((name, rel, " <- ".join(chain)))
            return
        root = ET.parse(mpath).getroot()
        for dep in root.findall("m:Dependencies/m:Package", NS):
            visit(dep.get("name", "?"), dep.get("path"), dep.get("installAs", ""), chain + [name])
        s = _step(root, name, install_as, rel, img, lang)
        if s:
            steps.append(s)

    for rel in roots:
        apath = img.find(rel)
        if not apath:
            raise SystemExit("no %s in %s" % (rel, img.root))
        for pkg in ET.parse(apath).getroot().iter("{%s}Package" % NS["m"]):
            if not pkg.get("path"):
                continue
            if (pkg.get("installAs") == "optional" and not include_all
                    and pkg.get("name", "").lower() not in extra):
                skipped.append((pkg.get("name"), "optional in %s" % rel))
                seen.add(pkg.get("path").lower())
                continue
            visit(pkg.get("name", "?"), pkg.get("path"), pkg.get("installAs", ""), [os.path.basename(rel)])
    return steps, skipped, missing


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("image")
    ap.add_argument("--app", action="append")
    ap.add_argument("--lang", default="en-US")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--with", dest="extra", action="append", default=[],
                    help="also install this optional package (name as listed under skipped)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--release", action="store_true",
                    help="only print the Inventor release of IMAGE (a download, image or folder)")
    a = ap.parse_args()
    if a.release:
        print(release_of(a.image) or "")
        return
    steps, skipped, missing = plan(Image(a.image), a.app or ["inventor"], a.lang, a.all, a.extra)
    if a.json:
        json.dump({"steps": steps, "skipped": skipped, "missing": missing}, sys.stdout, indent=1)
        return
    for i, s in enumerate(steps, 1):
        flag = "" if s["present"] else "   [file not in image]"
        print("%2d. %-5s %-55s %s%s" % (i, s["type"], s["display"][:55], s["version"], flag))
        print("        %s %s" % (s["file"], s["params"]))
    if skipped:
        print("\nskipped:")
        for n, why in skipped:
            print("   %-16s %s" % (n, why))
    if missing:
        print("\nmanifest not found:")
        for n, rel, chain in missing:
            print("   %-16s %s  (needed by %s)" % (n, rel, chain))


if __name__ == "__main__":
    main()
