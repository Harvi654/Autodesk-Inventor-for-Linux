"""Prefix migrations (scripts/lib/migrations.sh, scripts/migrate-prefix.sh)
with fake prefixes in a temporary HOME and a fake Wine: its registry lives
in the prefix's user.reg/system.reg (so backups and restores work on the
real files), `wineboot -u` copies the fake runtime's ntdll.dll into the
prefix. No real Wine is started."""
from pathlib import Path
import hashlib
import os
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "scripts" / "lib" / "migrations"

FAKE_WINE = r"""#!/bin/bash
# registry: "KEY|VALUE|DATA" lines, HKLM in system.reg, the rest in user.reg
echo "$*" >> "$WINEPREFIX/calls.log"
regfile() { case "${1^^}" in HKLM*) echo "$WINEPREFIX/system.reg" ;; *) echo "$WINEPREFIX/user.reg" ;; esac; }
case "$1" in
    --version) echo wine-11.20; exit 0 ;;
    wineboot)
        # like Wine: the builtin DLL copies in system32 stay as they are
        echo 1794413159 > "$WINEPREFIX/.update-timestamp"
        [ -n "${FAIL_WINEBOOT:-}" ] && exit 1
        exit 0 ;;
    reg)
        export K="$3"; f="$(regfile "$3")"; touch "$f"
        case "$2" in
            add)
                v="" t=REG_SZ d=""; shift 3
                while [ $# -gt 0 ]; do case "$1" in /v) v="$2"; shift ;; /t) t="$2"; shift ;; /d) d="$2"; shift ;; esac; shift; done
                [ -n "${FAIL_REG_VALUE:-}" ] && [ "$v" = "$FAIL_REG_VALUE" ] && exit 1
                [ "$t" = REG_DWORD ] && d="$(printf '0x%x' "$d")"
                V="$v" awk -F'|' '!(tolower($1) == tolower(ENVIRON["K"]) && $2 == ENVIRON["V"])' "$f" > "$f.n" 2>/dev/null
                mv "$f.n" "$f"; printf '%s|%s|%s\n' "$K" "$v" "$d" >> "$f"; exit 0 ;;
            query)
                line="$(K="$3" V="$5" awk -F'|' 'tolower($1) == tolower(ENVIRON["K"]) && $2 == ENVIRON["V"]' "$f" | tail -1)"
                [ -n "$line" ] || exit 1
                printf '\r\n%s\r\n    %s    REG_SZ    %s\r\n\r\n' "$3" "$5" "${line##*|}"; exit 0 ;;
        esac ;;
esac
exit 0
"""


