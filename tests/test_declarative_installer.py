"""Check the boundary between a personal prefix and an explicitly prepared build prefix."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "installer", Path(__file__).resolve().parents[1] / "scripts/install-from-image.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class PreparedPrefixTests(unittest.TestCase):
    def run_installer(self, extra, *, initialized=False):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / "prefix"
            (prefix / "drive_c").mkdir(parents=True)
            if initialized:
                (prefix / ".odis-install-state.json").write_text("{}")
            with patch.object(installer.odis, "image_kind", return_value="product"), \
                    patch.object(installer.Installer, "main") as install, \
                    patch("sys.argv", ["installer", directory, "--prefix", str(prefix), *extra]):
                installer.main()
                install.assert_called_once()

    def test_unknown_prefix_is_rejected_by_default(self):
        with self.assertRaisesRegex(SystemExit, "refusing to install"):
            self.run_installer([])

    def test_explicit_prepared_prefix_is_accepted(self):
        self.run_installer(["--prepared-prefix"])

    def test_existing_installer_prefix_can_resume(self):
        self.run_installer([], initialized=True)

    def test_logs_can_be_outside_read_only_sources(self):
        from argparse import Namespace
        with patch.dict(os.environ, {"INV_LOGDIR": "/tmp/inventor-build-logs"}):
            instance = installer.Installer(Namespace(image="/tmp/media", prefix="/tmp/prefix", lang="en-US"))
        self.assertEqual(Path(instance.logdir).parent, Path("/tmp/inventor-build-logs"))

    def test_preinstalled_webview2_requires_an_actual_executable(self):
        from argparse import Namespace
        with tempfile.TemporaryDirectory() as directory:
            instance = installer.Installer(Namespace(image=directory, prefix=directory,
                                                    lang="en-US", preinstalled_webview2=True))
            with self.assertRaisesRegex(RuntimeError, "requires msedgewebview2.exe"):
                instance.use_preinstalled_webview2({"name": "WebView2"})
            executable = Path(instance.c) / "Program Files (x86)/Microsoft/EdgeWebView/Application/154.0.4258.62/msedgewebview2.exe"
            executable.mkdir(parents=True)
            with self.assertRaises(RuntimeError):
                instance.use_preinstalled_webview2({"name": "WebView2"})
            executable.rmdir()
            executable.write_bytes(b"MZ")
            with patch.object(instance, "log"):
                self.assertTrue(instance.use_preinstalled_webview2({"name": "WebView2"}))
            self.assertFalse(instance.use_preinstalled_webview2({"name": "AdskLicensing"}))
            instance.a.preinstalled_webview2 = False
            self.assertFalse(instance.use_preinstalled_webview2({"name": "WebView2"}))


if __name__ == "__main__":
    unittest.main()
