#!/usr/bin/env python3
"""What our installer leaves out of an ODIS image, without installing anything.

For every application manifest of the image (manifest/app.*.xml) and every
package they pull in, lists:
  - the applications and which of their packages are optional;
  - %VARIABLES% that install-from-image.py cannot fill in, per place
    (installLocation, MSI properties, install parameters, action paths and
    action parameters) - these are dropped or passed on unexpanded;
  - custom action types it does not run (it runs preInstall/postInstall).

Usage: odis-audit.py IMAGE [--lang en-US]
Names only; nothing from the packages' contents.
"""
import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "scripts", "lib"))
import odis  # noqa: E402

# the variables install-from-image.py knows (Installer.vars)
KNOWN = {"commonprogramfiles", "commonprogramfiles(x86)", "programfiles", "programfiles(x86)",
         "programdata", "allusersprofile", "install_dest", "adsk_odis_metadata_base_location",
         "temp", "tmp", "inv_locale", "media_root", "install_source"}
RUN_KINDS = {"preInstall", "postInstall"}
VAR = re.compile(r"%([A-Za-z0-9_()]+)%")
# the image's own variables install-from-image.py reads (setup.xml
# properties); filled in by main()
IMAGE_VARS = {}


def unknown(s, step):
    if not s:
        return []
    props = dict(IMAGE_VARS)
    props.update({k.lower(): v for k, v in (step.get("properties") or {}).items()})
    out = []
    for _ in range(5):   # properties may refer to other variables
        changed = False
        for m in VAR.finditer(s):
            n = m.group(1).lower()
            if n in props:
                s = s.replace(m.group(0), props[n])
                changed = True
        if not changed:
            break
    for m in VAR.finditer(s):
        if m.group(1).lower() not in KNOWN:
            out.append(m.group(1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--lang", default="en-US")
    a = ap.parse_args()
    img = odis.Image(a.image)
    for pr in odis.setup_properties(img.root):
        if pr["name"].lower() not in KNOWN:
            IMAGE_VARS[pr["name"].lower()] = pr["default"]
    mdir = os.path.join(img.root, "manifest")
    apps = sorted(f[4:-4] for f in os.listdir(mdir) if f.startswith("app.") and f.endswith(".xml"))
    print("## Variables from setup.xml (<Properties>)")
    for pr in odis.setup_properties(img.root):
        print("- %s = %s%s" % (pr["name"], pr["default"], "".join(
            "; RegistrySearch %s\\%s -> %s" % (x["root"], x["key"], x["name"] or "(default)") if x["root"] and x["key"]
            else "; RegistrySearch not understood (attributes: %s)" % ", ".join(x["attrs"]) for x in pr["searches"])))
    print("\n## Applications in the image")
    print("manifest/app.*.xml: %s (our installer plans only 'inventor' unless --app is given)" % ", ".join(apps))
    for app in apps:
        steps, skipped, missing = odis.plan(img, (app,), a.lang)
        allsteps, _, _ = odis.plan(img, (app,), a.lang, include_all=True)
        print("- %s: %d packages planned, %d with optional/skipped ones" % (app, len(steps), len(allsteps)))
        for n, why in skipped:
            print("    - skipped: %s (%s)" % (n, why))
        for n, rel, chain in missing:
            print("    - MISSING manifest: %s (%s)" % (n, rel))

    print("\n## Unknown %VARIABLES% per package (all applications, all packages)")
    seen = set()
    kinds = collections.Counter()
    for app in apps:
        steps, _, _ = odis.plan(img, (app,), a.lang, include_all=True)
        for s in steps:
            if s["manifest"].lower() in seen:
                continue
            seen.add(s["manifest"].lower())
            lines = []
            for v in unknown(s.get("installLocation"), s):
                lines.append("installLocation: %%%s%% (MSI packages: INSTALLDIR not passed)" % v)
            for k, val in s["msiProperties"].items():
                for v in unknown(val, s):
                    lines.append("MSI property %s: %%%s%% (property dropped)" % (k, v))
            for v in unknown(s["params"], s):
                lines.append("install parameters: %%%s%% (passed on unexpanded)" % v)
            for act in s["actions"]:
                kinds[act["type"]] += 1
                tag = "action %s %s" % (act["type"], os.path.basename((act["path"] or "").replace("\\", "/")))
                if act["type"] not in RUN_KINDS:
                    lines.append("%s: action type not run by us" % tag)
                    continue
                for v in unknown(act["path"], s):
                    lines.append("%s: path %%%s%% (action skipped)" % (tag, v))
                for v in unknown(act["params"], s):
                    lines.append("%s: parameter %%%s%% (passed on unexpanded)" % (tag, v))
            if lines:
                print("- %s [%s, %s, app %s]" % (s["name"], s["type"], s["installAs"] or "-", app))
                for l in dict.fromkeys(lines):
                    print("    - " + l)
    print("\n## Custom action types in the image")
    for k, n in sorted(kinds.items()):
        print("- %s: %d%s" % (k, n, "" if k in RUN_KINDS else "  (not run by us)"))


if __name__ == "__main__":
    main()
