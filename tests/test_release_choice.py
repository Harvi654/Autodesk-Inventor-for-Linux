"""Which Inventor release and prefix the scripts take when INV_YEAR is not
given: fake prefixes in a temporary HOME, config.env in a temporary
XDG_CONFIG_HOME. No Wine is started (select_wine finds none)."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseChoice(unittest.TestCase):
    def setUp(self):
        if (ROOT / "config.env").exists():
            self.skipTest("this checkout has a config.env, which would take part")
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-release-choice-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.cfg = Path(self.tmp.name) / "config"
        self.home.mkdir()

    def prefix(self, name, year=None, addins=()):
        p = self.home / name
        (p / "drive_c").mkdir(parents=True)
        if year:
            b = p / "drive_c" / "Program Files" / "Autodesk" / ("Inventor %s" % year) / "Bin"
            (b / "Addins").mkdir(parents=True)
            (b / "Inventor.exe").write_bytes(b"")
            for a in addins:
                (b / "Addins" / a).write_text("")
        return p

    def config(self, text):
        d = self.cfg / "inventor-on-linux"
        d.mkdir(parents=True, exist_ok=True)
        (d / "config.env").write_text(text)

    def env(self, **extra):
        e = {"HOME": str(self.home), "USER": "test", "PATH": "/usr/bin:/bin",
             "XDG_CONFIG_HOME": str(self.cfg), "XDG_DATA_HOME": str(self.home / "data")}
        e.update(extra)
        return e

    def choice(self, pre="", **extra):
        out = subprocess.run(["bash", "-c", pre + 'source scripts/lib/common.sh >/dev/null 2>&1; '
                              'printf "%s|%s|%s\\n" "$INV_YEAR" "$INV_PREFIX" "$INV_PREFIX_SOURCE"'],
                             cwd=str(ROOT), env=self.env(**extra), capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        return tuple(out.stdout.strip().split("|"))

    def test_maintainers_case_config_prefix_2026_and_a_2027_prefix(self):
        # config.env names a working 2026 prefix on purpose; ~/.wine-inventor2027
        # exists beside it
        c = self.prefix(".wine-invclean", 2026)
        p27 = self.prefix(".wine-inventor2027", 2027)
        self.config('INV_PREFIX=$HOME/.wine-invclean\n')
        self.assertEqual(self.choice(), ("2026", str(c), "config.env"))
        self.assertEqual(self.choice(INV_YEAR="2027"), ("2027", str(p27), "default"))

    def test_no_config_only_2027(self):
        # a fresh Ubuntu VM: no config.env, only ~/.wine-inventor2027 - not
        # 2026 in an empty ~/.wine-inventor2026 ("no Inventor in ...2026")
        p = self.prefix(".wine-inventor2027", 2027)
        self.assertEqual(self.choice(), ("2027", str(p), "found"))

    def test_migrate_status_without_anything_given(self):
        # the Ubuntu VM: "ERROR no Inventor in .../.wine-inventor2026" before
        p = self.prefix(".wine-inventor2027", 2027)
        out = subprocess.run(["bash", "scripts/migrate-prefix.sh", "--status"], cwd=str(ROOT), env=self.env(),
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("Inventor 2027 in %s (prefix: found)" % p, out.stdout)

    def test_no_config_test_prefix_only(self):
        # an older VM: the only installation in a prefix of another name
        p = self.prefix(".wine-inventor2027-msitest", 2027)
        (p / ".odis-install-state.json").write_text("{}")
        self.assertEqual(self.choice(), ("2027", str(p), "found"))

    def test_no_config_2026_with_inventor_stays(self):
        # ~/.wine-inventor2026 with Inventor: the default stays 2026
        p = self.prefix(".wine-inventor2026", 2026)
        self.prefix(".wine-inventor2027", 2027)
        self.assertEqual(self.choice(), ("2026", str(p), "default"))

    def test_config_prefix_without_inventor_falls_back_to_the_installed_one(self):
        # the maintainer's case: config.env still named an emptied test prefix
        self.prefix(".wine-invclean")
        p = self.prefix(".wine-inventor2027", 2027)
        self.config('INV_PREFIX="$HOME/.wine-invclean"\n')
        self.assertEqual(self.choice(), ("2027", str(p), "found"))

    def test_config_prefix_with_inventor_wins(self):
        c = self.prefix(".wine-invclean", 2026)
        self.prefix(".wine-inventor2027", 2027)
        self.config('INV_PREFIX="$HOME/.wine-invclean"\n')
        self.assertEqual(self.choice(), ("2026", str(c), "config.env"))

    def test_empty_config_prefix_several_installed_newest(self):
        self.prefix(".wine-invclean")
        self.prefix(".wine-inventor2026", 2026)
        p = self.prefix(".wine-inventor2027", 2027)
        self.config('INV_PREFIX="$HOME/.wine-invclean"\n')
        self.assertEqual(self.choice(), ("2027", str(p), "found"))

    def test_year_given(self):
        self.prefix(".wine-inventor2027", 2027)
        self.assertEqual(self.choice(INV_YEAR="2026"), ("2026", str(self.home / ".wine-inventor2026"), "default"))

    def test_prefix_from_environment_is_kept(self):
        self.prefix(".wine-inventor2027", 2027)
        target = self.prefix(".wine-new")
        self.assertEqual(self.choice(INV_PREFIX=str(target)), ("2026", str(target), "environment"))

    def test_nothing_installed(self):
        self.assertEqual(self.choice(), ("2026", str(self.home / ".wine-inventor2026"), "default"))

    def desktop(self, **extra):
        env = dict(self.env(), XDG_DATA_HOME=str(self.home / "data"), INV_LOGDIR=str(self.home / "logs"))
        env.update(extra)
        out = subprocess.run(["bash", "scripts/install-desktop-integration.sh"], cwd=str(ROOT), env=env,
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        apps = self.home / "data" / "applications"
        return out, sorted(p.name for p in apps.glob("autodesk-inventor-20*.desktop")) if apps.exists() else []

    def test_desktop_entry_for_the_installed_release_only(self):
        self.prefix(".wine-inventor2027", 2027)
        out, entries = self.desktop()
        self.assertEqual(entries, ["autodesk-inventor-2027.desktop"])
        # asked for a release that is not installed: no entry, no failure
        out, entries = self.desktop(INV_YEAR="2026")
        self.assertIn("no Inventor 2026", out.stderr)
        self.assertEqual(entries, ["autodesk-inventor-2027.desktop"])

    def test_desktop_entry_maintainers_case(self):
        self.prefix(".wine-invclean", 2026)
        self.prefix(".wine-inventor2027", 2027)
        self.config('INV_PREFIX=$HOME/.wine-invclean\n')
        out, entries = self.desktop()
        self.assertEqual(entries, ["autodesk-inventor-2026.desktop"])
        out, entries = self.desktop(INV_YEAR="2027")
        self.assertEqual(entries, ["autodesk-inventor-2026.desktop", "autodesk-inventor-2027.desktop"])

    def test_installer_keeps_its_own_choice(self):
        self.prefix(".wine-inventor2027", 2027)
        self.assertEqual(self.choice(pre="_INV_FOR_INSTALL=1; "),
                         ("2026", str(self.home / ".wine-inventor2026"), "default"))

    def test_addins_list_names_prefix_and_release(self):
        c = self.prefix(".wine-invclean", 2026, addins=["Anark.Core.addin", "iLogic.addin"])
        self.prefix(".wine-inventor2027", 2027)
        self.config('INV_PREFIX=$HOME/.wine-invclean\n')
        out = subprocess.run(["bash", "scripts/addins.sh", "list"], cwd=str(ROOT), env=self.env(),
                             capture_output=True, text=True)
        # also: exit code 0 without Addins.disabled/libs
        self.assertEqual(out.returncode, 0, out.stderr)
        first = out.stdout.splitlines()[0]
        self.assertEqual(first, "Inventor 2026 in %s (prefix: config.env; INV_YEAR=... or INV_PREFIX=... "
                                "chooses another)" % c)
        self.assertIn("Anark.Core.addin", out.stdout)


if __name__ == "__main__":
    unittest.main()
