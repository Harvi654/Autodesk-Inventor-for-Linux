"""The default plan leaves out Autodesk Access and the ODIS installer."""

import tempfile
import unittest
from pathlib import Path

import image_fixture as fx


class UpdaterPackages(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory(prefix="autodesk-updaters-")
        self.addCleanup(work.cleanup)
        root = Path(work.name)
        fx.write(root, "manifest/app.acad.en-US.xml", fx.app_xml("AutoCAD 2027", [
            ("AcadCore", "x64/acad/pkg.core.xml", ""),
            ("AdAccess", "x64/Access/pkg.access.xml", ""),
        ]))
        fx.write(root, "x64/acad/pkg.core.xml", fx.package_xml(
            "AutoCAD", "MSI", "x64/acad/acad.msi", deps=[
                ("AdODIS", "ODIS/pkg.installer.xml"),
                ("Licensing", "ODIS/pkg.licensing.xml"),
            ]))
        fx.write(root, "x64/Access/pkg.access.xml", fx.package_xml(
            "Autodesk Access", "EXE", r"x64\Access\ADACCESS-Installer.EXE"))
        fx.write(root, "ODIS/pkg.installer.xml", fx.package_xml(
            "Autodesk Installer", "EXE", "ODIS/AdODIS-installer.exe"))
        fx.write(root, "ODIS/pkg.licensing.xml", fx.package_xml(
            "Autodesk Licensing", "EXE", "ODIS/AdskLicensing-installer.exe"))
        self.odis = fx.load_installer().odis
        self.image = self.odis.Image(str(root))

    def test_skip_updaters_by_payload_name(self):
        steps, skipped, missing = self.odis.plan(self.image, ["acad.en-US"])
        self.assertEqual([step["name"] for step in steps], ["Licensing", "AcadCore"])
        self.assertEqual([name for name, _ in skipped], ["AdODIS", "AdAccess"])
        self.assertEqual(missing, [])

    def test_explicit_package_selection(self):
        steps, skipped, _ = self.odis.plan(self.image, ["acad.en-US"], extra=["adaccess"])
        self.assertEqual([step["name"] for step in steps], ["Licensing", "AcadCore", "AdAccess"])
        self.assertEqual([name for name, _ in skipped], ["AdODIS"])

    def test_include_all(self):
        steps, skipped, _ = self.odis.plan(self.image, ["acad.en-US"], include_all=True)
        self.assertEqual([step["name"] for step in steps], ["AdODIS", "Licensing", "AcadCore", "AdAccess"])
        self.assertEqual(skipped, [])
