"""An ADIX update takes the files of the old package version that the new
one no longer has out of their place, as Windows does (2027.2: DevExpress
v25.1, AutodeskAssistant, iLogic Codeblocks scripts) - into a backup under
.inventor-on-linux/removed-by-update, never a file another package still
lists. Synthetic packages."""
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

    def install(self, files, version, identity="Autodesk.InvCore", name="InvCore", display="Inventor Core 2027"):
        pkg = Path(self.tmp.name) / ("%s-%s.adix" % (name, version))
        pkg.write_bytes(adix(files, identity))
        s = {"name": name, "display": display, "version": version}
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
        self.assertIn("moved 2 files of Inventor Core 2027 31.0.19200.0 that this version no longer has (as Windows "
                      "does) to .inventor-on-linux/removed-by-update/Autodesk.InvCore-31.0.19200.0", self.log())
        removed = Path(self.inst.logdir, "31.20.33400.0-removed.txt").read_text()
        self.assertIn("DevExpress.Data.v25.1.dll", removed)
        # kept, with its path under drive_c, as the migrations' backups
        backup = self.prefix / ".inventor-on-linux/removed-by-update/Autodesk.InvCore-31.0.19200.0"
        self.assertEqual((backup / "Program Files/Autodesk/Inventor 2027/Bin/DevExpress.Data.v25.1.dll").read_bytes(),
                         b"x DevExpress.Data.v25.1.dll")
        self.assertTrue((backup / "Program Files/Autodesk/Inventor 2027/Bin/AutodeskAssistant/en-US/"
                                  "InvMcp.resources.dll").exists())

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
        self.assertNotIn("moved", self.log())

    def test_dry_run_only_says_it(self):
        self.install(["Inventor.exe", "Old.dll"], "1")
        self.inst.a.dry_run = True
        self.install(["Inventor.exe"], "2")
        self.assertTrue((self.bin / "Old.dll").exists())
        self.assertIn("would move 1 files", self.log())
        self.assertIn(r"C:\Program Files\Autodesk\Inventor 2027\Bin\Old.dll", self.log())
        self.assertFalse((self.prefix / ".inventor-on-linux/removed-by-update").exists())

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
        self.assertNotIn("moved", self.log())

    def test_an_edited_file_is_kept_in_the_backup(self):
        # iLogic Codeblocks scripts in ProgramData can be edited by users
        pd = "VFS/Common AppData/Autodesk/Inventor 2027/iLogic Codeblocks/"
        pkg = Path(self.tmp.name) / "v1.adix"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("AppxManifest.xml", '<Package><Identity Name="Autodesk.InvCore"/></Package>')
            z.writestr(pd + "1076.bundle.js", b"original")
        pkg.write_bytes(buf.getvalue())
        self.inst.do_adix({"name": "InvCore", "display": "Inventor Core 2027", "version": "1"}, "1.log", str(pkg))
        script = self.prefix / "drive_c/ProgramData/Autodesk/Inventor 2027/iLogic Codeblocks/1076.bundle.js"
        script.write_bytes(b"edited by the user")
        self.install(["Inventor.exe"], "2")
        self.assertFalse(script.exists())
        self.assertEqual((self.prefix / ".inventor-on-linux/removed-by-update/Autodesk.InvCore-1/ProgramData/"
                          "Autodesk/Inventor 2027/iLogic Codeblocks/1076.bundle.js").read_bytes(), b"edited by the user")

    def test_add_in_turned_off_by_the_prefix_setup_is_moved_too(self):
        self.install(["Inventor.exe", "Addins/Autodesk.Old.Inventor.addin", "Old.Crash.dll", "Tool.exe"], "1")
        inv = self.bin.parent
        (inv / "Addins.disabled/libs").mkdir(parents=True)
        (self.bin / "Addins/Autodesk.Old.Inventor.addin").rename(inv / "Addins.disabled/Autodesk.Old.Inventor.addin")
        (self.bin / "Old.Crash.dll").rename(inv / "Addins.disabled/libs/Old.Crash.dll")
        (self.bin / "Tool.exe").rename(self.bin / "Tool.exe.disabled")
        self.install(["Inventor.exe"], "2")
        for p in ("Addins.disabled/Autodesk.Old.Inventor.addin", "Addins.disabled/libs/Old.Crash.dll",
                  "Bin/Tool.exe.disabled"):
            self.assertFalse((inv / p).exists(), p)
            self.assertTrue((self.prefix / ".inventor-on-linux/removed-by-update/Autodesk.InvCore-1/Program Files/"
                             "Autodesk/Inventor 2027" / Path(p)).exists(), p)
        self.assertIn("moved 3 files", self.log())

    def test_a_file_that_cannot_be_moved_is_a_warning(self):
        self.install(["Inventor.exe", "A.dll", "B.dll", "C.dll"], "1")
        real_move = self.mod.shutil.move

        def move(src, dst):
            if src.endswith("B.dll"):
                raise PermissionError(13, "Permission denied")
            return real_move(src, dst)
        self.mod.shutil.move = move
        try:
            self.install(["Inventor.exe"], "2")
        finally:
            self.mod.shutil.move = real_move
        log = self.log()
        self.assertIn(r"WARN could not move C:\Program Files\Autodesk\Inventor 2027\Bin\B.dll to the backup", log)
        self.assertIn("moved 2 files", log)
        self.assertTrue((self.bin / "B.dll").exists())
        self.assertFalse((self.bin / "A.dll").exists())
        self.assertFalse((self.bin / "C.dll").exists())

    # Revit 2027.4: "Core Extension Package Component" and "Core-RVT
    # Package Component" both carry the identity Autodesk.Revit.Ext, have
    # the same version and go into the same folder.
    def test_packages_sharing_an_identity_keep_each_others_files(self):
        self.install(["Revit.exe", "RevitDB.dll"], "27.0.4.412", identity="Autodesk.Revit.Ext", name="RVTEXT",
                     display="Core Extension Package Component for Revit 2027")
        self.install(["RevitCore.dll"], "27.0.4.412", identity="Autodesk.Revit.Ext", name="RVTONLY",
                     display="Core-RVT Package Component for Revit 2027")
        for f in ("Revit.exe", "RevitDB.dll", "RevitCore.dll"):
            self.assertTrue((self.bin / f).exists(), f)
        self.assertNotIn("moved", self.log())
        records = self.inst.read_adix_records()
        self.assertIn("Autodesk.Revit.Ext", records)
        self.assertIn("Autodesk.Revit.Ext#RVTONLY", records)
        self.assertEqual(records["Autodesk.Revit.Ext#RVTONLY"]["files"],
                         ["C:\\Program Files\\Autodesk\\Inventor 2027\\Bin\\RevitCore.dll"])

    def test_an_update_of_one_of_them_removes_only_its_own_files(self):
        self.install(["Revit.exe", "RevitDB.dll"], "27.0.4.412", identity="Autodesk.Revit.Ext", name="RVTEXT")
        self.install(["RevitCore.dll", "Old.dll"], "27.0.4.412", identity="Autodesk.Revit.Ext", name="RVTONLY")
        self.install(["RevitCore.dll"], "27.0.5.100", identity="Autodesk.Revit.Ext", name="RVTONLY")
        self.assertFalse((self.bin / "Old.dll").exists())
        for f in ("Revit.exe", "RevitDB.dll", "RevitCore.dll"):
            self.assertTrue((self.bin / f).exists(), f)
        self.assertIn("moved 1 files", self.log())

    def test_a_list_from_before_names_were_kept_still_updates(self):
        self.install(["A.dll", "B.dll"], "1")
        rec = Path(self.inst.adix_record_path("Autodesk.InvCore"))
        data = rec.read_text().replace('"name": "InvCore",', "")
        rec.write_text(data)
        self.assertNotIn('"name"', rec.read_text())
        self.install(["A.dll"], "2")
        self.assertFalse((self.bin / "B.dll").exists())

    def nameless(self, identity):
        rec = Path(self.inst.adix_record_path(identity))
        rec.write_text(rec.read_text().replace('"name": ', '"was_name": '))

    def test_a_nameless_list_of_a_sibling_is_not_taken_by_another_version(self):
        # #43 review: RVTEXT's list from before names, RVTONLY of another version
        self.install(["Revit.exe", "RevitDB.dll"], "27.0.4.412", identity="Autodesk.Revit.Ext", name="RVTEXT",
                     display="Core Extension Package Component for Revit 2027")
        self.nameless("Autodesk.Revit.Ext")
        self.install(["RevitCore.dll"], "27.0.5.100", identity="Autodesk.Revit.Ext", name="RVTONLY",
                     display="Core-RVT Package Component for Revit 2027")
        for f in ("Revit.exe", "RevitDB.dll", "RevitCore.dll"):
            self.assertTrue((self.bin / f).exists(), f)
        self.assertNotIn("moved", self.log())

    def test_a_nameless_list_of_a_sibling_is_not_taken_on_the_already_installed_path(self):
        self.install(["Revit.exe", "RevitDB.dll"], "27.0.4.412", identity="Autodesk.Revit.Ext", name="RVTEXT",
                     display="Core Extension Package Component for Revit 2027")
        self.nameless("Autodesk.Revit.Ext")
        pkg = Path(self.tmp.name) / "image" / "x64/RVTONLY/RVTONLY.adix"
        pkg.parent.mkdir(parents=True)
        pkg.write_bytes(adix(["RevitCore.dll"], "Autodesk.Revit.Ext"))
        s = {"name": "RVTONLY", "display": "Core-RVT Package Component for Revit 2027", "version": "27.0.5.100",
             "type": "ADIX", "file": "x64/RVTONLY/RVTONLY.adix"}
        self.inst.record_installed_adix(s, self.mod.odis.Image(str(Path(self.tmp.name) / "image")))
        self.assertTrue((self.bin / "Revit.exe").exists())
        self.assertIn("Autodesk.Revit.Ext#RVTONLY", self.inst.read_adix_records())

    def test_suffixed_and_plain_keys_never_share_a_file(self):
        # #43 review: a package without AppxManifest is identified by its name
        self.install(["A.dll"], "1", identity="Autodesk.Revit.Ext", name="RVTEXT")
        self.install(["B.dll"], "1", identity="Autodesk.Revit.Ext", name="RVTONLY")
        self.install(["C.dll"], "1", identity=None, name="Autodesk.Revit.Ext_RVTONLY")
        records = self.inst.read_adix_records()
        self.assertEqual(sorted(records), ["Autodesk.Revit.Ext", "Autodesk.Revit.Ext#RVTONLY",
                                           "Autodesk.Revit.Ext_RVTONLY"])
        self.assertNotEqual(self.inst.adix_record_path("Autodesk.Revit.Ext#RVTONLY"),
                            self.inst.adix_record_path("Autodesk.Revit.Ext_RVTONLY"))

    def test_without_appx_manifest_the_name_identifies(self):
        self.install(["A.dll", "B.dll"], "1", identity=None, name="Pkg")
        self.install(["A.dll"], "2", identity=None, name="Pkg")
        self.assertFalse((self.bin / "B.dll").exists())


if __name__ == "__main__":
    unittest.main()
