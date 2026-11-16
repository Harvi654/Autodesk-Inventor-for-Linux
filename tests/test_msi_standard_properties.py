"""Every MSI gets ODIS's standard properties MSIFASTINSTALL=7,
REBOOT=ReallySuppress and ARPSYSTEMCOMPONENT=1 (docs/installer-
completeness-review.md, "Needed" 8); a value the manifest gives wins.
Patches (MSP) are left as they were. Synthetic step dicts, dry run."""
import os
import shlex
import tempfile
import unittest
from pathlib import Path

import image_fixture as fx


def msi(params="", props=None):
    return {"name": "P", "type": "MSI", "display": "P", "version": "1", "file": "x64/p/p.msi", "params": params,
            "installLocation": None, "msiProperties": props or {}, "properties": {}, "actions": []}


class MsiStandardProperties(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-msi-std-")
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        (t / "image").mkdir()
        (t / "prefix").mkdir()
        saved = os.environ.get("INV_LOGDIR")
        self.addCleanup(lambda: os.environ.pop("INV_LOGDIR", None) if saved is None
                        else os.environ.__setitem__("INV_LOGDIR", saved))
        self.mod, self.inst = fx.installer(t / "image", t / "prefix", t / "logs")
        self.seen = []
        # the command as logged: an msiexec line with a space runs through a batch file
        self.inst.run = lambda argv, logname, timeout=None, show=None: \
            self.seen.append(shlex.split(show) if show else argv) or 0

    def test_standard_properties(self):
        self.inst.do_msi(msi(), "x.log")
        argv = self.seen[0]
        for p in ("MSIFASTINSTALL=7", "REBOOT=ReallySuppress", "ARPSYSTEMCOMPONENT=1", "ADSK_ODIS_SETUP=1"):
            self.assertEqual(argv.count(p), 1, argv)

    def test_manifest_value_wins(self):
        self.inst.do_msi(msi(params="REBOOT=Force", props={"ARPSYSTEMCOMPONENT": "0"}), "x.log")
        argv = self.seen[0]
        self.assertIn("REBOOT=Force", argv)
        self.assertNotIn("REBOOT=ReallySuppress", argv)
        self.assertIn("ARPSYSTEMCOMPONENT=0", argv)
        self.assertNotIn("ARPSYSTEMCOMPONENT=1", argv)
        self.assertIn("MSIFASTINSTALL=7", argv)

    def test_patches_unchanged(self):
        self.inst.do_msp(dict(msi(), type="MSP", file="x64/p/p.msp"), "x.log")
        self.assertFalse(any(a.startswith(("MSIFASTINSTALL=", "ARPSYSTEMCOMPONENT=")) for a in self.seen[0]))


if __name__ == "__main__":
    unittest.main()
