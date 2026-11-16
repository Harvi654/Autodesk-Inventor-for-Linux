"""install-from-image.py runs Inventor's own registration (Inventor.exe
/install 0) once after the product's packages, with winemenubuilder off,
and stops the prefix afterwards (docs/installer-completeness-review.md,
"Needed" 1). Fake wine and wineserver; no real Wine is started."""
import argparse
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The fake Inventor.exe writes the two keys the way Wine stores them in
# user.reg (unless NO_KEYS is set); wineserver calls are recorded.
FAKE_WINE = r"""#!/bin/bash
echo "wine $* | WINEDLLOVERRIDES=${WINEDLLOVERRIDES:-}" >> "$WINEPREFIX/calls.log"
case "$1" in
    *'\Bin\Inventor.exe')
        [ -n "${NO_KEYS:-}" ] && exit 1
        printf '[Software\\\\Classes\\\\Inventor.Application] 1700000000\n@="Inventor Application"\n' >> "$WINEPREFIX/user.reg"
        printf '[Software\\\\Classes\\\\Inventor.PartDocument\\\\CLSID] 1700000000\n@="{X}"\n' >> "$WINEPREFIX/user.reg" ;;
esac
exit 0
"""
FAKE_WINESERVER = """#!/bin/sh
echo "wineserver $*" >> "$WINEPREFIX/calls.log"
"""


def load_installer():
    spec = importlib.util.spec_from_file_location("install_from_image", ROOT / "scripts" / "install-from-image.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class InventorRegistration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-registration-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.prefix = root / "prefix"
        (self.prefix / "drive_c/Program Files/Autodesk/Inventor 2027/Bin").mkdir(parents=True)
        (self.prefix / "drive_c/Program Files/Autodesk/Inventor 2027/Bin/Inventor.exe").write_bytes(b"MZ")
        (self.prefix / "user.reg").write_text("WINE REGISTRY Version 2\n")
        b = root / "bin"
        b.mkdir()
        for name, text in (("wine", FAKE_WINE), ("wineserver", FAKE_WINESERVER)):
            (b / name).write_text(text)
            (b / name).chmod(0o755)
        self.mod = load_installer()
        saved = {k: os.environ.get(k) for k in ("INV_LOGDIR", "WINEDLLOVERRIDES", "XDG_DATA_HOME")}
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in saved.items()])
        os.environ["INV_LOGDIR"] = str(root / "logs")
        os.environ["XDG_DATA_HOME"] = str(root / "share")
        os.environ.pop("WINEDLLOVERRIDES", None)
        self.bin = b

    def installer(self, dry_run=False, redo=False, **env):
        a = argparse.Namespace(image=str(Path(self.tmp.name) / "image"), prefix=str(self.prefix), lang="en-US",
                               dry_run=dry_run, redo=redo)
        inst = self.mod.Installer(a)
        inst.env["PATH"] = "%s:%s" % (self.bin, os.environ.get("PATH", "/usr/bin:/bin"))
        inst.env.update(env)
        return inst

    def calls(self):
        p = self.prefix / "calls.log"
        return p.read_text().splitlines() if p.exists() else []

    def log(self, inst):
        return Path(inst.logdir, "install.log").read_text()

    def test_registration_runs_with_winemenubuilder_off_then_stops_the_prefix(self):
        inst = self.installer()
        self.assertTrue(inst.register_inventor())
        calls = self.calls()
        reg = [c for c in calls if "Inventor.exe" in c]
        self.assertEqual(len(reg), 1)
        self.assertIn(r"wine C:\Program Files\Autodesk\Inventor 2027\Bin\Inventor.exe /install 0", reg[0])
        self.assertIn("winemenubuilder.exe=d", reg[0])
        # wineserver -k after it (its helper processes keep the server alive)
        self.assertEqual(calls[calls.index(reg[0]) + 1], "wineserver -k")
        self.assertIn("registration:inventor", json.loads((self.prefix / ".odis-install-state.json").read_text()))
        self.assertIn("registered: Inventor.Application, Inventor.PartDocument", self.log(inst))

    def test_done_once(self):
        self.assertTrue(self.installer().register_inventor())
        inst = self.installer()
        self.assertTrue(inst.register_inventor())
        self.assertEqual(len([c for c in self.calls() if "Inventor.exe" in c]), 1)
        self.assertIn("already done", self.log(inst))

    def test_existing_overrides_are_kept(self):
        os.environ["WINEDLLOVERRIDES"] = "mscoree=n"
        self.assertEqual(self.installer().env["WINEDLLOVERRIDES"], "mscoree=n;winemenubuilder.exe=d")
        os.environ["WINEDLLOVERRIDES"] = "winemenubuilder.exe=d;mscoree=n"
        self.assertEqual(self.installer().env["WINEDLLOVERRIDES"], "winemenubuilder.exe=d;mscoree=n")

    def test_missing_keys_warn_and_are_not_marked_done(self):
        inst = self.installer(NO_KEYS="1")
        self.assertFalse(inst.register_inventor())
        log = self.log(inst)
        self.assertIn("WARN Inventor registration incomplete (exit code 1)", log)
        self.assertIn(r"Software\Classes\Inventor.Application", log)
        self.assertIn("--run 0005", log)
        self.assertFalse((self.prefix / ".odis-install-state.json").exists())
        self.assertIn("wineserver -k", self.calls())

    def test_dry_run_prints_the_command_only(self):
        inst = self.installer(dry_run=True)
        self.assertTrue(inst.register_inventor())
        self.assertEqual(self.calls(), [])
        self.assertIn(r"Inventor 2027\Bin\Inventor.exe /install 0 (winemenubuilder off), then wineserver -k",
                      self.log(inst))

    def test_new_menu_entries_are_reported(self):
        apps = Path(self.tmp.name) / "share" / "applications"
        apps.mkdir(parents=True)
        (apps / "wine-extension-old.desktop").write_text("")
        inst = self.installer()
        orig = inst.run

        def run(argv, logname, timeout=None):
            (apps / "wine-extension-ipt.desktop").write_text("")
            return orig(argv, logname, timeout)
        inst.run = run
        inst.register_inventor()
        log = self.log(inst)
        self.assertIn("new Linux menu entries", log)
        self.assertIn("wine-extension-ipt.desktop", log)
        self.assertNotIn("wine-extension-old.desktop", log)


