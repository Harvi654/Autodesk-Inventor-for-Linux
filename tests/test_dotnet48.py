""".NET Framework 4.8 prerequisite: found in an install image by its
Identity, not by a fixed path, and planned by install-from-image.py after the
product's packages.

Synthetic manifests only, in the ODIS namespace: no Autodesk files. The
installer is run with --dry-run, so no Wine is started."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import odis  # noqa: E402

NS = "https://emsfs.autodesk.com/schema/manifest/1/0"


def prerequisite(path, display, exe, params="/q /norestart", codes=(5100,)):
    path.parent.mkdir(parents=True, exist_ok=True)
    sc = "".join("<SuccessCode>%d</SuccessCode>" % c for c in codes)
    path.write_text(
        '<?xml version="1.0"?><Package xmlns="%s"><Identity><DisplayName>%s</DisplayName>'
        '<BuildNumber>4.8.1.0</BuildNumber></Identity><Configuration>'
        '<InstallFile type="EXE" contents="File" installParams="%s" file="%s">'
        '<InstallSuccessCodes>%s</InstallSuccessCodes></InstallFile>'
        '<Attributes ignoreFailure="true"/>'
        '<Conditions><Condition state="INSTALLED"><![CDATA[( 1 < %%REL%% )]]></Condition></Conditions>'
        '</Configuration></Package>' % (NS, display, params, exe, sc))


def image(root, with_dotnet=True, folder="3rdParty/NetFx/48"):
    (root / "manifest").mkdir(parents=True)
    (root / "manifest" / "app.inventor.xml").write_text(
        '<?xml version="1.0"?><Package xmlns="%s"><Identity><DisplayName>Inventor</DisplayName>'
        '</Identity></Package>' % NS)
    (root / "Setup.exe").write_bytes(b"")
    if with_dotnet:
        d = root / folder
        prerequisite(d / "pkg.netfx.xml", ".NET Framework Runtime 4.8", folder + "/netfx_full.exe")
        prerequisite(d / "pkg.netfx_1031.xml", ".NET Framework Runtime 4.8 Language Pack (de-DE)",
                     folder + "/netfx_lp.exe")
        (d / "netfx_full.exe").write_bytes(b"MZ")


class FindPackage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-dotnet-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_found_by_display_name_not_language_pack(self):
        image(self.root)
        s = odis.find_package(odis.Image(str(self.root)), ".NET Framework Runtime 4.8")
        self.assertIsNotNone(s)
        self.assertEqual(s["file"], "3rdParty/NetFx/48/netfx_full.exe")
        self.assertEqual(s["params"], "/q /norestart")
        self.assertEqual(s["successCodes"], [5100])
        self.assertTrue(s["present"])
        self.assertIn("%REL%", s["condition"])
        self.assertEqual(s["installAs"], "prerequisite")

    def test_other_folder(self):
        image(self.root, folder="ThirdParty/dotnet")
        s = odis.find_package(odis.Image(str(self.root)), ".NET Framework Runtime 4.8")
        self.assertEqual(s["file"], "ThirdParty/dotnet/netfx_full.exe")

    def test_absent(self):
        image(self.root, with_dotnet=False)
        self.assertIsNone(odis.find_package(odis.Image(str(self.root)), ".NET Framework Runtime 4.8"))

    def test_dry_run_plans_it_after_the_packages(self):
        image(self.root)
        prefix = self.root / "prefix"
        env = dict(os.environ, INV_LOGDIR=str(self.root / "logs"), INV_YEAR="2027")
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "install-from-image.py"),
                              str(self.root), "--prefix", str(prefix), "--dry-run"],
                             env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn(".NET Framework 4.8 (3rdParty/NetFx/48/netfx_full.exe", out.stdout)
        self.assertIn("remove Wine Mono", out.stdout)
        self.assertLess(out.stdout.index(".NET Framework 4.8 ("), out.stdout.index("All steps finished"))

    def test_dry_run_opt_out(self):
        image(self.root)
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "install-from-image.py"),
                              str(self.root), "--prefix", str(self.root / "prefix"), "--dry-run",
                              "--no-dotnet48"],
                             env=dict(os.environ, INV_LOGDIR=str(self.root / "logs")),
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("--no-dotnet48", out.stdout)
        self.assertNotIn("remove Wine Mono", out.stdout)


FAKE_WINE = """#!/bin/sh
# Answers only the query dotnet48_present makes; the override is "native"
# when the test put a marker file into the prefix.
case "$*" in
    *"reg query"*DllOverrides*mscoree*)
        if [ -f "$WINEPREFIX/override-native" ]; then
            printf '\\nHKEY_CURRENT_USER\\\\Software\\\\Wine\\\\DllOverrides\\n    mscoree    REG_SZ    native\\n\\n'
        else
            printf '\\nHKEY_CURRENT_USER\\\\Software\\\\Wine\\\\DllOverrides\\n    mscoree    REG_SZ    builtin\\n\\n'
        fi ;;