class Migrations(unittest.TestCase):
    def setUp(self):
        if (ROOT / "config.env").exists():
            self.skipTest("this checkout has a config.env, which would take part")
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-migrations-")
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.home = t / "home"
        self.home.mkdir()
        # a fake Wine installation: bin/wine, bin/wineserver, lib/wine/*/ntdll.dll
        self.rt = t / "runtime"
        (self.rt / "bin").mkdir(parents=True)
        for arch in ("x86_64-windows", "i386-windows"):
            (self.rt / "lib" / "wine" / arch).mkdir(parents=True)
            (self.rt / "lib" / "wine" / arch / "ntdll.dll").write_bytes(b"ntdll of winum " + arch.encode())
        w = self.rt / "bin" / "wine"
        w.write_text(FAKE_WINE)
        w.chmod(0o755)
        ws = self.rt / "bin" / "wineserver"
        ws.write_text("#!/bin/sh\nexit 0\n")
        ws.chmod(0o755)
        wb = self.rt / "bin" / "wineboot"
        wb.write_text('#!/bin/sh\nexec "$(dirname "$0")/wine" wineboot "$@"\n')
        wb.chmod(0o755)
        self.logs = t / "logs"

    def prefix(self, name=".wine-inventor2027", year=2027, runtime="old"):
        p = self.home / name
        b = p / "drive_c" / "Program Files" / "Autodesk" / ("Inventor %s" % year) / "Bin"
        (b / "Addins").mkdir(parents=True)
        (b / "Inventor.exe").write_bytes(b"")
        for d, arch in (("system32", "x86_64-windows"), ("syswow64", "i386-windows")):
            (p / "drive_c" / "windows" / d).mkdir(parents=True)
            data = (b"ntdll of winum " + arch.encode()) if runtime == "winum" else b"ntdll of wine-inventor-11.20-6"
            (p / "drive_c" / "windows" / d / "ntdll.dll").write_bytes(data)
            (p / "drive_c" / "windows" / d / "kernel32.dll").write_bytes(b"k32 " + runtime.encode())
        for r in ("system.reg", "user.reg", "userdef.reg"):
            (p / r).write_text("WINE REGISTRY Version 2\n")
        (p / ".update-timestamp").write_text("disable\n")
        return p

    def env(self, prefix, year=2027, **extra):
        e = {"HOME": str(self.home), "USER": "test", "PATH": "%s/bin:/usr/bin:/bin" % self.rt,
             "INV_PREFIX": str(prefix), "INV_YEAR": str(year), "INV_WINE": "system", "INV_SANDBOX": "0",
             "INV_LOGDIR": str(self.logs), "XDG_CONFIG_HOME": str(self.home / ".config")}
        e.update(extra)
        return e

    def migrate(self, prefix, *args, year=2027, **extra):
        return subprocess.run(["bash", "scripts/migrate-prefix.sh"] + list(args), cwd=str(ROOT),
                              env=self.env(prefix, year, **extra), capture_output=True, text=True)

    def state(self, prefix):
        f = prefix / ".inventor-on-linux" / "state"
        return dict(l.split("=", 1) for l in f.read_text().splitlines()) if f.exists() else {}

    # --- whole runs ---------------------------------------------------------
    def test_old_prefix_gets_every_step(self):
        # like ~/.wine-invclean: from before migrations, last updated by wine-inventor-11.20-6
        p = self.prefix(".wine-invclean", 2026)
        out = self.migrate(p, year=2026)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        st = self.state(p)
        self.assertIn("adopted", st["done.0001-base-setup"])
        for step in ("0002-winum-runtime", "0003-x11-driver-inventor", "0004-enable-hydra"):
            self.assertIn("applied", st["done." + step], out.stdout)
        self.assertEqual(st["runtime"], "wine-11.20")
        # wineboot -u ran; isolation off here, so Wine's own updates stay disabled
        self.assertEqual((p / ".update-timestamp").read_text(), "disable\n")
        user = (p / "user.reg").read_text()
        self.assertIn("Inventor.exe\\X11 Driver|UseEGL|N", user)
        self.assertIn("Inventor.exe\\X11 Driver|ClientSideWithRender|N", user)
        # release 2026 -> RegistryVersion30.0
        self.assertIn("RegistryVersion30.0\\System\\Preferences\\Driver|EnableHydra|0x1", user)
        self.assertIn("wineboot -u", (p / "calls.log").read_text())
        self.assertTrue((p / ".inventor-on-linux/backup/0002-winum-runtime/files/user.reg").exists())
        # a second run: nothing to do
        again = self.migrate(p, year=2026)
        self.assertIn("nothing to do", again.stdout)

    def test_clean_prefix_from_today(self):
        # made with winum-11.20-1 by today's installer: runtime current, the
        # two registry steps are not in it yet
        p = self.prefix(runtime="winum")
        out = self.migrate(p)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        st = self.state(p)
        self.assertIn("already so", st["done.0002-winum-runtime"])
        self.assertNotIn("wineboot", (p / "calls.log").read_text())
        self.assertIn("applied", st["done.0003-x11-driver-inventor"])
        self.assertIn("RegistryVersion31.0\\System\\Preferences\\Driver|EnableHydra|0x1", (p / "user.reg").read_text())

    def test_prefix_with_everything_has_nothing_to_do(self):
        p = self.prefix(runtime="winum")
        k = "HKCU\\Software\\Wine\\AppDefaults\\Inventor.exe\\X11 Driver"
        (p / "user.reg").write_text("WINE REGISTRY Version 2\n%s|UseEGL|N\n%s|ClientSideWithRender|N\n"
                                    "HKCU\\Software\\Autodesk\\Inventor\\RegistryVersion31.0\\System\\Preferences\\"
                                    "Driver|EnableHydra|0x1\n" % (k, k))
        before = (p / "user.reg").read_text()
        out = self.migrate(p)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual((p / "user.reg").read_text(), before)
        self.assertTrue(all("already so" in v for k, v in self.state(p).items()
                            if k.startswith("done.") and k != "done.0001-base-setup"))
        self.assertIn("nothing to do", self.migrate(p).stdout)

    # --- failure and restore ------------------------------------------------
    def test_failing_step_is_restored_and_stops(self):
        p = self.prefix(runtime="winum")
        out = self.migrate(p, FAIL_REG_VALUE="EnableHydra")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("0004-enable-hydra failed", out.stderr)
        st = self.state(p)
        self.assertIn("done.0003-x11-driver-inventor", st)
        self.assertNotIn("done.0004-enable-hydra", st)
        # user.reg is exactly as it was after 0003: 0004's partial work is gone
        saved = (p / ".inventor-on-linux/backup/0004-enable-hydra/files/user.reg").read_text()
        self.assertEqual((p / "user.reg").read_text(), saved)
        self.assertNotIn("EnableHydra", (p / "user.reg").read_text())
        # the next run (problem gone) does 0004 only
        out = self.migrate(p)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("applied", self.state(p)["done.0004-enable-hydra"])

    def test_failing_wineboot_is_undone(self):
        p = self.prefix(".wine-invclean", 2026)
        out = self.migrate(p, year=2026, FAIL_WINEBOOT="1")
        self.assertNotEqual(out.returncode, 0)
        # the fake wineboot wrote a timestamp before failing: put back
        self.assertEqual((p / ".update-timestamp").read_text(), "disable\n")
        self.assertNotIn("runtime", self.state(p))
        self.assertNotIn("done.0002-winum-runtime", self.state(p))
        self.assertNotIn("done.0003-x11-driver-inventor", self.state(p))

    def test_runtime_check_used_by_the_launcher(self):
        def differs(prefix):
            r = subprocess.run(["bash", "-c", "source scripts/lib/common.sh >/dev/null 2>&1; "
                                "source scripts/lib/migrations.sh; prefix_runtime_differs && echo DIFFERS || echo SAME"],
                               cwd=str(ROOT), env=self.env(prefix), capture_output=True, text=True)
            return r.stdout.strip()
        old = self.prefix(".wine-inventor2026", 2026)
        made = self.prefix(".wine-inventor2027", 2027, runtime="winum")
        self.assertEqual(differs(old), "DIFFERS")      # no record, DLL copies of another Wine
        self.assertEqual(differs(made), "SAME")        # no record, made by this Wine
        self.migrate(old, year=2026)
        self.assertEqual(differs(old), "SAME")         # recorded by 0002
        # a newer winum later: the record no longer matches
        (self.rt / "BUILDINFO").write_text("winum - Fortified Wine\n\nname:        winum-11.20-2-x86_64\n")
        self.assertEqual(differs(old), "DIFFERS")

    def test_restore_by_hand(self):
        p = self.prefix(runtime="winum")
        self.assertEqual(self.migrate(p).returncode, 0)
        out = self.migrate(p, "--restore", "0003-x11-driver-inventor")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("UseEGL", (p / "user.reg").read_text())

    # --- guards ---------------------------------------------------------------
    def test_busy_prefix_is_left_alone(self):
        p = self.prefix(runtime="winum")
        proc = subprocess.Popen(["bash", "-c", 'exec -a "C:\\\\Program Files\\\\Autodesk\\\\Inventor.exe" sleep 30'],
                                env=dict(os.environ, WINEPREFIX=str(p)))
        self.addCleanup(proc.kill)
        time.sleep(0.3)
        out = self.migrate(p)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("Inventor.exe is running", out.stderr)
        self.assertEqual(self.state(p), {})

    def test_status_changes_nothing(self):
        p = self.prefix(".wine-invclean", 2026)
        out = self.migrate(p, "--status", year=2026)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("0001-base-setup (before migrations - adopted on the first run)", out.stdout)
        self.assertIn("pending   0002-winum-runtime", out.stdout)
        self.assertFalse((p / ".inventor-on-linux").exists())
        self.assertFalse((p / "calls.log").exists() and "reg add" in (p / "calls.log").read_text())

    def test_optional_step_only_by_name(self):
        p = self.prefix(runtime="winum")
        mdir = Path(self.tmp.name) / "migs"
        mdir.mkdir()
        (mdir / "0001-base-setup.sh").write_text('MIG_DESC="base"\nmig_apply() { :; }\n')
        (mdir / "0009-big.sh").write_text('MIG_DESC="big"\nMIG_OPTIONAL=1\nmig_apply() { touch "$WINEPREFIX/big-done"; }\n')
        out = self.migrate(p, INV_MIG_DIR=str(mdir))
        self.assertIn("nothing to do", out.stdout)
        self.assertFalse((p / "big-done").exists())
        out = self.migrate(p, "--run", "0009", INV_MIG_DIR=str(mdir))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue((p / "big-done").exists())

    def test_a_failing_command_inside_a_step_stops_it(self):
        # run from an `||` (as the runner does), a subshell would ignore set -e
        p = self.prefix(runtime="winum")
        mdir = Path(self.tmp.name) / "migs-fail"
        mdir.mkdir()
        (mdir / "0001-base-setup.sh").write_text('MIG_DESC="base"\nmig_apply() { :; }\n')
        (mdir / "0002-half.sh").write_text(
            'MIG_DESC="half"\nmig_apply() {\n    echo half >> "$WINEPREFIX/user.reg"\n    false\n'
            '    touch "$WINEPREFIX/after-false"\n}\n')
        before = (p / "user.reg").read_text()
        out = self.migrate(p, INV_MIG_DIR=str(mdir))
        self.assertNotEqual(out.returncode, 0, out.stdout)
        self.assertFalse((p / "after-false").exists())
        self.assertEqual((p / "user.reg").read_text(), before)
        self.assertNotIn("done.0002-half", self.state(p))

    def test_all_installed_prefixes(self):
        a = self.prefix(".wine-inventor2026", 2026, runtime="winum")
        b = self.prefix(".wine-inventor2027", 2027, runtime="winum")
        env = self.env(a)
        del env["INV_PREFIX"], env["INV_YEAR"]
        out = subprocess.run(["bash", "scripts/migrate-prefix.sh", "--all"], cwd=str(ROOT), env=env,
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("== Inventor 2026 in %s" % a, out.stdout)
        self.assertIn("RegistryVersion30.0", (a / "user.reg").read_text())
        self.assertIn("RegistryVersion31.0", (b / "user.reg").read_text())


class MigrationFilesAreNeverEdited(unittest.TestCase):
    """A change to the prefix is a new migration file, never an edit of an
    old one (AGENTS.md): every file is listed with its SHA-256 in
    scripts/lib/migrations/SHA256SUMS, and a listed file must not change."""

    def test_listed_files_unchanged_and_all_listed(self):
        sums = {}
        for line in (MIGRATIONS / "SHA256SUMS").read_text().splitlines():
            h, name = line.split(None, 1)
            sums[name.strip()] = h
        files = sorted(p.name for p in MIGRATIONS.glob("[0-9][0-9][0-9][0-9]-*.sh"))
        self.assertEqual(sorted(sums), files, "every migration is listed in SHA256SUMS (and nothing else)")
        for name in files:
            self.assertEqual(hashlib.sha256((MIGRATIONS / name).read_bytes()).hexdigest(), sums[name],
                             "%s was edited - write a new migration instead" % name)

    def test_finish_install_changes_the_prefix_only_through_migrations(self):
        text = (ROOT / "scripts" / "finish-install.sh").read_text()
        for word in ("wine_reg_add", "install_dxvk", "install_vkd3d", "cfg_disable_addins", "cfg_isolation",
                     "webview2_reg"):
            self.assertNotIn(word, text, "finish-install.sh changes the prefix outside a migration: " + word)
        self.assertIn("run_migrations --with-base", text)


if __name__ == "__main__":
    unittest.main()
