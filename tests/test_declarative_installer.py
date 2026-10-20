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

    def test_licensing_without_standalone_sdk_has_no_dangling_link(self):
        from argparse import Namespace
        with tempfile.TemporaryDirectory() as directory:
            instance = installer.Installer(Namespace(image=directory, prefix=directory, lang="en-US"))
            base = Path(instance.c) / "Program Files (x86)/Common Files/Autodesk Shared/AdskLicensing"
            (base / "15.1.0.12339").mkdir(parents=True)
            (base / "CurrentSDK").symlink_to("15.1.0.12339/AdskLicensingSDK")
            with patch.object(instance, "log"):
                self.assertTrue(instance.finish_licensing())
            self.assertEqual(os.readlink(base / "Current"), "15.1.0.12339")
            self.assertFalse(os.path.lexists(base / "CurrentSDK"))

    def test_licensing_junction_recovery_retries_vendor_installer(self):
        from argparse import Namespace
        with tempfile.TemporaryDirectory() as directory:
            instance = installer.Installer(Namespace(image=directory, prefix=directory, lang="en-US"))
            base = Path(instance.c) / "Program Files (x86)/Common Files/Autodesk Shared/AdskLicensing"
            service = base / "15.1.0.12339/AdskLicensingService/AdskLicensingService.exe"
            service.parent.mkdir(parents=True)
            service.write_bytes(b"MZ")
            (base / "15.1.0.12339/AdskLicensingSDK").mkdir()
            log = Path(instance.c) / f"users/{installer.USER}/AppData/Local/Temp/AdskLicensing-install.log"
            log.parent.mkdir(parents=True)
            step = {"name": "AdskLicensing", "file": "setup.exe", "params": "--mode unattended"}
            with patch.object(instance, "log"), patch.object(instance, "run", side_effect=[250, 0]) as run:
                self.assertFalse(instance.do_exe(step, "licensing.log"))
                self.assertEqual(run.call_count, 1)
            log.write_text("Error code=LIC-INST-ERROR-250. Creating 'Current' link to version failed.")
            with patch.object(instance, "log"), patch.object(instance, "run", side_effect=[250, 0]) as run:
                self.assertTrue(instance.do_exe(step, "licensing.log"))
                self.assertEqual(run.call_count, 2)
                self.assertEqual(run.call_args_list[0].args[0], run.call_args_list[1].args[0])
            self.assertEqual(os.readlink(base / "Current"), "15.1.0.12339")
            self.assertEqual(os.readlink(base / "CurrentSDK"), "15.1.0.12339/AdskLicensingSDK")
            with patch.object(instance, "log"), patch.object(instance, "run", side_effect=[250, 7]) as run:
                self.assertFalse(instance.do_exe(step, "licensing.log"))
                self.assertEqual(run.call_count, 2)
            with patch.object(instance, "log"), patch.object(instance, "run", side_effect=[250, 63]):
                self.assertFalse(instance.do_exe(step, "licensing.log"))
            calls = []

            def vendor_retry(argv, logname):
                calls.append(argv)
                if len(calls) == 1:
                    return 250
                log.write_text("Error code=LIC-INST-ERROR-69009471. "
                               "Starting Windows service during installation-skip workflow failed: "
                               "Calling system API failed, (error code 1053)")
                return 63

            with patch.object(instance, "log"), patch.object(instance, "run", side_effect=vendor_retry):
                self.assertTrue(instance.do_exe(step, "licensing.log"))
            self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