esac
exit 0
"""


class Dotnet48Present(unittest.TestCase):
    """The shell side: dotnet48_present and inv_default_disabled_addins from
    scripts/lib/common.sh, run with a fake wine in a fake prefix."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-dotnet-sh-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.home = root / "home"
        self.prefix = self.home / ".wine-inventor2027"
        inv = self.prefix / "drive_c" / "Program Files" / "Autodesk" / "Inventor 2027" / "Bin"
        inv.mkdir(parents=True)
        (inv / "Inventor.exe").write_bytes(b"")
        self.bin = root / "bin"
        self.bin.mkdir()
        wine = self.bin / "wine"
        wine.write_text(FAKE_WINE)
        wine.chmod(0o755)

    def clr(self, *frameworks):
        for fw in frameworks:
            d = self.prefix / "drive_c" / "windows" / "Microsoft.NET" / fw / "v4.0.30319"
            d.mkdir(parents=True, exist_ok=True)
            (d / "clr.dll").write_bytes(b"MZ")

    def run_sh(self):
        env = {"HOME": str(self.home), "USER": "test", "PATH": "%s:/usr/bin:/bin" % self.bin,
               "INV_YEAR": "2027", "INV_PREFIX": str(self.prefix), "WINEPREFIX": str(self.prefix),
               "INV_WINE": "system"}
        script = ('source scripts/lib/common.sh >/dev/null 2>&1; '
                  'if dotnet48_present; then echo PRESENT; else echo MISSING; fi; '
                  'inv_default_disabled_addins')
        out = subprocess.run(["bash", "-c", script], cwd=str(ROOT), env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = out.stdout.split()
        return lines[0], set(lines[1:])

    def test_present_with_clr_and_native_override(self):
        self.clr("Framework64", "Framework")
        (self.prefix / "override-native").write_bytes(b"")
        state, off = self.run_sh()
        self.assertEqual(state, "PRESENT")
        self.assertNotIn("Anark.Core.addin", off)
        self.assertNotIn("Autodesk.Publisher.Inventor.addin", off)
        self.assertIn("Autodesk.SharedViews.Inventor.addin", off)

    def test_missing_without_anything(self):
        state, off = self.run_sh()
        self.assertEqual(state, "MISSING")
        self.assertIn("Anark.Core.addin", off)
        self.assertIn("Autodesk.Publisher.Inventor.addin", off)

    def test_missing_with_clr_but_builtin_mscoree(self):
        self.clr("Framework64", "Framework")
        state, off = self.run_sh()
        self.assertEqual(state, "MISSING")
        self.assertIn("Anark.Core.addin", off)

    def test_missing_with_native_override_but_one_clr(self):
        self.clr("Framework64")
        (self.prefix / "override-native").write_bytes(b"")
        state, _ = self.run_sh()
        self.assertEqual(state, "MISSING")


if __name__ == "__main__":
    unittest.main()
