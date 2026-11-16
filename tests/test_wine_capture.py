"""Captured wine calls must not wait for the prefix's services.

A wine call into a stopped prefix starts the wineserver and the prefix's
services (FlexNet's FNPLicensingService64.exe in a 2026 prefix,
MicrosoftEdgeUpdate.exe /c), which inherit stdout and never exit. Reading
that output from a pipe waits for them forever: the .NET Framework 4.0 step
of a fresh 2026 installation hung for 40 minutes (2026-11-16). The fake wine
here leaves such a child behind, holding stdout and stderr open; every
capture must return as soon as wine itself exits."""
import argparse
import importlib.util
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from shell_fixture import fixture_path, shell_script

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("USER", "test")

# answers like Wine's reg/uninstaller, then leaves a "service" running that
# keeps the inherited stdout/stderr open for 40 s
FAKE_WINE = r"""#!/bin/bash
case "$1 $2" in
    "reg query")  printf '\r\n%s\r\n    %s    REG_SZ    %s\r\n\r\n' "$3" "$5" "win7" ;;
    "uninstaller --list") echo "{E45D8920-A758-4088-B6C6-31DBB276992E}|||Wine Mono Windows Support" >&2 ;;
esac
( sleep 40 ) &
exit 0
"""


def load_installer():
    spec = importlib.util.spec_from_file_location("install_from_image", ROOT / "scripts" / "install-from-image.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class WineCapture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-wine-capture-")
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.bin = t / "bin"
        self.bin.mkdir()
        w = self.bin / "wine"
        w.write_text(shell_script(FAKE_WINE))
        w.chmod(0o755)
        self.prefix = t / "prefix"
        (self.prefix / "drive_c").mkdir(parents=True)

    def installer(self):
        saved = os.environ.get("INV_LOGDIR")
        os.environ["INV_LOGDIR"] = str(Path(self.tmp.name) / "logs")
        self.addCleanup(lambda: os.environ.pop("INV_LOGDIR", None) if saved is None
                        else os.environ.__setitem__("INV_LOGDIR", saved))
        a = argparse.Namespace(image=str(Path(self.tmp.name) / "image"), prefix=str(self.prefix), lang="en-US",
                               dry_run=False, redo=False)
        inst = load_installer().Installer(a)
        inst.env["PATH"] = fixture_path(self.bin)
        return inst

    def test_reg_query_returns_when_wine_exits(self):
        inst = self.installer()
        t0 = time.monotonic()
        self.assertEqual(inst.reg_query(r"HKCU\Software\Wine", "Version"), "win7")
        self.assertLess(time.monotonic() - t0, 15)

    def test_wine_mono_entries_returns_when_wine_exits(self):
        inst = self.installer()
        t0 = time.monotonic()
        self.assertEqual(inst.wine_mono_entries(), ["{E45D8920-A758-4088-B6C6-31DBB276992E}"])
        self.assertLess(time.monotonic() - t0, 15)

    def test_no_pipe_reads_of_wine_left_in_the_installer(self):
        text = (ROOT / "scripts" / "install-from-image.py").read_text()
        self.assertNotIn("capture_output", text)
        self.assertNotIn("stdout=subprocess.PIPE", text)

    def test_shell_captures_return_when_wine_exits(self):
        env = dict(os.environ, PATH=fixture_path(self.bin), HOME=self.tmp.name, INV_WINE="system",
                   INV_PREFIX=str(self.prefix), WINEPREFIX=str(self.prefix), INV_LOGDIR=str(Path(self.tmp.name)))
        script = ('source scripts/lib/common.sh >/dev/null 2>&1; source scripts/lib/migrations.sh; '
                  'out="$(wine_capture reg query "HKCU\\\\Software\\\\Wine" /v Version)"; '
                  'printf "%s" "$out" | grep -c REG_SZ; mig_reg_get "HKCU\\\\Software\\\\Wine" Version; '
                  'dotnet48_why || true')
        t0 = time.monotonic()
        out = subprocess.run(["bash", "-c", script], cwd=str(ROOT), env=env, capture_output=True, text=True,
                             timeout=50)
        self.assertLess(time.monotonic() - t0, 30, out.stdout + out.stderr)
        lines = out.stdout.splitlines()
        self.assertEqual(lines[:2], ["1", "win7"], out.stdout + out.stderr)

    def test_no_shell_pipe_reads_of_wine_reg(self):
        for f in ("scripts/lib/common.sh", "scripts/lib/migrations.sh", "scripts/launch-inventor.sh"):
            for line in (ROOT / f).read_text().splitlines():
                if "$(" in line and "wine reg query" in line:
                    self.fail("%s: %s" % (f, line.strip()))


class SudoOnlyForPackages(unittest.TestCase):
    def test_sudo_is_asked_only_when_packages_are_installed(self):
        text = (ROOT / "scripts" / "install.sh").read_text()
        i = text.index("sudo -v")
        block = text[text.rindex("\nif ", 0, i):i]
        self.assertIn('"$SKIP_PKG" -eq 0', block)
        self.assertIn('-z "${INV_GUI:-}"', block)
        # no other step of install.sh calls sudo itself
        calls = [l for l in text.splitlines() if "sudo " in l and not l.lstrip().startswith("#")
                 and "sudo -v" not in l and "not with sudo" not in l]
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
