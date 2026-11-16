#!/usr/bin/env python3
"""Which INSTALLDIR did ODIS pass to each MSI package on Windows, next to
the package's installLocation in the image's manifests?

Question behind it (installer completeness review, 2026-11-16):
adsk-hive-host.msi has no installLocation, yet Windows passed
INSTALLDIR=C:\\Program Files\\Autodesk (= %INSTALL_DEST%). Does ODIS pass
INSTALL_DEST to every MSI without an installLocation?

Usage: installdir-check.py CAP_DIR IMAGE [--lang en-US]
  CAP_DIR  capture of tools/capture-state.ps1 (after/logs holds the MSI logs)
  IMAGE    the unpacked install image
Prints, per MSI package of all applications (optional ones included): its
installLocation, and the INSTALLDIR of Windows' command line (masked) or
that Windows had no log for it. Then a verdict for the packages without
an installLocation.
"""
import argparse
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "lib"))
import odis  # noqa: E402

spec = importlib.util.spec_from_file_location("compare_reference", os.path.join(HERE, "compare-reference.py"))
cr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cr)


def msi_packages(img, lang):
    mdir = os.path.join(img.root, "manifest")
    apps = sorted(f[4:-4] for f in os.listdir(mdir) if f.startswith("app.") and f.endswith(".xml"))
    seen = {}
    for app in apps:
        steps, _, _ = odis.plan(img, (app,), lang, include_all=True)
        for s in steps:
            if s["type"] == "MSI" and s["manifest"].lower() not in seen:
                seen[s["manifest"].lower()] = s
    return list(seen.values())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cap")
    ap.add_argument("image")
    ap.add_argument("--lang", default="en-US")
    a = ap.parse_args()
    win = cr.windows_msi_logs(os.path.join(a.cap, "after", "logs"))
    users = [os.environ.get("USER", "")]
    no_loc = []
    print("| package | MSI | installLocation | Windows INSTALLDIR |")
    print("|---|---|---|---|")
    for s in sorted(msi_packages(odis.Image(a.image), a.lang), key=lambda s: s["name"].lower()):
        msi = os.path.basename(s["file"].replace("\\", "/"))
        w = win.get(msi.lower())
        given = "no Windows log" if w is None else w[1].get("INSTALLDIR", "(not passed)")
        print("| %s | %s | %s | %s |" % (s["name"], msi, s.get("installLocation") or "-",
                                        cr.mask(given, users)))
        if not s.get("installLocation"):
            no_loc.append((s["name"], given))
    print()
    print("MSI packages without an installLocation: %d" % len(no_loc))
    for name, given in no_loc:
        print("- %s: %s" % (name, cr.mask(given, users)))
    ran = [g for _, g in no_loc if g != "no Windows log"]
    if ran and all(g.rstrip("\\").lower() == r"c:\program files\autodesk" for g in ran):
        print("Verdict: every one Windows ran got INSTALLDIR = %INSTALL_DEST% (C:\\Program Files\\Autodesk)")
    elif ran:
        print("Verdict: not the same for all - see the list")
    else:
        print("Verdict: Windows ran none of them as an MSI with a log")


if __name__ == "__main__":
    main()
