"""Exercise the launch scripts (release state, native licensing-state migration,
fonts, registry refresh) without Wine. nix-overlayfs's session lock, which
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

    # The Tahoma -> Segoe UI substitution of earlier launchers is removed;
    # none is added, even with Segoe UI installed (ClearType since winum
    # 11.22-3 makes Tahoma smooth).
    def test_leftover_segoe_substitution_is_removed(self):
        self.env["FONT_CURRENT"] = "Segoe UI"
        self.assertIn("reg delete", self.apply_fonts())

    def test_removed_even_with_segoe_installed(self):
        self.env.update(FONT_CURRENT="Segoe UI", FONT_HOST_FAMILIES="Segoe UI",
                        FONT_PREFIX_FAMILIES="Segoe UI")
        actions = self.apply_fonts()
        self.assertIn("reg delete", actions)
        self.assertNotIn("reg add", actions)

    def test_no_substitution_is_added(self):
        self.env.update(FONT_HOST_FAMILIES="Segoe UI", FONT_PREFIX_FAMILIES="Segoe UI")
        self.assertEqual(self.apply_fonts(), "")

    def test_custom_substitution_is_preserved(self):
        self.env["FONT_CURRENT"] = "DejaVu Sans"
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

    def test_shared_components_values_follow_the_installation(self):
        # The writable registry is merged after the layers: after an update
        # that moves the Shared Components version, the launcher writes the
        # installed version again, so old values cannot win.
        year = "2027"
        self.env["INVENTOR_YEAR"] = year
        prefix = Path(self.env["WINEPREFIX"])
        service = prefix / "drive_c/ProgramData/Autodesk/AdskLicensingService"
        service.mkdir(parents=True)
        (service / "AdskLicensingService.sds").write_bytes(b"state")
        (prefix / ("drive_c/Program Files (x86)/Common Files/"
                   "Autodesk Shared/AdskLicensing/1.0")).mkdir(parents=True)
        components = prefix / f"drive_c/Program Files/Common Files/Autodesk Shared/Components/{year}"
        for version in ["31.0.2", "31.0.10"]:
            (components / version).mkdir(parents=True)
        profile = prefix / "drive_c/users" / self.env["USER"] / (
            f"AppData/Roaming/Autodesk/Inventor {year}/RealDWGSettings.xml")
        profile.parent.mkdir(parents=True)
        profile.write_text("settings")
        log = self.root / "wine.log"
        # what `reg query ... /v Path` answers: a user's own segment and the
        # Shared Components folder of the version before the update
        current_path = self.root / "path.txt"
        current_path.write_text(
            "C:\\windows\\system32;C:\\windows;C:\\Tools\\mine;"
            f"C:\\Program Files\\Common Files\\Autodesk Shared\\Components\\{year}\\31.0.2;"
            f"C:\\Program Files\\Autodesk\\Inventor {year}\\Bin")
        mock_bin = self.root / "bin"
        mock_bin.mkdir()
        (mock_bin / "wine").write_text(
            f"#!{shutil.which('bash')}\n"
            f"printf '%s\\n' \"$*\" >> {log}\n"
            "if [ \"$1 $2\" = 'reg query' ]; then\n"
            f"  printf '\\r\\n%s\\r\\n    Path    REG_EXPAND_SZ    %s\\r\\n' \"$3\" \"$(cat {current_path})\"\n"
            "fi\n")
        (mock_bin / "sleep").write_text(f"#!{shutil.which('bash')}\nexit 0\n")
        for name in ["wine", "sleep"]:
            (mock_bin / name).chmod(0o755)
        self.env["PATH"] = str(mock_bin) + os.pathsep + self.env["PATH"]
        out = self.run_script(f'. "{STATE}"; . "{SERVICES}"')
        self.assertEqual(out.returncode, 0, out.stderr)
        calls = log.read_text()
        key = f"reg add HKLM\\SOFTWARE\\Autodesk\\SharedComponents\\{year}"
        self.assertIn(f"{key} /v Version /t REG_EXPAND_SZ /d 31.0.10 /f", calls)
        # ClearType with RGB subpixels, as on Windows, at every start
        desktop = "reg add HKCU\\Control Panel\\Desktop"
        self.assertIn(f"{desktop} /v FontSmoothing /t REG_SZ /d 2 /f", calls)
        self.assertIn(f"{desktop} /v FontSmoothingType /t REG_DWORD /d 2 /f", calls)
        self.assertIn(f"{desktop} /v FontSmoothingOrientation /t REG_DWORD /d 1 /f", calls)
        self.assertIn(f"{key} /v InstallPath /t REG_EXPAND_SZ "
                      f"/d C:\\Program Files\\Common Files\\Autodesk Shared\\Components\\{year} /f", calls)
        # only the Shared Components segment changes; the user's stays
        self.assertIn("/v Path /t REG_EXPAND_SZ /d C:\\windows\\system32;C:\\windows;C:\\Tools\\mine;"
                      f"C:\\Program Files\\Common Files\\Autodesk Shared\\Components\\{year}\\31.0.10;"
                      f"C:\\Program Files\\Autodesk\\Inventor {year}\\Bin /f", calls)
        self.assertNotIn("31.0.2", calls)
        # a Path that is already current is not written again
        current_path.write_text(
            "C:\\windows\\system32;C:\\Tools\\mine;"
            f"C:\\Program Files\\Common Files\\Autodesk Shared\\Components\\{year}\\31.0.10;"
            f"C:\\Program Files\\Autodesk\\Inventor {year}\\Bin")
        log.write_text("")
        out = self.run_script(f'. "{STATE}"; . "{SERVICES}"')
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("/v Path /t", log.read_text())
        # a custom subdirectory of the Shared Components folder is not the
        # managed version directory: it stays, only 31.0.2 is replaced
        custom = f"C:\\Program Files\\Common Files\\Autodesk Shared\\Components\\{year}\\Plugins"
        current_path.write_text(
            f"C:\\windows\\system32;{custom};"
            f"C:\\Program Files\\Common Files\\Autodesk Shared\\Components\\{year}\\31.0.2;"
            f"C:\\Program Files\\Autodesk\\Inventor {year}\\Bin")
        log.write_text("")
        out = self.run_script(f'. "{STATE}"; . "{SERVICES}"')
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn(f"/d C:\\windows\\system32;{custom};"
                      f"C:\\Program Files\\Common Files\\Autodesk Shared\\Components\\{year}\\31.0.10;", log.read_text())
        # a failed query leaves Path alone instead of writing defaults
        (mock_bin / "wine").write_text(
            f"#!{shutil.which('bash')}\n"
            f"printf '%s\\n' \"$*\" >> {log}\n"
            "if [ \"$1 $2\" = 'reg query' ]; then exit 1; fi\n")
        log.write_text("")
        out = self.run_script(f'. "{STATE}"; . "{SERVICES}"')
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("/v Path /t", log.read_text())
        self.assertIn("could not read the Windows Path", out.stderr)


if __name__ == "__main__":
    unittest.main()
