"""ADIX packages: files outside VFS/ that are not the package's metadata
(SharedComponents.json at the root of InvCore) are listed in the log
instead of being dropped silently (docs/installer-completeness-review.md,
"Needed" 7). Synthetic ADIX zips."""
import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

import image_fixture as fx


class AdixRootFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-adix-root-")
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        (t / "image").mkdir()
        saved = os.environ.get("INV_LOGDIR")
        self.addCleanup(lambda: os.environ.pop("INV_LOGDIR", None) if saved is None
                        else os.environ.__setitem__("INV_LOGDIR", saved))
        self.prefix = t / "prefix"
        self.mod, self.inst = fx.installer(t / "image", self.prefix, t / "logs", dry_run=False)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name in ("AppxManifest.xml", "AppxBlockMap.xml", "[Content_Types].xml", "AppxSignature.p7x",
                         "SharedComponents.json", "Extra/notes.txt", "VFS/loose.txt",
                         "VFS/ProgramFilesX64/Autodesk/Inventor 2027/Bin/a.dll"):
                z.writestr(name, b"x")
            z.writestr("VFS/ProgramFilesX64/Autodesk/Inventor 2027/Bin/empty/", b"")
        self.pkg = t / "InvCore.adix"
        self.pkg.write_bytes(buf.getvalue())

    def run_it(self, dry_run):
        self.inst.a.dry_run = dry_run
        self.assertTrue(self.inst.do_adix({"name": "InvCore"}, "x.log", str(self.pkg)))
        return Path(self.inst.logdir, "install.log").read_text()

    def test_unknown_root_files_are_listed(self):
        log = self.run_it(False)
        self.assertIn("1 files placed", log)
        self.assertIn("not installed (outside VFS, not package metadata): Extra/notes.txt, "
                      "SharedComponents.json, VFS/loose.txt", log)
        # the package's metadata is not listed
        self.assertNotIn("AppxManifest", log)
        self.assertTrue((self.prefix / "drive_c/Program Files/Autodesk/Inventor 2027/Bin/a.dll").exists())
        self.assertFalse((self.prefix / "drive_c/SharedComponents.json").exists())

    def test_dry_run_lists_them_too(self):
        log = self.run_it(True)
        self.assertIn("SharedComponents.json", log)
        self.assertFalse(self.prefix.exists() and any(self.prefix.rglob("a.dll")))


if __name__ == "__main__":
    unittest.main()
