"""MSI_FROM_C: a package whose custom action fails when it reads from the
image's drive M: is installed from a copy of its folder on C:, removed
afterwards (maintainer's decision for AceInvAddIn-ca.msi if the drive is
the cause, 2026-11-16). Synthetic image, fake run."""
import os
import shlex
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import image_fixture as fx


def msi(name):
    return {"name": name, "type": "MSI", "display": name, "version": "1", "file": "x64/AceAddIn-ca/AceInvAddIn-ca.msi",
            "params": "", "installLocation": None, "msiProperties": {}, "properties": {}, "actions": []}


class MsiFromC(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-msi-from-c-")
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.image, self.prefix = t / "image", t / "prefix"
        fx.write(self.image, "x64/AceAddIn-ca/AceInvAddIn-ca.msi", b"msi")
        fx.write(self.image, "x64/AceAddIn-ca/Documents/ADSK/Content/AceInvLib.zip", b"zip")
        (self.prefix / "drive_c").mkdir(parents=True)
        saved = os.environ.get("INV_LOGDIR")
        self.addCleanup(lambda: os.environ.pop("INV_LOGDIR", None) if saved is None
                        else os.environ.__setitem__("INV_LOGDIR", saved))
        self.mod, self.inst = fx.installer(self.image, self.prefix, t / "logs", dry_run=False)
        self.seen = []

        def run(argv, logname, timeout=None, show=None):
            # what msiexec would read: the copy exists while it runs
            self.seen.append((shlex.split(show) if show else argv,
                              (self.prefix / "drive_c/odis-media/ACEINVADDIN_CA/Documents/ADSK/Content/AceInvLib.zip")
                              .exists()))
            return 0
        self.inst.run = run

    def test_listed_package_runs_from_a_copy_on_c(self):
        with mock.patch.dict(self.mod.MSI_FROM_C, {"aceinvaddin_ca": "its unzip action fails on M:"}):
            self.assertTrue(self.inst.do_msi(msi("ACEINVADDIN_CA"), "31-ACEINVADDIN_CA.log"))
        argv, existed = self.seen[0]
        self.assertEqual(argv[3], r"C:\odis-media\ACEINVADDIN_CA\AceInvAddIn-ca.msi")
        self.assertTrue(existed)
        self.assertFalse((self.prefix / "drive_c/odis-media/ACEINVADDIN_CA").exists())
        log = Path(self.inst.logdir, "install.log").read_text()
        self.assertIn("from a copy on C: (its unzip action fails on M:)", log)
        self.assertIn("copy removed", log)

    def test_other_packages_run_from_m(self):
        self.inst.do_msi(msi("HIVE"), "02-HIVE.log")
        self.assertEqual(self.seen[0][0][3], r"M:\x64\AceAddIn-ca\AceInvAddIn-ca.msi")

    def test_empty_until_the_diagnosis(self):
        self.assertEqual(self.mod.MSI_FROM_C, {})


if __name__ == "__main__":
    unittest.main()
