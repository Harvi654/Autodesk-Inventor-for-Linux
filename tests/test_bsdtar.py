"""tar.exe for the prefix: libarchive's signed Windows build of bsdtar
(scripts/lib/bsdtar.env), put into system32 (and syswow64) by
install-from-image.py before the packages, with its license text.
A synthetic zip stands in for libarchive's; no network."""
import hashlib
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import image_fixture as fx

FAKE = b"MZ fake bsdtar.exe"


class Bsdtar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-bsdtar-")
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        (t / "image").mkdir()
        self.prefix = t / "prefix"
        for d in ("system32", "syswow64"):
            (self.prefix / "drive_c/windows" / d).mkdir(parents=True)
        self.dl = t / "downloads"
        self.dl.mkdir()
        with zipfile.ZipFile(self.dl / "libarchive-test-win64.zip", "w") as z:
            z.writestr("libarchive/bin/bsdtar.exe", FAKE)
            z.writestr("libarchive/bin/archive.dll", b"MZ dll")
        self.env_file = t / "bsdtar.env"
        self.write_env(hashlib.sha256((self.dl / "libarchive-test-win64.zip").read_bytes()).hexdigest())
        patcher = mock.patch.dict(os.environ, {"INV_BSDTAR_ENV": str(self.env_file), "DOWNLOAD_DIR": str(self.dl)})
        patcher.start()
        self.addCleanup(patcher.stop)
        saved = os.environ.get("INV_LOGDIR")
        self.addCleanup(lambda: os.environ.pop("INV_LOGDIR", None) if saved is None
                        else os.environ.__setitem__("INV_LOGDIR", saved))
        self.mod, self.inst = fx.installer(t / "image", self.prefix, t / "logs", dry_run=False)

    def write_env(self, zip_sha):
        self.env_file.write_text(
            "# test\nBSDTAR_VER=3.5.3\nBSDTAR_ZIP=libarchive-test-win64.zip\nBSDTAR_URL=http://127.0.0.1:9/none\n"
            "BSDTAR_SHA256=%s\nBSDTAR_MEMBER=libarchive/bin/bsdtar.exe\nBSDTAR_EXE_SHA256=%s\n"
            % (zip_sha, hashlib.sha256(FAKE).hexdigest()))

    def log(self):
        return Path(self.inst.logdir, "install.log").read_text()

    def test_tar_exe_in_system32_and_syswow64_with_license(self):
        self.assertTrue(self.inst.install_bsdtar())
        for d in ("system32", "syswow64"):
            self.assertEqual((self.prefix / "drive_c/windows" / d / "tar.exe").read_bytes(), FAKE)
        self.assertFalse((self.prefix / "drive_c/windows/system32/archive.dll").exists())
        self.assertIn("Tim Kientzle", (self.prefix / ".inventor-on-linux/doc/libarchive-3.5.3/COPYING").read_text())
        self.assertIn("sha256 verified", self.log())
        # the second time: nothing to do
        self.assertTrue(self.inst.install_bsdtar())
        self.assertIn("already in the prefix", self.log())

    def test_checksum_mismatch_is_refused_and_the_file_deleted(self):
        self.write_env("0" * 64)
        self.assertFalse(self.inst.install_bsdtar())
        self.assertIn("checksum mismatch (file deleted)", self.log())
        self.assertFalse((self.dl / "libarchive-test-win64.zip").exists())
        self.assertFalse((self.prefix / "drive_c/windows/system32/tar.exe").exists())

    def test_another_tar_exe_is_replaced(self):
        (self.prefix / "drive_c/windows/system32/tar.exe").write_bytes(b"MZ something else")
        self.assertTrue(self.inst.install_bsdtar())
        self.assertEqual((self.prefix / "drive_c/windows/system32/tar.exe").read_bytes(), FAKE)

    def test_dry_run_changes_nothing(self):
        self.inst.a.dry_run = True
        self.assertTrue(self.inst.install_bsdtar())
        self.assertFalse((self.prefix / "drive_c/windows/system32/tar.exe").exists())
        self.assertIn(r"tar.exe: bsdtar 3.5.3 (libarchive-test-win64.zip", self.log())


class PinnedValues(unittest.TestCase):
    def test_bsdtar_env(self):
        cfg = fx.load_installer().read_env_file(fx.ROOT / "scripts/lib/bsdtar.env")
        self.assertEqual(cfg["BSDTAR_VER"], "3.5.3")
        self.assertEqual(cfg["BSDTAR_URL"], "https://github.com/libarchive/libarchive/releases/download/v3.5.3/"
                                            + cfg["BSDTAR_ZIP"])
        for k in ("BSDTAR_SHA256", "BSDTAR_EXE_SHA256"):
            self.assertRegex(cfg[k], r"^[0-9a-f]{64}$")
        self.assertTrue((fx.ROOT / ("scripts/lib/licenses/libarchive-%s-COPYING" % cfg["BSDTAR_VER"])).is_file())
        # the Nix build fetches the same file with the same hash
        nix = (fx.ROOT / "nix/inventor.nix").read_text()
        self.assertIn(cfg["BSDTAR_URL"], nix)
        self.assertIn(cfg["BSDTAR_SHA256"], nix)
        self.assertIn('"$DOWNLOAD_DIR/%s"' % cfg["BSDTAR_ZIP"], nix)


if __name__ == "__main__":
    unittest.main()
