"""nix/desktop-check.sh: reports user desktop entries that hide the NixOS
module's Inventor entries or start an old launcher, and changes nothing."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "nix" / "desktop-check.sh"


class DesktopCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-desktop-check-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.apps = self.root / "data/applications"
        self.apps.mkdir(parents=True)
        self.current = self.root / "store/current/bin/inventor-2027"
        self.old = self.root / "store/old/bin/inventor-2027"
        for launcher in (self.current, self.old):
            launcher.parent.mkdir(parents=True)
            launcher.write_text("#!/bin/sh\n")
            launcher.chmod(0o755)
        # the Nix check has no notify-send: findings go to stderr only
        self.env = dict(os.environ, XDG_DATA_HOME=str(self.root / "data"), HOME=str(self.root))

    def entry(self, name, target):
        path = self.apps / name
        path.write_text(f"[Desktop Entry]\nType=Application\nName=x\nExec={target} %U\n")
        return path

    def run_check(self):
        return subprocess.run(
            ["bash", str(SCRIPT), "autodesk-inventor-2027.desktop", "autodesk-inventor-url-handler.desktop",
             "--", str(self.current)],
            env=self.env, capture_output=True, text=True, timeout=10)

    def test_nothing_to_report(self):
        out = self.run_check()
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stderr, "")

    def test_reports_a_shadowing_entry_and_its_target(self):
        shadow = self.entry("autodesk-inventor-2027.desktop", self.old)
        out = self.run_check()
        self.assertEqual(out.returncode, 0)
        self.assertIn(f"{shadow} hides the system entry of the same name; it starts {self.old}", out.stderr)
        self.assertTrue(shadow.exists(), "the check must not remove anything")

    def test_reports_old_wayland_and_handler_entries(self):
        self.entry("autodesk-inventor-2027-wayland.desktop", self.old)
        self.entry("adskidmgr-handler.desktop", self.root / "gone/launch-inventor")
        out = self.run_check()
        self.assertIn("autodesk-inventor-2027-wayland.desktop (an old Wayland entry) starts", out.stderr)
        self.assertIn("adskidmgr-handler.desktop (an adskidmgr handler outside the module) starts", out.stderr)
        self.assertIn("launch-inventor (missing; Exec=", out.stderr)

    def test_quoted_program_paths_and_env_wrappers(self):
        spaced = self.root / "Old Launchers/inventor-2027"
        spaced.parent.mkdir()
        spaced.write_text("#!/bin/sh\n")
        spaced.chmod(0o755)
        (self.apps / "autodesk-inventor-2027.desktop").write_text(
            f'[Desktop Entry]\nType=Application\nName=x\nExec="{spaced}" %U\n')
        (self.apps / "autodesk-inventor-2027-wayland.desktop").write_text(
            f"[Desktop Entry]\nType=Application\nName=x\nExec=env INVENTOR_WINE_DRIVER=wayland {self.old} %U\n")
        out = self.run_check()
        self.assertIn(f"it starts {spaced}\n", out.stderr)
        self.assertIn(f"(an old Wayland entry) starts {self.old}\n", out.stderr)

    def test_an_unresolvable_program_shows_the_exec_line(self):
        self.entry("autodesk-inventor-2027.desktop", "/gone/inventor-2027")
        out = self.run_check()
        self.assertIn("/gone/inventor-2027 (missing; Exec=/gone/inventor-2027 %U)", out.stderr)

    def test_an_extra_entry_for_the_current_launcher_is_fine(self):
        self.entry("autodesk-inventor-2027-wayland.desktop", self.current)
        self.assertEqual(self.run_check().stderr, "")


if __name__ == "__main__":
    unittest.main()
