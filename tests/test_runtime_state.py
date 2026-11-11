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
FONTS = ROOT / "nix/launch-fonts.sh"


class RuntimeFonts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="inventor-runtime-fonts-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        mock_bin = self.root / "bin"
        mock_bin.mkdir()
        self.actions = self.root / "actions"
        self.env = os.environ | {
            "PATH": str(mock_bin) + os.pathsep + os.environ["PATH"],
            "WINEPREFIX": str(self.root / "prefix"),
            "FONT_HOST_FAMILIES": "",
            "FONT_PREFIX_FAMILIES": "",
            "FONT_CURRENT": "",
            "FONT_ACTIONS": str(self.actions),
        }
        scripts = {
            "fc-list": 'printf "%s\\n" "$FONT_HOST_FAMILIES"',
            "fc-scan": 'printf "%s\\n" "$FONT_PREFIX_FAMILIES"',
            "wine": '''
if [ "$2" = query ]; then
    if [ -z "$FONT_CURRENT" ]; then
        printf 'reg: Unable to find the specified registry value\\n'
        exit 1
    fi
    printf 'HKEY_LOCAL_MACHINE\\n    Tahoma    REG_SZ    %s\\n' "$FONT_CURRENT"
else
    printf '%s\\n' "$*" >> "$FONT_ACTIONS"
fi
''',
        }
        for name, script in scripts.items():
            path = mock_bin / name
            path.write_text(f"#!{shutil.which('bash')}\n{script}\n")
            path.chmod(0o755)

    def apply_fonts(self):
        result = subprocess.run(["bash", "-euo", "pipefail", str(FONTS)],
                                env=self.env, text=True, capture_output=True,
                                timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.actions.read_text() if self.actions.exists() else ""

    def test_real_host_family_enables_substitution(self):
        self.env["FONT_HOST_FAMILIES"] = "Segoe UI,Segoe UI Semibold"
        actions = self.apply_fonts()
        self.assertIn("reg add", actions)
        self.assertIn("/v Tahoma /t REG_SZ /d Segoe UI /f", actions)

    def test_prefix_font_enables_substitution(self):
        self.env["FONT_PREFIX_FAMILIES"] = "Segoe UI"
        self.assertIn("reg add", self.apply_fonts())

    def test_fallback_and_other_segoe_families_do_not_enable_it(self):
        self.env["FONT_HOST_FAMILIES"] = "Noto Sans\nSegoe UI Symbol\nSegoe UI Variable"
        self.assertEqual(self.apply_fonts(), "")

    def test_disappearing_font_removes_segoe_substitution(self):
        self.env["FONT_CURRENT"] = "Segoe UI"
        self.assertIn("reg delete", self.apply_fonts())

    def test_existing_segoe_substitution_needs_no_write(self):
        self.env.update(FONT_CURRENT="Segoe UI", FONT_HOST_FAMILIES="Segoe UI")
        self.assertEqual(self.apply_fonts(), "")

    def test_custom_substitution_is_preserved_with_or_without_segoe(self):
        self.env["FONT_CURRENT"] = "DejaVu Sans"
        self.assertEqual(self.apply_fonts(), "")
        self.env["FONT_HOST_FAMILIES"] = "Segoe UI"
        self.assertEqual(self.apply_fonts(), "")


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

    def test_different_releases_can_hold_locks_simultaneously(self):
        script = f'. "{LOCK}"; echo ready; read -r line'
        owner = subprocess.Popen(["bash", "-c", script], env=self.env,
                                 text=True, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: owner.poll() is None and owner.kill())
        self.assertEqual(owner.stdout.readline().strip(), "ready")
        self.env["INVENTOR_YEAR"] = "2027"
        other = self.run_script(f'. "{LOCK}"; printf "%s" "$inventor_state_dir"')
        self.assertEqual(other.returncode, 0, other.stderr)
        self.assertIn("autodesk-inventor-2027", other.stdout)
        owner.communicate("release\n", timeout=5)

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
        script = f'. "{LOCK}"; . "{SERVICES}"'
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


if __name__ == "__main__":
    unittest.main()
