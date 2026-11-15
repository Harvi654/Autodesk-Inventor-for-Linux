#!/usr/bin/env python3
"""List what the AppxManifest.xml of each ADIX package in an ODIS image
declares beyond files: extension categories (COM servers, file type
associations, ...), with counts and the declared names (ProgIDs, file
types), no other content.

ODIS registers these with its own handlers (ComServer, FileTypeAssociation,
fonts, shortcuts); install-from-image.py today only places the files and
imports Registry.dat. Usage: adix-extensions.py IMAGE [--lang en-US]
"""
import argparse
import collections
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "scripts", "lib"))
import odis  # noqa: E402


def local(tag):
    return tag.rsplit("}", 1)[-1]


def manifest_of(path):
    if os.path.isdir(path):
        for d, _, files in os.walk(path):
            for f in files:
                if f.lower() == "appxmanifest.xml":
                    return open(os.path.join(d, f), "rb").read()
        return None
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.lower() == "appxmanifest.xml":
                return z.read(n)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--lang", default="en-US")
    a = ap.parse_args()
    img = odis.Image(a.image)
    mdir = os.path.join(img.root, "manifest")
    apps = sorted(f[4:-4] for f in os.listdir(mdir) if f.startswith("app.") and f.endswith(".xml"))
    seen = set()
    for app in apps:
        steps, _, _ = odis.plan(img, (app,), a.lang, include_all=True)
        for s in steps:
            if s["type"] != "ADIX" or s["manifest"].lower() in seen:
                continue
            seen.add(s["manifest"].lower())
            path = img.find(s["file"])
            if not path:
                print("- %s: package file not in the image" % s["name"])
                continue
            data = manifest_of(path)
            if data is None:
                print("- %s: no AppxManifest.xml" % s["name"])
                continue
            root = ET.fromstring(data)
            cats = collections.Counter()
            names = collections.defaultdict(set)
            for el in root.iter():
                t = local(el.tag)
                if t == "Extension" and el.get("Category"):
                    cats[el.get("Category")] += 1
                elif t == "Class" and el.get("Id"):
                    cats["  COM classes"] += 1
                elif t == "ProgId" and el.get("Id"):
                    names["ProgIds"].add(el.get("Id"))
                elif t == "FileTypeAssociation" and el.get("Name"):
                    names["file type associations"].add(el.get("Name"))
                elif t == "FileType" and el.text:
                    names["file types"].add(el.text.strip())
                elif t == "Font" and el.get("File"):
                    cats["  fonts"] += 1
                elif t == "Shortcut":
                    cats["  shortcuts"] += 1
                elif t == "TypeLib" and el.get("Id"):
                    cats["  type libraries"] += 1
            print("- %s [app %s]" % (s["name"], app))
            if not cats and not names:
                print("    (no extensions)")
            for c, n in sorted(cats.items()):
                print("    - %s: %d" % (c.strip(), n))
            for k, v in sorted(names.items()):
                print("    - %s (%d): %s" % (k, len(v), ", ".join(sorted(v)[:20]) + (" ..." if len(v) > 20 else "")))


if __name__ == "__main__":
    main()
