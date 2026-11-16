"""The image's applications are installed like ODIS does by default
(inventor, dclibrary, dwgtrueview, aceinvaddin), each can be left out; a
file another package already put into the prefix keeps the higher version,
whatever the package order (docs/installer-completeness-review.md,
"Needed" 5). Synthetic manifests and ADIX zips."""
import io
import os
import struct
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile
from pathlib import Path

import image_fixture as fx

APPS = {
    "inventor": ("Inventor 2027", [("InvCore", "x64/inv/pkg.invcore.xml", "")]),
    "dclibrary": ("Content Center 2027", [("DCLibrary", "x64/dc/pkg.dclibrary.xml", "")]),
    "dwgtrueview": ("DWG TrueView 2027", [("TrueView", "x64/tv/pkg.trueview.xml", "")]),
    "aceinvaddin": ("Electrical Catalog Browser 2027", [("AceInv", "x64/ace/pkg.aceinv.xml", "")]),
    "inventor.ui": ("Inventor 2027", []),
}


def pe(version, body=b""):
    """Bytes of a fake PE file with a VS_FIXEDFILEINFO of this version."""
    a, b, c, d = version
    return b"MZ" + b"\0" * 62 + body + b"\xbd\x04\xef\xfe" + struct.pack("<IIII", 0x10000, a << 16 | b, c << 16 | d, 0)


