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
        self.state = self.root / "state"
        self.state.mkdir()
        self.base_conf = self.root / "fonts.conf"
        self.base_conf.write_text("<fontconfig/>\n")
        self.actions = self.root / "actions"
        self.env = os.environ | {
            "PATH": str(mock_bin) + os.pathsep + os.environ["PATH"],
            "WINEPREFIX": str(self.root / "prefix"),
            "inventor_state_dir": str(self.state),
            "FONTCONFIG_FILE": str(self.base_conf),
            "FONT_CURRENT": "",
            "FONT_ACTIONS": str(self.actions),
        }
        self.set_desktop(smoothing="2", type="0x1", orientation="0x1")
        # Output as Wine's reg.exe prints it, with CRLF line ends.
        scripts = {
            "wine": r"""
if [ "$2" = query ]; then
    case "$3" in
        *Desktop)
            printf 'HKEY_CURRENT_USER\\Control Panel\\Desktop\r\n'
            printf '    FontSmoothing    REG_SZ    %s\r\n' "$FONT_SMOOTHING"
            printf '    FontSmoothingOrientation    REG_DWORD    %s\r\n' "$FONT_ORIENTATION"
            printf '    FontSmoothingType    REG_DWORD    %s\r\n' "$FONT_TYPE"
            ;;
        *FontSubstitutes)
            if [ -z "$FONT_CURRENT" ]; then
                printf 'reg: Unable to find the specified registry value\r\n'
                exit 1
            fi
            printf 'HKEY_LOCAL_MACHINE\r\n    Tahoma    REG_SZ    %s\r\n' "$FONT_CURRENT"
            ;;
    esac
else
    printf '%s\n' "$*" >> "$FONT_ACTIONS"
fi
""",
        }
        for name, script in scripts.items():
            path = mock_bin / name
            path.write_text(f"#!{shutil.which('bash')}\n{script}\n")
            path.chmod(0o755)

    def set_desktop(self, smoothing, type, orientation):
        self.env.update(FONT_SMOOTHING=smoothing, FONT_TYPE=type,
                        FONT_ORIENTATION=orientation)

    def apply_fonts(self):
        """Source the script; return (registry writes, FONTCONFIG_FILE after)."""
        if self.actions.exists():
            self.actions.unlink()
        result = subprocess.run(
            ["bash", "-euo", "pipefail", "-c",
             f'. "{FONTS}"; printf "%s" "$FONTCONFIG_FILE"'],
            env=self.env, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        actions = self.actions.read_text() if self.actions.exists() else ""
        return actions, result.stdout

    def assert_subpixel(self, fontconfig_file, rgba):
        conf = Path(fontconfig_file)
        self.assertEqual(conf, self.state / "fonts-subpixel.conf")
        text = conf.read_text()
        self.assertIn(f"<include ignore_missing=\"no\">{self.base_conf}</include>", text)
        self.assertIn(f"<const>{rgba}</const>", text)

    def test_first_launch_switches_greyscale_prefix_to_cleartype(self):
        actions, fontconfig_file = self.apply_fonts()
        self.assertIn("/v FontSmoothingType /t REG_DWORD /d 2 /f", actions)
        self.assertTrue((self.state / "font-smoothing-cleartype").exists())
        self.assert_subpixel(fontconfig_file, "rgb")

    def test_later_choice_of_greyscale_is_kept(self):
        self.apply_fonts()
        actions, fontconfig_file = self.apply_fonts()
        self.assertEqual(actions, "")
        self.assertEqual(fontconfig_file, str(self.base_conf))

    def test_cleartype_prefix_needs_no_write(self):
        self.set_desktop(smoothing="2", type="0x2", orientation="0x1")
        actions, fontconfig_file = self.apply_fonts()
        self.assertEqual(actions, "")
        self.assert_subpixel(fontconfig_file, "rgb")

    def test_bgr_orientation(self):
        self.set_desktop(smoothing="2", type="0x2", orientation="0x0")
        self.assert_subpixel(self.apply_fonts()[1], "bgr")

    def test_smoothing_off_leaves_fontconfig_alone(self):
        self.set_desktop(smoothing="0", type="0x2", orientation="0x1")
        self.assertEqual(self.apply_fonts()[1], str(self.base_conf))

    def test_former_segoe_substitution_is_removed_once(self):
        self.env["FONT_CURRENT"] = "Segoe UI"
        self.assertIn("reg delete", self.apply_fonts()[0])
        # A substitution the user adds again afterwards stays.
        self.assertEqual(self.apply_fonts()[0], "")

    def test_custom_substitution_is_preserved(self):
        self.env["FONT_CURRENT"] = "DejaVu Sans"
        self.assertNotIn("reg delete", self.apply_fonts()[0])


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