class WineRegReader(unittest.TestCase):
    def test_keys_and_values(self):
        with tempfile.NamedTemporaryFile("w", suffix=".reg", delete=False) as f:
            f.write('WINE REGISTRY Version 2\n;; All keys relative to \\\\Machine\n\n'
                    '[Software\\\\Autodesk\\\\Inventor\\\\RegistryVersion31.0] 1700000000\n'
                    '#time=1db\n"InventorLocation"="C:\\\\Program Files\\\\Autodesk\\\\Inventor 2027\\\\"\n'
                    '"Expand"=str(2):"%ProgramFiles%\\\\X"\n"Count"=dword:00000001\n@="default"\n\n'
                    '[Software\\\\Classes\\\\Only\\\\Sub] 1\n')
        self.addCleanup(os.remove, f.name)
        r = load_installer().WineReg(f.name)
        k = r"SOFTWARE\Autodesk\Inventor\RegistryVersion31.0"
        self.assertEqual(r.value(k, "inventorlocation"), "C:\\Program Files\\Autodesk\\Inventor 2027\\")
        self.assertEqual(r.value(k, "Expand"), "%ProgramFiles%\\X")
        self.assertIsNone(r.value(k, "Count"))
        self.assertEqual(r.value(k, ""), "default")
        self.assertIsNone(r.value(k, "Missing"))
        self.assertTrue(r.has_key(r"Software\Classes\Only"))
        self.assertFalse(r.has_key(r"Software\Classes\On"))
        self.assertFalse(load_installer().WineReg("/nonexistent").has_key("Software"))


if __name__ == "__main__":
    unittest.main()
