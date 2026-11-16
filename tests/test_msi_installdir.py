"""Every MSI package with an install location gets it as INSTALLDIR, as
ODIS passes it (docs/installer-completeness-review.md, "Needed" 4).
Synthetic manifests, dry run (msiexec is not started)."""
import os
import shlex
import tempfile
import unittest
from pathlib import Path

import image_fixture as fx

SETUP_XML = r"""<Setup><Properties>
<Property property="INV_INSTALL_PATH" defaultValue="%INSTALL_DEST%\Inventor 2027\"/>
</Properties></Setup>"""


class MsiInstallDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-installdir-")
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.image, self.prefix = t / "image", t / "prefix"
        fx.write(self.image, "setup.xml", SETUP_XML)
        pk = [("hive", "x64/hive/pkg.hive.xml", ""), ("InvPrivate", "x64/inv/pkg.invprivate.xml", ""),
              ("Odd", "x64/odd/pkg.odd.xml", ""), ("Given", "x64/given/pkg.given.xml", ""),
              ("NoLoc", "x64/noloc/pkg.noloc.xml", "")]
        fx.write(self.image, "manifest/app.inventor.xml", fx.app_xml("Inventor 2027", pk))
        fx.write(self.image, "x64/hive/pkg.hive.xml", fx.package_xml(
            "Autodesk Interoperability Engine Manager", "MSI", "x64/hive/adsk-hive-host.msi",
            install_location="%INSTALL_DEST%"))
        fx.write(self.image, "x64/inv/pkg.invprivate.xml", fx.package_xml(
            "Inventor Private 2027", "MSI", "x64/inv/InvPrivate.msi", install_location="%INV_INSTALL_PATH%",
            msi_props={"UNITS": "%UNITS%", "ADSK_LANG": "en-US"}))
        fx.write(self.image, "x64/odd/pkg.odd.xml", fx.package_xml(
            "Odd", "MSI", "x64/odd/odd.msi", install_location=r"%NOBODY_KNOWS%\Odd"))
        fx.write(self.image, "x64/given/pkg.given.xml", fx.package_xml(
            "Given", "MSI", "x64/given/given.msi", params="INSTALLDIR=C:\\Mine",
            install_location="%INSTALL_DEST%\\Given"))
        fx.write(self.image, "x64/noloc/pkg.noloc.xml", fx.package_xml("NoLoc", "MSI", "x64/noloc/noloc.msi"))
        self.prefix.mkdir()
        saved = os.environ.get("INV_LOGDIR")
        self.addCleanup(lambda: os.environ.pop("INV_LOGDIR", None) if saved is None
                        else os.environ.__setitem__("INV_LOGDIR", saved))
        self.mod, self.inst = fx.installer(self.image, self.prefix, t / "logs")
        self.inst.load_setup_properties(str(self.image))
        self.steps = {s["name"]: s for s in self.mod.odis.plan(self.mod.odis.Image(str(self.image)))[0]}
        self.seen = []
        # the command as logged: an msiexec line with a space runs through a batch file
        self.inst.run = lambda argv, logname, timeout=None, show=None: \
            self.seen.append(shlex.split(show) if show else argv) or 0

    def props(self, name):
        self.seen.clear()
        self.assertTrue(self.inst.do_msi(self.steps[name], name + ".log"))
        return [a for a in self.seen[0][8:] if "=" in a]

    def test_install_location_becomes_installdir(self):
        self.assertIn(r"INSTALLDIR=C:\Program Files\Autodesk", self.props("hive"))
        self.assertIn("INSTALLDIR=C:\\Program Files\\Autodesk\\Inventor 2027\\", self.props("InvPrivate"))

    def test_properties_only_odis_fills_are_still_left_out(self):
        p = self.props("InvPrivate")
        self.assertIn("ADSK_LANG=en-US", p)
        self.assertFalse(any(a.startswith("UNITS=") for a in p))

    def test_unknown_variable_is_not_passed_and_said(self):
        self.assertFalse(any(a.startswith("INSTALLDIR=") for a in self.props("Odd")))
        log = Path(self.inst.logdir, "install.log").read_text()
        self.assertIn(r"WARN INSTALLDIR not passed: unknown %NOBODY_KNOWS% in installLocation %NOBODY_KNOWS%\Odd",
                      log)

    def test_installdir_from_the_manifest_is_kept(self):
        self.assertEqual([a for a in self.props("Given") if a.startswith("INSTALLDIR=")], ["INSTALLDIR=C:\\Mine"])

    def test_package_without_location(self):
        self.assertFalse(any(a.startswith("INSTALLDIR=") for a in self.props("NoLoc")))


if __name__ == "__main__":
    unittest.main()
