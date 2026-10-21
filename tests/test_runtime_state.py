"""Exercise session exclusion and native licensing-state migration without Wine."""
from pathlib import Path
import os
import pwd
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "nix/launch-lock.sh"
SERVICES = ROOT / "nix/launch-services.sh"


class RuntimeState(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="inventor-runtime-state-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = os.environ | {
            "XDG_DATA_HOME": str(self.root / "data"),
            "XDG_STATE_HOME": str(self.root / "state"),
            "WINEPREFIX": str(self.root / "overlay"),
            "INVENTOR_WINE_DRIVER": "x11",
            "USER": pwd.getpwuid(os.getuid()).pw_name,
        }

    def run_script(self, script):
        return subprocess.run(["bash", "-c", script], env=self.env,
                              text=True, capture_output=True, timeout=10)

    def test_lock_survives_exec_and_blocks_overlap(self):
        script = f'. "{LOCK}"; exec bash -c \'echo ready; read -r line\''
        owner = subprocess.Popen(["bash", "-c", script], env=self.env,
                                 text=True, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: owner.poll() is None and owner.kill())
        self.assertEqual(owner.stdout.readline().strip(), "ready")
        blocked = self.run_script(f'. "{LOCK}"')
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("already in use", blocked.stderr)
        owner.communicate("release\n", timeout=5)
        self.assertEqual(owner.returncode, 0)
        self.assertEqual(self.run_script(f'. "{LOCK}"').returncode, 0)

    def test_database_migration_preserves_native_updates(self):
        prefix = Path(self.env["WINEPREFIX"])
        service = prefix / "drive_c/ProgramData/Autodesk/AdskLicensingService"
        service.mkdir(parents=True)
        database = service / "AdskLicensingService.sds"
        database.write_bytes(b"registered-product-and-user-state")
        database.chmod(0o444)
        (service / "AdskLicensingService.data").write_text("endpoint")
        version = prefix / ("drive_c/Program Files (x86)/Common Files/"
                            "Autodesk Shared/AdskLicensing/1.0")
        version.mkdir(parents=True)
        profile = prefix / "drive_c/users" / self.env["USER"] / (
            "AppData/Roaming/Autodesk/Inventor 2026/RealDWGSettings.xml")
        profile.parent.mkdir(parents=True)
        profile.write_text("settings")
        mock_bin = self.root / "bin"
        mock_bin.mkdir()
        for name in ["wine", "sleep"]:
            path = mock_bin / name
            path.write_text(f"#!{shutil.which('bash')}\nexit 0\n")
            path.chmod(0o755)
        self.env["PATH"] = str(mock_bin) + os.pathsep + self.env["PATH"]
        script = f'. "{LOCK}"; . "{SERVICES}"'
        first = self.run_script(script)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue(database.is_symlink())
        native = database.resolve()
        self.assertFalse(native.is_relative_to(prefix))
        self.assertEqual(native.read_bytes(), b"registered-product-and-user-state")
        self.assertEqual(native.stat().st_mode & 0o777, 0o600)
        native.write_bytes(b"updated-genuine-authorization")
        # An older launcher or a fresh composition may leave a regular file.
        database.unlink()
        database.write_bytes(b"older-overlay-copy")
        second = self.run_script(script)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(database.is_symlink())
        self.assertEqual(database.read_bytes(), b"updated-genuine-authorization")


if __name__ == "__main__":
    unittest.main()
