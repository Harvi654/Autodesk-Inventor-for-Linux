"""MSI property values with a space (INSTALLDIR=C:\\Program Files\\...)
reach msiexec as NAME="value" through a batch file: passed as an argument,
Wine's msiexec rejects them with 1639 (exit code 103, seen for
InvPrivate.msi on 2026-11-16). Commands without a space run as before.
Fake wine; no real Wine is started."""
import os
import re
import shlex
import tempfile
import unittest
from pathlib import Path

import image_fixture as fx

FAKE_WINE = r"""#!/bin/sh
printf '%s\n' "$*" >> "$WINEPREFIX/calls.log"
exit 0
"""


def msi(props=None, loc=None):
    return {"name": "InvPrivate", "type": "MSI", "display": "Inventor Private 2027", "version": "1",
            "file": "x64/InvPrivate/InvPrivate.msi", "params": "", "installLocation": loc,
            "msiProperties": props or {}, "properties": {}, "actions": []}


class MsiSpaceValues(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-msi-space-")
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        (t / "image").mkdir()
        self.prefix = t / "prefix"
        (self.prefix / "drive_c").mkdir(parents=True)
        b = t / "bin"
        b.mkdir()
        (b / "wine").write_text(FAKE_WINE)
        (b / "wine").chmod(0o755)
        saved = os.environ.get("INV_LOGDIR")
        self.addCleanup(lambda: os.environ.pop("INV_LOGDIR", None) if saved is None
                        else os.environ.__setitem__("INV_LOGDIR", saved))
        self.mod, self.inst = fx.installer(t / "image", self.prefix, t / "logs", dry_run=False)
        self.inst.env["PATH"] = "%s:%s" % (b, os.environ.get("PATH", "/usr/bin:/bin"))

    def calls(self):
        p = self.prefix / "calls.log"
        return p.read_text().splitlines() if p.exists() else []

    def log(self):
        return Path(self.inst.logdir, "install.log").read_text()

    def test_value_with_a_space_goes_through_a_batch_file(self):
        self.assertTrue(self.inst.do_msi(msi(loc=r"C:\Program Files\Autodesk\Inventor 2027" + "\\"), "22-InvPrivate.log"))
        self.assertEqual(self.calls(), [r"cmd /c C:\odis-logs\22-InvPrivate.msi.cmd"])
        bat = (self.prefix / "drive_c/odis-logs/22-InvPrivate.msi.cmd").read_bytes().decode("ascii")
        lines = bat.split("\r\n")
        self.assertEqual(lines[0], "@echo off")
        self.assertTrue(lines[1].startswith(r"msiexec /i M:\x64\InvPrivate\InvPrivate.msi /qn /norestart /l*v "
                                            r"C:\odis-logs\22-InvPrivate.msi.log ADSK_ODIS_SETUP=1 "), lines[1])
        # as ODIS passes it: NAME="value", the trailing backslash kept
        self.assertTrue(lines[1].endswith(r' INSTALLDIR="C:\Program Files\Autodesk\Inventor 2027\"'), lines[1])
        self.assertEqual(lines[2], "exit /b %errorlevel%")
        # the log keeps the usual "$ wine msiexec ..." line (compare-reference.py reads it)
        log = self.log()
        self.assertIn("through C:\\odis-logs\\22-InvPrivate.msi.cmd", log)
        m = re.search(r"\$ wine msiexec /i (\S+)(.*)$", log, re.M)
        self.assertIn("'INSTALLDIR=C:\\Program Files\\Autodesk\\Inventor 2027\\'", m.group(2))

    def test_without_a_space_msiexec_runs_directly(self):
        self.inst.do_msi(msi(props={"ADSK_LANG": "en-US"}, loc=r"C:\ProgramData\Autodesk"), "02-HIVE.log")
        calls = self.calls()
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith(r"msiexec /i M:\x64\InvPrivate\InvPrivate.msi /qn"), calls[0])
        self.assertFalse((self.prefix / "drive_c/odis-logs/02-HIVE.msi.cmd").exists())

    def test_percent_and_other_arguments_with_spaces(self):
        a = self.mod.cmd_arg
        self.assertEqual(a("PROP=50% off"), 'PROP="50%% off"')
        self.assertEqual(a(r"M:\My Image\x.msi"), r'"M:\My Image\x.msi"')
        self.assertEqual(a('PROP="already quoted"'), 'PROP="already quoted"')
        self.assertEqual(a("PLAIN=1"), "PLAIN=1")

    def test_dry_run_writes_no_batch_file(self):
        self.inst.a.dry_run = True
        self.inst.do_msi(msi(loc=r"C:\Program Files\Autodesk"), "02-HIVE.log")
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.prefix / "drive_c/odis-logs").exists())
        self.assertIn(r'INSTALLDIR="C:\Program Files\Autodesk"', self.log())

    def test_exit_code_hint_for_msiexec_through_cmd(self):
        log_line = []
        self.inst.log = log_line.append
        self.inst.a.dry_run = True
        self.inst.run(["wine", "cmd", "/c", "x.cmd"], "x.log", show="wine msiexec /i x.msi")
        self.assertIn("$ wine msiexec /i x.msi", log_line[0])


if __name__ == "__main__":
    unittest.main()
