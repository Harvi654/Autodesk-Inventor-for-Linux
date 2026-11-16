"""CONTENT_PATH comes from the setup UI settings of the application
(SetupRes/locale/<lang>/<app>.xml, defaultVal %PROGRAMDATA%\\Autodesk), or
ODIS's default when no file names it (docs/installer-completeness-review.md,
"Needed" 3). Synthetic image, dry run."""
import os
import tempfile
import unittest
from pathlib import Path

import image_fixture as fx

DCLIBRARY_UI = r"""<?xml version="1.0"?>
<SetupUI xmlns="urn:example">
  <Page id="ContentCenter">
    <Setting name="CONTENT_PATH" type="folder" defaultVal="%PROGRAMDATA%\Autodesk"/>
    <Choice label="Libraries" defaultVal="all"/>
  </Page>
</SetupUI>
"""


class SetupUISettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-setup-ui-")
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.image, self.prefix = t / "image", t / "prefix"
        fx.write(self.image, "manifest/app.inventor.xml",
                 fx.app_xml("Inventor 2027", [("InvCore", "x64/inv/pkg.invcore.xml", "")]))
        fx.write(self.image, "manifest/app.dclibrary.xml",
                 fx.app_xml("Content Center 2027", [("DCLibrary", "x64/dc/pkg.dclibrary.xml", "")]))
        fx.write(self.image, "x64/inv/pkg.invcore.xml", fx.package_xml("Inventor Core 2027", "ADIX", "x64/inv/c.adix"))
        fx.write(self.image, "x64/dc/pkg.dclibrary.xml", fx.package_xml(
            "Content Center Libraries 2027", "MSI", "x64/dc/DCLibrary64.msi",
            install_location=r"%CONTENT_PATH%\Inventor 2027"))
        self.prefix.mkdir()
        saved = os.environ.get("INV_LOGDIR")
        self.addCleanup(lambda: os.environ.pop("INV_LOGDIR", None) if saved is None
                        else os.environ.__setitem__("INV_LOGDIR", saved))

    def inst(self, apps=("inventor", "dclibrary"), lang="en-US"):
        mod, inst = fx.installer(self.image, self.prefix, Path(self.tmp.name) / "logs", lang=lang)
        inst.load_setup_ui_settings(mod.odis.Image(str(self.image)), list(apps))
        return mod, inst

    def log(self, inst):
        return Path(inst.logdir, "install.log").read_text()

    def dclibrary_location(self, mod, inst):
        steps = mod.odis.plan(mod.odis.Image(str(self.image)), ["dclibrary"])[0]
        return inst.expand(steps[0]["installLocation"], step=steps[0])

    def test_content_path_from_the_settings_file(self):
        fx.write(self.image, "SetupRes/locale/en-US/dclibrary.xml", DCLIBRARY_UI)
        mod, inst = self.inst()
        self.assertEqual(self.dclibrary_location(mod, inst), r"C:\ProgramData\Autodesk\Inventor 2027")
        log = self.log(inst)
        self.assertIn(r"var    %CONTENT_PATH% = C:\ProgramData\Autodesk (setup UI default, "
                      + os.path.join("SetupRes", "locale", "en-US", "dclibrary.xml") + ")", log)
        # an element with a defaultVal but no variable name is reported
        self.assertIn("settings without a variable name (not used): Choice", log)

    def test_other_language_falls_back_to_en_us(self):
        fx.write(self.image, "SetupRes/locale/en-US/dclibrary.xml",
                 '<s><CONTENT_PATH defaultVal="C:\\Libraries"/></s>')
        mod, inst = self.inst(lang="de-DE")
        self.assertEqual(inst.vars["content_path"], "C:\\Libraries")
        self.assertIn("setup UI default", self.log(inst))

    def test_language_file_wins(self):
        fx.write(self.image, "SetupRes/locale/en-US/dclibrary.xml", '<s><CONTENT_PATH defaultVal="C:\\En"/></s>')
        fx.write(self.image, "SetupRes/locale/de-DE/dclibrary.xml", '<s><CONTENT_PATH defaultVal="C:\\De"/></s>')
        mod, inst = self.inst(lang="de-DE")
        self.assertEqual(inst.vars["content_path"], "C:\\De")

    def test_odis_default_without_a_settings_file(self):
        mod, inst = self.inst()
        self.assertEqual(self.dclibrary_location(mod, inst), r"C:\ProgramData\Autodesk\Inventor 2027")
        self.assertIn("(ODIS default; no setup UI settings file names it)", self.log(inst))

    def test_file_the_xml_parser_rejects(self):
        # as in Inventor 2027's image: <Setting name=... defaultVal=... deployment=...> with children
        fx.write(self.image, "SetupRes/locale/en-US/dclibrary.xml",
                 '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "&undefined;">]><Settings>\n'
                 '<Setting name="CONTENT_PATH" defaultVal="%PROGRAMDATA%\\Autodesk" deployment="true" '
                 'standalone="true">\n<String id="IDC_CONTENT_PATH">&nbsp;Content</String></Setting></Settings>')
        mod, inst = self.inst()
        self.assertEqual(inst.vars["content_path"], "%PROGRAMDATA%\\Autodesk")
        self.assertIn("setup UI default", self.log(inst))

    def test_setting_in_another_file_or_folder(self):
        fx.write(self.image, "x64/Setup/SetupRes/locale/en-US/inventor-content.xml",
                 '<s><Setting name="CONTENT_PATH" defaultVal="C:\\Elsewhere"/></s>')
        mod, inst = self.inst()
        self.assertEqual(inst.vars["content_path"], "C:\\Elsewhere")
        self.assertIn("inventor-content.xml", self.log(inst))

    def test_settings_of_an_application_not_planned_are_read_too(self):
        fx.write(self.image, "SetupRes/locale/en-US/dclibrary.xml", '<s><CONTENT_PATH defaultVal="C:\\X"/></s>')
        mod, inst = self.inst(apps=("inventor",))
        self.assertEqual(inst.vars["content_path"], "C:\\X")


if __name__ == "__main__":
    unittest.main()
