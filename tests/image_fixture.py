"""Synthetic ODIS install images for the installer tests: application
manifests, package manifests, setup.xml and setup UI settings in the shape
scripts/lib/odis.py reads, with empty or tiny payload files. Nothing from
Autodesk's images."""
import argparse
import importlib.util
import os
from pathlib import Path
from xml.sax.saxutils import quoteattr

ROOT = Path(__file__).resolve().parents[1]
NS = "https://emsfs.autodesk.com/schema/manifest/1/0"


def load_installer():
    spec = importlib.util.spec_from_file_location("install_from_image", ROOT / "scripts" / "install-from-image.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def q(s):
    return quoteattr(s)


def package_xml(display, itype, file, params="", install_location=None, msi_props=None, properties=None,
                actions=(), deps=()):
    """A pkg.*.xml. deps: (name, path) pairs; actions: (type, path, params)."""
    info = ""
    if install_location is not None or msi_props:
        loc = " installLocation=%s" % q(install_location) if install_location is not None else ""
        props = "".join("<MsiProperty name=%s value=%s/>" % (q(k), q(v)) for k, v in (msi_props or {}).items())
        info = "<AdditionalPackageInfo%s><MsiTransform><MsiProperties>%s</MsiProperties></MsiTransform>" \
               "</AdditionalPackageInfo>" % (loc, props)
    prop = ""
    if properties:
        prop = "<Properties>%s</Properties>" % "".join(
            "<Property property=%s defaultValue=%s/>" % (q(k), q(v)) for k, v in properties.items())
    acts = ""
    if actions:
        acts = "<CustomCommands>%s</CustomCommands>" % "".join(
            "<Action type=%s path=%s params=%s/>" % (q(t), q(p), q(a)) for t, p, a in actions)
    dep = ""
    if deps:
        dep = "<Dependencies>%s</Dependencies>" % "".join(
            "<Package name=%s path=%s/>" % (q(n), q(p)) for n, p in deps)
    return ('<?xml version="1.0"?><Package xmlns="%s"><Identity><DisplayName>%s</DisplayName>'
            '<BuildNumber>31.0.1.1</BuildNumber></Identity>%s<Configuration>'
            '<InstallFile type=%s file=%s installParams=%s/>%s%s%s</Configuration></Package>'
            % (NS, display, dep, q(itype), q(file), q(params), info, prop, acts))


def app_xml(display, packages):
    """manifest/app.<name>.xml; packages: (name, path, installAs) triples."""
    return ('<?xml version="1.0"?><Application xmlns="%s"><Identity><DisplayName>%s</DisplayName></Identity>'
            '<Packages>%s</Packages></Application>'
            % (NS, display, "".join("<Package name=%s path=%s installAs=%s/>" % (q(n), q(p), q(i))
                                    for n, p, i in packages)))


def write(root, rel, text):
    p = Path(root, *rel.split("/"))
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        p.write_bytes(text)
    else:
        p.write_text(text)
    return p


def installer(image, prefix, logdir, **opts):
    """An Installer for IMAGE/PREFIX with the options main() would give."""
    mod = load_installer()
    os.environ["INV_LOGDIR"] = str(logdir)
    a = argparse.Namespace(image=str(image), prefix=str(prefix), lang="en-US", dry_run=True, redo=False,
                           start=1, only=None, app=None, no_app=[], include_app=[], no_content=False, extra=[],
                           no_dotnet48=True, prepared_prefix=False, preinstalled_webview2=False)
    for k, v in opts.items():
        setattr(a, k, v)
    return mod, mod.Installer(a)
