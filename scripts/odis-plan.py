#!/usr/bin/env python3
"""Read an Autodesk ODIS install image and print the install plan.

An ODIS image is what Autodesk's "Browser download" unpacks to (the folder
with Setup.exe, setup.xml, manifest/, x64/, 3rdParty/ ...). Its manifests
describe every package: the file to run (MSI/EXE/ZIP/7Z/ADIX), the
parameters ODIS passes, and the packages it depends on. This script walks
them the way ODIS does - dependencies first - so we can install the same
packages under Wine without running Autodesk's installer UI.

Usage:
  odis-plan.py IMAGE_DIR [--app inventor] [--all] [--lang en-US] [--json]

  IMAGE_DIR  the image folder (contains manifest/app.*.xml). A copy of
             ProgramData/Autodesk/ODIS/metadata also works for planning:
             manifests are then looked up across its {GUID} folders.
  --app      application manifest(s) to install (default: inventor)
  --all      include packages this project skips (telemetry, Genuine
             Service, Autodesk Access, the ODIS installer itself)
  --json     machine-readable plan for the installer
"""
import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET

NS = {"m": "https://emsfs.autodesk.com/schema/manifest/1/0"}

# Packages we leave out by default, by manifest name (case-insensitive):
# they phone home, watch for "non-genuine" installs, or are Autodesk's own
# installer/updater - none of them are needed to run Inventor.
SKIP = {
    "ags": "Autodesk Genuine Service (licence-compliance watcher)",
    "cer": "Customer Error Reporting (crash upload)",
    "access": "Autodesk Access (updater app)",
    "acc_connector": "Autodesk Access connector",
    "accessconnector": "Autodesk Access connector",
    "odis": "Autodesk installer (ODIS) itself",
}


class Image:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self._index = None

    def find(self, rel):
        """Path of a manifest-relative file, or None."""
        p = os.path.join(self.root, *rel.replace("\\", "/").split("/"))
        if os.path.exists(p):
            return p
        # metadata copy: same relative path below one of the {GUID} folders
        if self._index is None:
            self._index = {}
            for d, _, files in os.walk(self.root):
                for f in files:
                    full = os.path.join(d, f)
                    self._index.setdefault(f.lower(), []).append(full)
        want = rel.replace("\\", "/").lower()
        for cand in self._index.get(os.path.basename(want), []):
            if cand.replace("\\", "/").lower().endswith("/" + want):
                return cand
        return None


def text(el, path):
    x = el.find(path, NS)
    return x.text.strip() if x is not None and x.text else ""


def load(path):
    return ET.parse(path).getroot()


def plan(img, apps, lang, include_all):
    steps, seen, skipped, missing = [], set(), [], []

    def visit(ref_name, rel, install_as, chain):
        key = rel.lower()
        if key in seen:
            return
        seen.add(key)
        if not include_all and ref_name.lower() in SKIP:
            skipped.append((ref_name, SKIP[ref_name.lower()]))
            return
        mpath = img.find(rel)
        if not mpath:
            missing.append((ref_name, rel, " <- ".join(chain)))
            return
        root = load(mpath)
        for dep in root.findall("m:Dependencies/m:Package", NS):
            visit(dep.get("name", "?"), dep.get("path"), dep.get("installAs", ""),
                  chain + [ref_name])
        inst = root.find("m:Configuration/m:InstallFile", NS)
        if inst is None:
            return
        base = os.path.dirname(rel)
        steps.append({
            "name": ref_name,
            "display": text(root, "m:Identity/m:DisplayName"),
            "version": text(root, "m:Identity/m:BuildNumber"),
            "installAs": install_as,
            "type": inst.get("type"),
            "file": inst.get("file"),
            "params": (inst.get("installParams") or "")
                      .replace("%INV_LOCALE%", lang),
            "manifest": rel,
            "present": bool(img.find(inst.get("file") or "")),
            "patches": [p.get("file") for p in
                        root.findall("m:Configuration/m:InstallFile/m:Patch", NS)],
            "base": base,
        })

    for app in apps:
        rel = "manifest/app.%s.xml" % app
        apath = img.find(rel)
        if not apath:
            sys.exit("no %s in %s" % (rel, img.root))
        aroot = load(apath)
        for pkg in aroot.findall("m:Packages/m:Package", NS):
            if pkg.get("installAs") == "optional" and not include_all:
                skipped.append((pkg.get("name"), "optional in %s" % rel))
                seen.add(pkg.get("path").lower())
                continue
            visit(pkg.get("name", "?"), pkg.get("path"), pkg.get("installAs", ""),
                  ["app." + app])
    return steps, skipped, missing


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("image")
    ap.add_argument("--app", action="append")
    ap.add_argument("--lang", default="en-US")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    img = Image(a.image)
    steps, skipped, missing = plan(img, a.app or ["inventor"], a.lang, a.all)
    if a.json:
        json.dump({"steps": steps, "skipped": skipped, "missing": missing},
                  sys.stdout, indent=1)
        return
    for i, s in enumerate(steps, 1):
        flag = "" if s["present"] else "   [file not in image]"
        print("%2d. %-5s %-55s %s%s" % (i, s["type"], s["display"][:55],
                                        s["version"], flag))
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
