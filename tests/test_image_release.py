"""Release detection for downloads and unpacked install images (issue #6).

Synthetic manifests only, in the ODIS namespace: no Autodesk files. The shell
checks stop at the unsupported-distribution check, before any package, Wine
or prefix work."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import odis  # noqa: E402

NS = "https://emsfs.autodesk.com/schema/manifest/1/0"


def manifest(path, display="", build="", packages=(), deps=(), tag="Package"):
    path.parent.mkdir(parents=True, exist_ok=True)
    pk = "".join('<Package name="p%d" path="%s"/>' % (i, p) for i, p in enumerate(packages))
    dp = "".join('<Package name="d%d" path="%s"/>' % (i, p) for i, p in enumerate(deps))
    path.write_text('<?xml version="1.0"?><%s xmlns="%s"><Identity><DisplayName>%s</DisplayName>'
                    '<BuildNumber>%s</BuildNumber></Identity>%s<Dependencies>%s</Dependencies></%s>'
                    % (tag, NS, display, build, pk, dp, tag))


def product_image(root, core_display, core_build, other=("RealDWG Shared 2027", "26.0.59.0")):
    manifest(root / "manifest" / "app.inventor.xml", packages=["x64/InvPro/manifest.xml"])
    manifest(root / "x64" / "InvPro" / "manifest.xml", "Inventor Pro", "",
             deps=["x64/InvCore/manifest.xml", "x64/RealDWG/manifest.xml", "x64/VC/manifest.xml"])
    manifest(root / "x64" / "InvCore" / "manifest.xml", core_display, core_build)
    manifest(root / "x64" / "RealDWG" / "manifest.xml", *other)
    manifest(root / "x64" / "VC" / "manifest.xml", "Microsoft Visual C++ 2015-2022", "14.50.35719.0")
    (root / "Setup.exe").write_bytes(b"")


class ImageRelease(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-release-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_unpacked_image_from_display_name(self):
        img = self.root / "Inventor"
        product_image(img, "Inventor Core 2027", "31.0.19200.0")
        self.assertEqual(odis.image_release(str(img)), "2027")
        self.assertEqual(odis.release_of(str(img)), "2027")

    def test_unpacked_image_from_build_number(self):
        img = self.root / "Inventor"
        product_image(img, "Inventor Core", "30.0.1.0")
        self.assertEqual(odis.release_of(str(img)), "2026")

    def test_folder_above_the_image(self):
        img = self.root / "Downloads" / "Inventor" / "image"
        product_image(img, "Inventor Core 2027", "31.0.19200.0")
        self.assertEqual(odis.release_of(str(self.root / "Downloads" / "Inventor")), "2027")

    def test_disagreeing_manifests_are_unknown(self):
        img = self.root / "Inventor"
        product_image(img, "Inventor Core 2027", "30.0.1.0")
        manifest(img / "x64" / "InvCore" / "manifest.xml", "Inventor Core 2026", "")
        manifest(img / "manifest" / "app.inventor.xml", "Autodesk Inventor Professional 2027",
                 packages=["x64/InvPro/manifest.xml"])
        self.assertIsNone(odis.release_of(str(img)))

    def test_other_products_do_not_count(self):
        img = self.root / "Inventor"
        product_image(img, "Inventor Core", "", other=("RealDWG Shared 2025", "25.0.1.0"))
        self.assertIsNone(odis.release_of(str(img)))

    def test_update_bundle(self):
        upd = self.root / "upd"
        manifest(upd / "setup.xml", "Inventor 2027.1 Update", "31.1.0.0", tag="Bundle")
        self.assertEqual(odis.release_of(str(upd)), "2027")

    def test_download_names(self):
        d = self.root / "dl"
        d.mkdir()
        for n in ("Inventor_Professional_2027_English_Win_64bit_db_001_002.exe",
                  "Inventor_Professional_2027_English_Win_64bit_db_002_002.7z"):
            (d / n).write_bytes(b"")
        self.assertEqual(odis.release_of(str(d)), "2027")
        self.assertEqual(odis.release_of(str(d / "Inventor_2027.1_Update.exe")), "2027")
        (d / "Inventor_Professional_2026_English_Win_64bit_db_002_002.7z").write_bytes(b"")
        self.assertIsNone(odis.release_of(str(d)))

    def env(self):
        home = self.root / "home"
        home.mkdir(exist_ok=True)
        env = {k: v for k, v in os.environ.items() if not k.startswith("INV_")}
        env.update(HOME=str(home), USER="tester", INV_DISTRO="unsupported", INV_GUI="1",
                   XDG_CACHE_HOME=str(self.root / "cache"))
        return env

    def test_install_sh_detects_unpacked_image(self):
        img = self.root / "Downloads" / "Inventor"
        product_image(img, "Inventor Core 2027", "31.0.19200.0")
        r = subprocess.run(["bash", str(ROOT / "scripts" / "install.sh"), "--skip-packages",
                            "--skip-wine", "--no-desktop", str(img)],
                           env=self.env(), text=True, capture_output=True, timeout=60)
        out = r.stdout + r.stderr
        self.assertIn("downloads are Inventor 2027", out)
        self.assertIn(".wine-inventor2027", out)
        # stops at phase 1 (as root: the sudo check, else the distribution check)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not with sudo" if os.geteuid() == 0 else "unsupported distribution", out)
        self.assertFalse((self.root / "home" / ".wine-inventor2026").exists())
        self.assertFalse((self.root / "home" / ".wine-inventor2027").exists())

    def test_finish_install_names_the_release_in_the_prefix(self):
        prefix = self.root / "home" / ".wine-inv"
        exe = prefix / "drive_c" / "Program Files" / "Autodesk" / "Inventor 2027" / "Bin" / "Inventor.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"")
        env = self.env() | {"INV_YEAR": "2026", "INV_PREFIX": str(prefix), "INV_FINISH_MAIN": "1"}
        r = subprocess.run(["bash", str(ROOT / "scripts" / "finish-install.sh")],
                           env=env, text=True, capture_output=True, timeout=60)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("holds Inventor 2027, not Inventor 2026", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
