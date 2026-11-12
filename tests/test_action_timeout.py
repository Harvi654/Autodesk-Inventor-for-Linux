"""install-from-image.py: an image's pre/postInstall helper that never exits
is stopped after ACTION_TIMEOUT instead of hanging the install (fake wine)."""
import argparse
import importlib.util
import os
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# "wine taskkill ..." is recorded and returns; anything else hangs (60 s,
# far longer than the 1 s timeout the tests use).
HANGING_WINE = """#!/bin/sh
echo "$*" >> "$WINEPREFIX/calls.log"
if [ "$1" = taskkill ]; then exit 0; fi
exec sleep 60
"""


def load_installer():
    spec = importlib.util.spec_from_file_location("install_from_image", ROOT / "scripts" / "install-from-image.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ActionTimeout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-action-timeout-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.prefix = root / "prefix"
        self.prefix.mkdir()
        b = root / "bin"
        b.mkdir()
        (b / "wine").write_text(HANGING_WINE)
        (b / "wine").chmod(0o755)
        self.mod = load_installer()
        old = os.environ.get("INV_LOGDIR")
        os.environ["INV_LOGDIR"] = str(root / "logs")
        self.addCleanup(lambda: os.environ.__setitem__("INV_LOGDIR", old) if old is not None
                        else os.environ.pop("INV_LOGDIR", None))
        a = argparse.Namespace(image=str(root / "image"), prefix=str(self.prefix), lang="en-US",
                               dry_run=False, no_dotnet48=True)
        self.inst = self.mod.Installer(a)
        self.inst.env["PATH"] = "%s:%s" % (b, os.environ.get("PATH", "/usr/bin:/bin"))

    def calls(self):
        p = self.prefix / "calls.log"
        return p.read_text() if p.exists() else ""

    def test_hanging_helper_is_stopped(self):
        t0 = time.monotonic()
        rc = self.inst.run(["wine", r"C:\Program Files\Helper\hang.exe", "CreateEventLog"], "action.log", timeout=1)
        self.assertLess(time.monotonic() - t0, 30)
        self.assertEqual(rc, -1)
        self.assertIn("taskkill /f /im hang.exe", self.calls())
        log = Path(self.inst.logdir, "install.log").read_text()
        self.assertIn("no exit after 1s", log)

    def test_actions_get_the_timeout(self):
        seen = []
        self.inst.run = lambda argv, logname, timeout=None: seen.append(timeout) or 0
        step = {"actions": [{"type": "postInstall", "path": r"C:\Program Files\Helper\hang.exe",
                             "params": "CreateEventLog"}]}
        self.assertTrue(self.inst.do_actions(step, "action.log"))
        self.assertEqual(seen, [self.mod.ACTION_TIMEOUT])

    def test_hanging_action_does_not_stop_the_install(self):
        self.mod.ACTION_TIMEOUT = 1
        step = {"actions": [{"type": "postInstall", "path": r"C:\Program Files\Helper\hang.exe",
                             "params": "CreateEventLog"}]}
        t0 = time.monotonic()
        self.assertTrue(self.inst.do_actions(step, "action.log"))
        self.assertLess(time.monotonic() - t0, 30)
        log = Path(self.inst.logdir, "install.log").read_text()
        self.assertIn("WARN postInstall action returned -1", log)


if __name__ == "__main__":
    unittest.main()
