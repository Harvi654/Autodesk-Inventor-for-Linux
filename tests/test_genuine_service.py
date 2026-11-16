"""Autodesk Genuine Service (AGS) can be installed on request
(--with ags), although it is optional in the manifest and on the skip
list; by default it stays out until its test on a prefix copy
(docs/installer-completeness-review.md). Synthetic manifests."""
import tempfile
import unittest
from pathlib import Path

import image_fixture as fx


class GenuineService(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-ags-")
        self.addCleanup(self.tmp.cleanup)
        self.image = Path(self.tmp.name)
        fx.write(self.image, "manifest/app.inventor.xml", fx.app_xml("Inventor 2027", [
            ("InvCore", "x64/inv/pkg.invcore.xml", ""), ("AGS", "x86/ags/pkg.ags.xml", "optional"),
            ("CER", "x64/cer/pkg.cer.xml", "")]))
        for rel, display, f in (("x64/inv/pkg.invcore.xml", "Inventor Core 2027", "x64/inv/InvCore.msi"),
                                ("x86/ags/pkg.ags.xml", "Autodesk Genuine Service", "x86/ags/AGS.msi"),
                                ("x64/cer/pkg.cer.xml", "Customer Error Reporting", "x64/cer/cer.msi")):
            fx.write(self.image, rel, fx.package_xml(display, "MSI", f))
        self.odis = fx.load_installer().odis

    def plan(self, extra=()):
        steps, skipped, missing = self.odis.plan(self.odis.Image(str(self.image)), ["inventor"], extra=extra)
        return [s["name"] for s in steps], dict(skipped)

    def test_left_out_by_default(self):
        names, skipped = self.plan()
        self.assertEqual(names, ["InvCore"])
        self.assertIn("optional", skipped["AGS"])

    def test_installed_with_with_ags(self):
        names, skipped = self.plan(extra=["ags"])
        self.assertEqual(names, ["InvCore", "AGS"])
        self.assertNotIn("AGS", skipped)
        # the rest of the skip list stays skipped
        self.assertIn("install it with --with CER", skipped["CER"])

    def test_skip_list_package_that_is_not_optional(self):
        names, skipped = self.plan(extra=["cer"])
        self.assertIn("CER", names)


if __name__ == "__main__":
    unittest.main()
