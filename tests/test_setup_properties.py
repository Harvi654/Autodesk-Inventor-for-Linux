"""The <Properties> of an image's setup.xml become variables
(INV_INSTALL_PATH = %INSTALL_DEST%\\Inventor 2027\\); a RegistrySearch
finds an existing installation in the prefix (docs/installer-completeness-
review.md, "Needed" 2). Synthetic image, dry run."""
import os
import tempfile
import unittest
from pathlib import Path

import image_fixture as fx

SETUP_XML = r"""<?xml version="1.0"?>
<Setup xmlns="urn:example">
  <Properties>
    <Property property="INV_INSTALL_PATH" defaultValue="%INSTALL_DEST%\Inventor 2027\">
      <RegistrySearch root="HKLM" key="SOFTWARE\Autodesk\Inventor\RegistryVersion31.0" name="InventorLocation"/>
    </Property>
    <Property property="WOW_PATH" defaultValue="C:\Default\">
      <RegistrySearch path="HKEY_LOCAL_MACHINE\SOFTWARE\Example" win64="false"/>
    </Property>
    <Property property="ODD_SEARCH" defaultValue="odd">
      <RegistrySearch somewhere="x"/>
    </Property>
    <Property property="INSTALL_DEST" defaultValue="D:\Elsewhere"/>
  </Properties>
</Setup>
"""


class SetupProperties(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-setup-props-")
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.image, self.prefix = t / "image", t / "prefix"
        fx.write(self.image, "setup.xml", SETUP_XML)
        fx.write(self.image, "manifest/app.inventor.xml",
                 fx.app_xml("Inventor 2027", [("InvCore", "x64/inv/pkg.invcore.xml", "")]))
        fx.write(self.image, "x64/inv/pkg.invcore.xml", fx.package_xml(
            "Inventor Core 2027", "ADIX", "x64/inv/InvCore.adix",
            actions=[("postInstall", r"%PROGRAMFILES%\Autodesk\Tool\InvAcNGEN.exe",
                      r'install "%INV_INSTALL_PATH%Bin"')]))
        fx.write(self.image, "x64/inv/InvCore.adix", b"")
        self.prefix.mkdir()
        self.saved = os.environ.get("INV_LOGDIR")
        self.addCleanup(lambda: os.environ.pop("INV_LOGDIR", None) if self.saved is None
                        else os.environ.__setitem__("INV_LOGDIR", self.saved))

    def inst(self):
        mod, inst = fx.installer(self.image, self.prefix, Path(self.tmp.name) / "logs")
        inst.load_setup_properties(str(self.image))
        return inst

    def log(self, inst):
        return Path(inst.logdir, "install.log").read_text()

    def test_defaults_in_a_fresh_prefix(self):
        inst = self.inst()
        self.assertEqual(inst.expand("%INV_INSTALL_PATH%Bin"), r"C:\Program Files\Autodesk\Inventor 2027\Bin")
        log = self.log(inst)
        self.assertIn(r"var    %INV_INSTALL_PATH% = C:\Program Files\Autodesk\Inventor 2027\ (setup.xml; "
                      r"HKLM\SOFTWARE\Autodesk\Inventor\RegistryVersion31.0 -> InventorLocation: not in the prefix)",
                      log)
        # ODIS's own folder variables are not replaced by setup.xml
        self.assertEqual(inst.vars["install_dest"], r"C:\Program Files\Autodesk")
        self.assertIn(r"%INSTALL_DEST% from setup.xml ignored", log)
        # a search we cannot read is said so, the default is used
        self.assertEqual(inst.vars["odd_search"], "odd")
        self.assertIn("search not understood (attributes: somewhere)", log)

    def test_found_value_wins(self):
        (self.prefix / "system.reg").write_text(
            "WINE REGISTRY Version 2\n\n"
            "[Software\\\\Autodesk\\\\Inventor\\\\RegistryVersion31.0] 1700000000\n"
            "\"InventorLocation\"=\"D:\\\\Inventor 2027\\\\\"\n\n"
            "[Software\\\\Wow6432Node\\\\Example] 1700000000\n@=\"C:\\\\Found32\\\\\"\n")
        inst = self.inst()
        self.assertEqual(inst.expand("%INV_INSTALL_PATH%Bin"), r"D:\Inventor 2027\Bin")
        self.assertEqual(inst.vars["wow_path"], "C:\\Found32\\")
        self.assertIn("RegistryVersion31.0 -> InventorLocation: found", self.log(inst))

    def test_key_without_the_value_keeps_the_default(self):
        (self.prefix / "system.reg").write_text(
            "WINE REGISTRY Version 2\n\n[Software\\\\Autodesk\\\\Inventor\\\\RegistryVersion31.0] 1\n\"Other\"=\"x\"\n")
        inst = self.inst()
        self.assertEqual(inst.vars["inv_install_path"], r"%INSTALL_DEST%\Inventor 2027" + "\\")
        self.assertIn("InventorLocation: no such value", self.log(inst))

    def test_action_parameter_is_expanded(self):
        # expanded first, then split like a Windows command line: the quotes
        # in the manifest keep the path with spaces together
        inst = self.inst()
        seen = []
        inst.run = lambda argv, logname, timeout=None: seen.append(argv) or 0
        step = fx.load_installer().odis.plan(fx.load_installer().odis.Image(str(self.image)))[0][0]
        self.assertTrue(inst.do_actions(step, "x.log"))
        self.assertEqual(seen[0][1:], [r"C:\Program Files\Autodesk\Tool\InvAcNGEN.exe", "install",
                                       r"C:\Program Files\Autodesk\Inventor 2027\Bin"])

    def test_no_setup_xml(self):
        os.remove(self.image / "setup.xml")
        inst = self.inst()
        self.assertNotIn("inv_install_path", inst.vars)


if __name__ == "__main__":
    unittest.main()