def adix(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


class DefaultApps(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-default-apps-")
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.image, self.prefix = t / "image", t / "prefix"
        for app, (display, pk) in APPS.items():
            fx.write(self.image, "manifest/app.%s.xml" % app, fx.app_xml(display, pk))
        for rel, display, f in (("x64/inv/pkg.invcore.xml", "Inventor Core 2027", "x64/inv/InvCore.msi"),
                                ("x64/dc/pkg.dclibrary.xml", "Content Center", "x64/dc/DCLibrary64.msi"),
                                ("x64/ace/pkg.aceinv.xml", "Electrical Catalog Browser", "x64/ace/ace.msi"),
                                ("3rdParty/net/pkg.dotnet48.xml", ".NET Framework Runtime 4.8", "3rdParty/net/ndp48.exe")):
            fx.write(self.image, rel, fx.package_xml(display, "EXE" if f.endswith(".exe") else "MSI", f))
            fx.write(self.image, f, b"")
        fx.write(self.image, "x64/tv/pkg.trueview.xml", fx.package_xml(
            "DWG TrueView 2027", "MSI", "x64/tv/dwgviewr.msi", deps=[("dotnet48", "3rdParty/net/pkg.dotnet48.xml")]))
        fx.write(self.image, "x64/tv/dwgviewr.msi", b"")
        self.prefix.mkdir()
        saved = os.environ.get("INV_LOGDIR")
        self.addCleanup(lambda: os.environ.pop("INV_LOGDIR", None) if saved is None
                        else os.environ.__setitem__("INV_LOGDIR", saved))

    def inst(self, **opts):
        return fx.installer(self.image, self.prefix, Path(self.tmp.name) / "logs", **opts)

    def log(self, inst):
        return Path(inst.logdir, "install.log").read_text()

    def test_every_application_like_odis(self):
        mod, inst = self.inst()
        apps, left = inst.choose_apps(mod.odis.Image(str(self.image)))
        self.assertEqual(apps, ["inventor", "dclibrary", "aceinvaddin", "dwgtrueview"])
        self.assertEqual(left, [("inventor.ui", "the setup's UI description, not an application")])

    def test_off_by_default_can_be_included(self):
        mod, inst = self.inst()
        with mock.patch.dict(inst.DEFAULT_OFF, {"aceinvaddin": "needs something"}):
            apps, left = inst.choose_apps(mod.odis.Image(str(self.image)))
            self.assertNotIn("aceinvaddin", apps)
            self.assertIn(("aceinvaddin", "off by default: needs something - install it with --include-app "
                                          "aceinvaddin"), left)
            inst.a.include_app = ["aceinvaddin"]
            apps, left = inst.choose_apps(mod.odis.Image(str(self.image)))
            self.assertIn("aceinvaddin", apps)

    def test_each_can_be_left_out(self):
        mod, inst = self.inst(no_app=["dwgtrueview", "AceInvAddin"], no_content=True)
        apps, left = inst.choose_apps(mod.odis.Image(str(self.image)))
        self.assertEqual(apps, ["inventor"])
        self.assertIn(("dwgtrueview", "left out (--no-app dwgtrueview)"), left)
        self.assertIn(("dclibrary", "left out (--no-content)"), left)

    def test_only_what_app_names(self):
        mod, inst = self.inst(app=["inventor"])
        apps, left = inst.choose_apps(mod.odis.Image(str(self.image)))
        self.assertEqual(apps, ["inventor"])
        self.assertIn(("dwgtrueview", "not asked for (--app)"), left)

    def test_unknown_app_is_said(self):
        mod, inst = self.inst(no_app=["nothing"])
        inst.choose_apps(mod.odis.Image(str(self.image)))
        self.assertIn("WARN   --no-app nothing: no manifest/app.nothing.xml in this image", self.log(inst))

    def test_dry_run_plans_them_and_leaves_dotnet48_to_its_own_step(self):
        mod, inst = self.inst()
        inst.main()
        log = self.log(inst)
        self.assertIn("apps   inventor, dclibrary, aceinvaddin, dwgtrueview", log)
        self.assertIn("skip   app inventor.ui: the setup's UI description, not an application", log)
        self.assertIn("skip   dotnet48: installed by the .NET Framework 4.8 step after the packages", log)
        for f in ("InvCore.msi", "DCLibrary64.msi", "ace.msi", "dwgviewr.msi"):
            self.assertIn(f, log)
        self.assertNotIn("ndp48.exe", log)
        # a dry run leaves the prefix alone: install.sh refuses a prefix
        # with drive_c that this installer did not finish setting up
        self.assertEqual(list(self.prefix.iterdir()), [])

    def test_install_sh_options(self):
        env = dict(os.environ, USER="test", HOME=self.tmp.name, XDG_CONFIG_HOME=self.tmp.name)
        out = subprocess.run(["bash", str(fx.ROOT / "scripts" / "install.sh"), "--help"],
                             capture_output=True, text=True, env=env).stdout
        self.assertIn("--no-trueview", out)
        self.assertIn("--no-electrical", out)
        text = (fx.ROOT / "scripts" / "install.sh").read_text()
        self.assertIn("--no-trueview) APP_OPTS+=(--no-app dwgtrueview)", text)
        self.assertIn("--no-electrical) APP_OPTS+=(--no-app aceinvaddin)", text)
        self.assertIn("--with-electrical) APP_OPTS+=(--include-app aceinvaddin)", text)


class SharedFiles(unittest.TestCase):
    """The seven DWG TrueView files in Common Files\\Autodesk Shared that
    another package already installs in a different build."""
    NAME = "VFS/ProgramFilesCommonX64/Autodesk Shared/AcInetEngine26.dll"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-shared-files-")
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        (t / "image").mkdir()
        self.prefix = t / "prefix"
        self.dst = self.prefix / "drive_c/Program Files/Common Files/Autodesk Shared/AcInetEngine26.dll"
        self.dst.parent.mkdir(parents=True)
        saved = os.environ.get("INV_LOGDIR")
        self.addCleanup(lambda: os.environ.pop("INV_LOGDIR", None) if saved is None
                        else os.environ.__setitem__("INV_LOGDIR", saved))
        self.mod, self.inst = fx.installer(t / "image", self.prefix, t / "logs", dry_run=False)
        self.pkg = t / "tv.adix"

    def install(self, data):
        self.pkg.write_bytes(adix({self.NAME: data, "AppxManifest.xml": b"<x/>"}))
        self.assertTrue(self.inst.do_adix({"name": "TrueView"}, "tv.log", str(self.pkg)))
        return Path(self.inst.logdir, "install.log").read_text()

    def test_newer_file_in_the_prefix_stays(self):
        self.dst.write_bytes(pe((26, 0, 60, 0)))
        log = self.install(pe((26, 0, 50, 0), b"older"))
        self.assertEqual(self.dst.read_bytes(), pe((26, 0, 60, 0)))
        self.assertIn("shared file Program Files/Common Files/Autodesk Shared/AcInetEngine26.dll: in the prefix "
                      "26.0.60.0", log)
        self.assertIn("kept the newer one in the prefix", log)

    def test_older_file_in_the_prefix_is_replaced(self):
        self.dst.write_bytes(pe((26, 0, 40, 0)))
        log = self.install(pe((26, 0, 50, 0)))
        self.assertEqual(self.dst.read_bytes(), pe((26, 0, 50, 0)))
        self.assertIn("replaced", log)

    def test_same_file_is_not_logged(self):
        self.dst.write_bytes(pe((26, 0, 50, 0)))
        log = self.install(pe((26, 0, 50, 0)))
        self.assertNotIn("shared file", log)

    def test_unversioned_file_is_replaced(self):
        self.dst.write_bytes(b"old type library")
        log = self.install(b"new type library")
        self.assertEqual(self.dst.read_bytes(), b"new type library")
        self.assertIn("no version", log)

    def test_dry_run_changes_nothing(self):
        self.dst.write_bytes(pe((26, 0, 40, 0)))
        self.inst.a.dry_run = True
        log = self.install(pe((26, 0, 50, 0)))
        self.assertEqual(self.dst.read_bytes(), pe((26, 0, 40, 0)))
        self.assertIn("replaced", log)
        self.assertIn("1 files to place (dry run)", log)

    def test_file_version(self):
        self.assertEqual(self.mod.pe_file_version(pe((31, 0, 0, 7))), (31, 0, 0, 7))
        self.assertIsNone(self.mod.pe_file_version(b"MZ no version"))
        self.assertIsNone(self.mod.pe_file_version(b"text"))


if __name__ == "__main__":
    unittest.main()


class CompareSizes(unittest.TestCase):
    """tools/compare-reference.py lists files both sides have in a different
    size - how the shared files are checked against Windows."""

    def test_different_size_is_listed(self):
        with tempfile.TemporaryDirectory(prefix="inventor-compare-") as d:
            d = Path(d)
            shared = d / "pfx/drive_c/Program Files/Common Files/Autodesk Shared"
            shared.mkdir(parents=True)
            (d / "cap/before").mkdir(parents=True)
            (d / "cap/after/logs").mkdir(parents=True)
            # Windows' own font, there before the install: no install difference
            (d / "cap/before/files.tsv").write_text("Path\tLength\tTime\nC:\\Windows\\Fonts\\tahoma.ttf\t9\tx\n")
            (d / "cap/after/files.tsv").write_text(
                "Path\tLength\tTime\n"
                "C:\\Program Files\\Common Files\\Autodesk Shared\\AcInetEngine26.dll\t100\tx\n"
                "C:\\Program Files\\Common Files\\Autodesk Shared\\Same.dll\t3\tx\n"
                "C:\\Windows\\Fonts\\AIGDT___.TTF\t7\tx\n"
                "C:\\Windows\\Fonts\\tahoma.ttf\t9\tx\n")
            (shared / "AcInetEngine26.dll").write_bytes(b"\0" * 90)
            (shared / "Same.dll").write_bytes(b"abc")
            fonts = d / "pfx/drive_c/windows/Fonts"
            fonts.mkdir(parents=True)
            (fonts / "AIGDT___.TTF").write_bytes(b"\0" * 5)
            (fonts / "tahoma.ttf").write_bytes(b"\0" * 2)
            subprocess.run(["python3", "-I", str(fx.ROOT / "tools/compare-reference.py"), str(d / "cap"),
                            str(d / "pfx"), "--details", str(d / "details.md")], capture_output=True, check=True)
            text = (d / "details.md").read_text()
            self.assertIn("AcInetEngine26.dll (Windows 100, prefix 90 bytes)", text)
            self.assertNotIn("Same.dll (Windows", text)
            self.assertIn("AIGDT___.TTF (Windows 7, prefix 5 bytes)", text)
            self.assertNotIn("tahoma", text.split("## 3a")[1].split("## 3b")[0])
