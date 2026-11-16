"""ADIX packages: ODIS's InstallPathMappings apply to files too. The
Electrical Catalog Browser's VFS puts its files under Program
Files\\Autodesk\\AutoCAD 2027; mapped to %INV_INSTALL_PATH% they belong in
Inventor's folder (run 3 found them in an "AutoCAD 2027" folder).
Synthetic package, manifest and .admeta."""
import io
import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

import image_fixture as fx

NAME = "VFS/ProgramFilesX64/Autodesk/AutoCAD 2027/Bin/InventorElectrical/AceInvAddIn.dll"
MAP = {r"[{ProgramFilesX64}]\Autodesk\AutoCAD 2027": "%INV_INSTALL_PATH%",
       "[{AppVPackageRoot}]": "%NOT_A_FOLDER%"}


def adix():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(NAME, b"MZ ace")
        z.writestr("VFS/ProgramFilesX64/Autodesk/Other/keep.txt", b"x")
        z.writestr("AppxManifest.xml", b"<x/>")
    return buf.getvalue()


class InstallerMapping(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-path-map-")
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        (t / "image").mkdir()
        self.prefix = t / "prefix"
        saved = os.environ.get("INV_LOGDIR")
        self.addCleanup(lambda: os.environ.pop("INV_LOGDIR", None) if saved is None
                        else os.environ.__setitem__("INV_LOGDIR", saved))
        self.mod, self.inst = fx.installer(t / "image", self.prefix, t / "logs", dry_run=False)
        self.inst.vars["inv_install_path"] = "C:\\Program Files\\Autodesk\\Inventor 2027\\"
        self.pkg = t / "AceInvAddIn.adix"
        self.pkg.write_bytes(adix())

    def test_files_go_where_the_mapping_says(self):
        self.assertTrue(self.inst.do_adix({"name": "ACEINVADDIN", "pathMappings": MAP}, "x.log", str(self.pkg)))
        c = self.prefix / "drive_c/Program Files/Autodesk"
        self.assertTrue((c / "Inventor 2027/Bin/InventorElectrical/AceInvAddIn.dll").exists())
        self.assertFalse((c / "AutoCAD 2027").exists())
        self.assertTrue((c / "Other/keep.txt").exists())
        log = Path(self.inst.logdir, "install.log").read_text()
        self.assertIn("path mapping [{ProgramFilesX64}]\\Autodesk\\AutoCAD 2027 -> "
                      "C:\\Program Files\\Autodesk\\Inventor 2027: 1 files", log)
        self.assertIn("WARN path mapping [{AppVPackageRoot}] -> %NOT_A_FOLDER% not understood", log)

    def test_common_documents_with_public(self):
        m = self.mod.odis.PathMapper({"[{Common Documents}]\\": "%PUBLIC%\\Documents\\"},
                                     lambda v: self.inst.expand(v))
        self.assertEqual(m.unread, [])
        self.assertEqual(m.map(r"C:\users\Public\Documents\Autodesk\x.txt"),
                         r"C:\users\Public\Documents\Autodesk\x.txt")

    def test_without_mappings_as_before(self):
        self.inst.do_adix({"name": "X"}, "x.log", str(self.pkg))
        self.assertTrue((self.prefix / "drive_c/Program Files/Autodesk/AutoCAD 2027/Bin/InventorElectrical/"
                         "AceInvAddIn.dll").exists())


class AdmetaCheckMapping(unittest.TestCase):
    def test_mapped_files_are_found(self):
        with tempfile.TemporaryDirectory(prefix="inventor-admeta-map-") as d:
            d = Path(d)
            img, pfx = d / "image", d / "prefix"
            fx.write(img, "setup.xml", '<Setup><Properties><Property property="INV_INSTALL_PATH" '
                                       'defaultValue="%INSTALL_DEST%\\Inventor 2027\\"/></Properties></Setup>')
            fx.write(img, "x64/ace/AceInvAddIn.adix", adix())
            fx.write(img, "x64/ace/AceInvAddIn.admeta", json.dumps({"files": [{"path": NAME.replace("/", "\\")}]}))
            maps = "".join('<InstallPathMapping source="%s" target="%s"/>' % kv for kv in MAP.items())
            # as in the 2027.2 update: the manifest in another folder
            fx.write(img, "manifest/x64/ace/pkg.aceinvaddin.xml",
                     '<Package xmlns="%s"><Configuration><InstallFile type="ADIX" file="x64/ace/AceInvAddIn.adix"/>'
                     '<AdditionalPackageInfo><Customizations><InstallPathMappings>%s</InstallPathMappings>'
                     '</Customizations></AdditionalPackageInfo></Configuration></Package>' % (fx.NS, maps))
            fx.write(pfx, "drive_c/Program Files/Autodesk/Inventor 2027/Bin/InventorElectrical/AceInvAddIn.dll",
                     b"MZ ace")
            (pfx / "drive_c/users/user").mkdir(parents=True)
            out = subprocess.run(["python3", "-I", str(fx.ROOT / "tools/admeta-check.py"), str(img), str(pfx)],
                                 capture_output=True, text=True, check=True).stdout
            self.assertIn("total 1: same 1", out)


if __name__ == "__main__":
    unittest.main()
