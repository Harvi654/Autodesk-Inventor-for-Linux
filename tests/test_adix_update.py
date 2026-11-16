"""An ADIX update removes the files of the old package version that the new
one no longer has, as Windows does (2027.2: DevExpress v25.1,
AutodeskAssistant, iLogic Codeblocks scripts), never a file another
package still lists. Synthetic packages."""
import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

import image_fixture as fx

INV = "VFS/ProgramFilesX64/Autodesk/Inventor 2027/Bin/"


def adix(files, identity="Autodesk.InvCore"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        if identity:
            z.writestr("AppxManifest.xml", '<Package><Identity Name="%s" Version="31.0.0.0"/></Package>' % identity)
        for f in files:
            z.writestr(INV + f, b"x " + f.encode())
    return buf.getvalue()


class AdixUpdate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-adix-update-")
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        (t / "image").mkdir()
        self.prefix = t / "prefix"
        saved = os.environ.get("INV_LOGDIR")
        self.addCleanup(lambda: os.environ.pop("INV_LOGDIR", None) if saved is None
                        else os.environ.__setitem__("INV_LOGDIR", saved))
        self.mod, self.inst = fx.installer(t / "image", self.prefix, t / "logs", dry_run=False)
        self.bin = self.prefix / "drive_c/Program Files/Autodesk/Inventor 2027/Bin"

    def install(self, files, version, identity="Autodesk.InvCore", name="InvCore"):
        pkg = Path(self.tmp.name) / ("%s-%s.adix" % (name, version))
        pkg.write_bytes(adix(files, identity))
        s = {"name": name, "display": "Inventor Core 2027", "version": version}
        self.assertTrue(self.inst.do_adix(s, "%s.log" % version, str(pkg)))
        return pkg, s

    def log(self):
        return Path(self.inst.logdir, "install.log").read_text()

    def test_files_the_new_version_drops_are_removed(self):
        self.install(["Inventor.exe", "DevExpress.Data.v25.1.dll", "AutodeskAssistant/en-US/InvMcp.resources.dll"],
                     "31.0.19200.0")
        self.install(["Inventor.exe", "DevExpress.Data.v25.2.dll"], "31.20.33400.0")
        self.assertTrue((self.bin / "Inventor.exe").exists())
        self.assertTrue((self.bin / "DevExpress.Data.v25.2.dll").exists())
        self.assertFalse((self.bin / "DevExpress.Data.v25.1.dll").exists())
        self.assertFalse((self.bin / "AutodeskAssistant").exists())        # emptied folders go too
        self.assertIn("removed 2 files of Inventor Core 2027 31.0.19200.0 that this version no longer has", self.log())
        removed = Path(self.inst.logdir, "31.20.33400.0-removed.txt").read_text()
        self.assertIn("DevExpress.Data.v25.1.dll", removed)

    def test_own_files_of_the_old_version_are_replaced_silently(self):
        self.install(["Inventor.exe"], "1")
        (self.bin / "Inventor.exe").write_bytes(b"MZ older build")   # differs from version 2's copy
        self.install(["Inventor.exe"], "2")
        self.assertNotIn("shared file", self.log())
        self.assertEqual((self.bin / "Inventor.exe").read_bytes(), b"x Inventor.exe")

    def test_a_file_another_package_lists_stays(self):
        self.install(["Inventor.exe", "Shared.dll"], "1")
        self.install(["Shared.dll"], "1", identity="Autodesk.Other", name="Other")
        self.install(["Inventor.exe"], "2")
        self.assertTrue((self.bin / "Shared.dll").exists())
        self.assertNotIn("removed", self.log())

    def test_dry_run_only_says_it(self):
        self.install(["Inventor.exe", "Old.dll"], "1")
        self.inst.a.dry_run = True
        self.install(["Inventor.exe"], "2")
        self.assertTrue((self.bin / "Old.dll").exists())
        self.assertIn("would remove 1 files", self.log())

    def test_package_installed_before_file_lists(self):
        # placed by an older installer: no list; the base image's step is
        # "already done" - its list is recorded from the package, unpacked never
        pkg = Path(self.tmp.name) / "image" / "x64/InvCore/InvCore.adix"
        pkg.parent.mkdir(parents=True)
        pkg.write_bytes(adix(["Inventor.exe", "Old.dll"]))
        for f in ("Inventor.exe", "Old.dll"):
            (self.bin / f).parent.mkdir(parents=True, exist_ok=True)
            (self.bin / f).write_bytes(b"old")
        s = {"name": "InvCore", "display": "Inventor Core 2027", "version": "1", "type": "ADIX",
             "file": "x64/InvCore/InvCore.adix"}
        self.inst.record_installed_adix(s, self.mod.odis.Image(str(Path(self.tmp.name) / "image")))
        self.assertTrue((self.prefix / ".inventor-on-linux/adix/Autodesk.InvCore.json").exists())
        self.assertEqual((self.bin / "Old.dll").read_bytes(), b"old")     # nothing unpacked
        self.install(["Inventor.exe"], "2")
        self.assertFalse((self.bin / "Old.dll").exists())

    def already_done(self, files, version, rel):
        pkg = Path(self.tmp.name) / "image" / rel
        pkg.parent.mkdir(parents=True, exist_ok=True)
        pkg.write_bytes(adix(files))
        s = {"name": "InvCore", "display": "Inventor Core 2027", "version": version, "type": "ADIX", "file": rel}
        self.inst.record_installed_adix(s, self.mod.odis.Image(str(Path(self.tmp.name) / "image")))

    def test_update_from_before_the_lists_cleaned_by_a_repair_run(self):
        # base and 2027.2 both installed by an older installer; install.sh BASE UPDATE again
        for f in ("Inventor.exe", "DevExpress.Data.v25.1.dll", "DevExpress.Data.v25.2.dll"):
            (self.bin / f).parent.mkdir(parents=True, exist_ok=True)
            (self.bin / f).write_bytes(b"x")
        self.already_done(["Inventor.exe", "DevExpress.Data.v25.1.dll"], "31.0.19200.0", "base/InvCore.adix")
        self.already_done(["Inventor.exe", "DevExpress.Data.v25.2.dll"], "31.20.33400.0", "upd/InvCore.adix")
        self.assertFalse((self.bin / "DevExpress.Data.v25.1.dll").exists())
        self.assertTrue((self.bin / "DevExpress.Data.v25.2.dll").exists())

    def test_base_run_again_on_an_updated_prefix_removes_nothing(self):
        self.install(["Inventor.exe", "DevExpress.Data.v25.2.dll"], "31.20.33400.0")
        self.already_done(["Inventor.exe", "DevExpress.Data.v25.1.dll"], "31.0.19200.0", "base/InvCore.adix")
        self.assertTrue((self.bin / "DevExpress.Data.v25.2.dll").exists())
        self.assertNotIn("removed", self.log())

    def test_without_appx_manifest_the_name_identifies(self):
        self.install(["A.dll", "B.dll"], "1", identity=None, name="Pkg")
        self.install(["A.dll"], "2", identity=None, name="Pkg")
        self.assertFalse((self.bin / "B.dll").exists())


if __name__ == "__main__":
    unittest.main()
