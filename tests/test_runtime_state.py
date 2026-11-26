"""Exercise the launch scripts (release state, native licensing-state migration)
without Wine. nix-overlayfs's session lock, which
allows one session per release, is tested in nix-overlayfs."""
from pathlib import Path
import os
import pwd
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "nix/launch-state.sh"
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
            "INVENTOR_YEAR": "2026",
            "USER": pwd.getpwuid(os.getuid()).pw_name,
        }

    def run_script(self, script):
        return subprocess.run(["bash", "-c", script], env=self.env,
                              text=True, capture_output=True, timeout=10)

    def test_state_takes_no_lock(self):
        # Two launches of one release must not be serialized here: nix-overlayfs
        # does it before touching the state, and a descriptor opened here would
        # be inherited by Wine. Sourcing opens nothing and blocks nothing.
        script = f'. "{STATE}"; echo ready; ls -l /proc/$$/fd; read -r line'
        owner = subprocess.Popen(["bash", "-c", script], env=self.env,
                                 text=True, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: owner.poll() is None and owner.kill())
        self.assertEqual(owner.stdout.readline().strip(), "ready")
        second = self.run_script(f'. "{STATE}"; printf "%s" "$inventor_state_dir"')
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(second.stdout.endswith("autodesk-inventor-2026/.nix-overlayfs"), second.stdout)
        fds, _ = owner.communicate("release\n", timeout=5)
        self.assertNotIn("inventor.lock", fds)

    def test_releases_have_separate_state(self):
        self.env["INVENTOR_YEAR"] = "2027"
        other = self.run_script(f'. "{STATE}"; printf "%s" "$inventor_state_dir"')
        self.assertEqual(other.returncode, 0, other.stderr)
        self.assertIn("autodesk-inventor-2027", other.stdout)
        self.assertTrue(Path(other.stdout).is_dir())

    def test_database_migration_preserves_native_updates(self):
        self.check_database_migration("2026")

    def test_2027_database_migration_is_separate(self):
        self.check_database_migration("2027")

    def check_database_migration(self, year):
        self.env["INVENTOR_YEAR"] = year
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
            f"AppData/Roaming/Autodesk/Inventor {year}/RealDWGSettings.xml")
        profile.parent.mkdir(parents=True)
        profile.write_text("settings")
        mock_bin = self.root / "bin"
        mock_bin.mkdir()
        for name in ["wine", "sleep"]:
            path = mock_bin / name
            path.write_text(f"#!{shutil.which('bash')}\nexit 0\n")
            path.chmod(0o755)
        self.env["PATH"] = str(mock_bin) + os.pathsep + self.env["PATH"]
        script = f'. "{STATE}"; . "{SERVICES}"'
        first = self.run_script(script)
        self.assertEqual(first.returncode, 0, first.stderr)
        public_macros = prefix / f"drive_c/users/Public/Documents/Autodesk/Inventor {year}/Macros"
        user_addins = profile.parent / "Addins"
        for directory in [public_macros, user_addins]:
            self.assertTrue(directory.is_dir())
            probe = directory / "write-test.tmp"
            probe.write_text("writable")
            probe.unlink()
        self.assertTrue(database.is_symlink())
        native = database.resolve()
        self.assertFalse(native.is_relative_to(prefix))
        self.assertIn(f"autodesk-inventor-{year}", str(native))
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

    def test_launcher_writes_no_registry_values(self):
        # Package settings come from the layers; the launcher must not write
        # registry values into the writable state (nix/AGENTS.md).
        year = "2027"
        self.env["INVENTOR_YEAR"] = year
        prefix = Path(self.env["WINEPREFIX"])
        service = prefix / "drive_c/ProgramData/Autodesk/AdskLicensingService"
        service.mkdir(parents=True)
        (service / "AdskLicensingService.sds").write_bytes(b"state")
        (prefix / ("drive_c/Program Files (x86)/Common Files/"
                   "Autodesk Shared/AdskLicensing/1.0")).mkdir(parents=True)
        (prefix / f"drive_c/Program Files/Common Files/Autodesk Shared/Components/{year}/31.0.10").mkdir(parents=True)
        profile = prefix / "drive_c/users" / self.env["USER"] / (
            f"AppData/Roaming/Autodesk/Inventor {year}/RealDWGSettings.xml")
        profile.parent.mkdir(parents=True)
        profile.write_text("settings")
        log = self.root / "wine.log"
        mock_bin = self.root / "bin"
        mock_bin.mkdir()
        (mock_bin / "wine").write_text(f"#!{shutil.which('bash')}\nprintf '%s\\n' \"$*\" >> {log}\n")
        (mock_bin / "sleep").write_text(f"#!{shutil.which('bash')}\nexit 0\n")
        for name in ["wine", "sleep"]:
            (mock_bin / name).chmod(0o755)
        self.env["PATH"] = str(mock_bin) + os.pathsep + self.env["PATH"]
        out = self.run_script(f'. "{STATE}"; . "{SERVICES}"')
        self.assertEqual(out.returncode, 0, out.stderr)
        calls = log.read_text() if log.exists() else ""
        self.assertNotIn("reg add", calls)
        self.assertNotIn("reg delete", calls)

if __name__ == "__main__":
    unittest.main()
