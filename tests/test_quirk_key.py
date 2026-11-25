"""The licensing-service quirk is found by installer, not by package name."""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location("install_from_image", ROOT / "scripts" / "install-from-image.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class QuirkKey(unittest.TestCase):
    def setUp(self):
        self.m = load()

    def test_inventor_package_name(self):
        s = {"name": "AdskLicensing", "file": "x86/Licensing/AdskLicensing-installer.exe"}
        self.assertEqual(self.m.quirk_key(s), "adsklicensing")

    def test_autocad_package_name(self):
        # AutoCAD 2027 ships the same installer under another package name
        s = {"name": "Licensing", "file": "x86/Licensing/AdskLicensing-installer.exe"}
        self.assertEqual(self.m.quirk_key(s), "adsklicensing")
        self.assertIn(self.m.quirk_key(s), self.m.QUIRKS)

    def test_other_package(self):
        s = {"name": "WebView2", "file": "3rdParty/x64/WebView2/MicrosoftEdgeWebView2RuntimeInstallerX64.exe"}
        self.assertEqual(self.m.quirk_key(s), "webview2")

    def test_step_without_file(self):
        self.assertEqual(self.m.quirk_key({"name": "Foo"}), "foo")


if __name__ == "__main__":
    unittest.main()
