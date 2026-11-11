""".NET Framework 4.8 prerequisite: found in an install image by its
Identity, not by a fixed path, and planned by install-from-image.py after the
product's packages.

Synthetic manifests only, in the ODIS namespace: no Autodesk files. The
installer is run with --dry-run, so no Wine is started."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
# install-from-image.py reads USER when it is loaded (the prefix's Temp folder)
os.environ.setdefault("USER", "test")
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import odis  # noqa: E402

NS = "https://emsfs.autodesk.com/schema/manifest/1/0"


def prerequisite(path, display, exe, params="/q /norestart", codes=(5100,)):
    path.parent.mkdir(parents=True, exist_ok=True)
    sc = "".join("<SuccessCode>%d</SuccessCode>" % c for c in codes)
    path.write_text(
        '<?xml version="1.0"?><Package xmlns="%s"><Identity><DisplayName>%s</DisplayName>'
        '<BuildNumber>4.8.1.0</BuildNumber></Identity><Configuration>'
        '<InstallFile type="EXE" contents="File" installParams="%s" file="%s">'
        '<InstallSuccessCodes>%s</InstallSuccessCodes></InstallFile>'
        '<Attributes ignoreFailure="true"/>'
        '<Conditions><Condition state="INSTALLED"><![CDATA[( 1 < %%REL%% )]]></Condition></Conditions>'
        '</Configuration></Package>' % (NS, display, params, exe, sc))


def image(root, with_dotnet=True, folder="3rdParty/NetFx/48"):
    (root / "manifest").mkdir(parents=True)
    (root / "manifest" / "app.inventor.xml").write_text(
        '<?xml version="1.0"?><Package xmlns="%s"><Identity><DisplayName>Inventor</DisplayName>'
        '</Identity></Package>' % NS)
    (root / "Setup.exe").write_bytes(b"")
    if with_dotnet:
        d = root / folder
        prerequisite(d / "pkg.netfx.xml", ".NET Framework Runtime 4.8", folder + "/netfx_full.exe")
        prerequisite(d / "pkg.netfx_1031.xml", ".NET Framework Runtime 4.8 Language Pack (de-DE)",
                     folder + "/netfx_lp.exe")
        (d / "netfx_full.exe").write_bytes(b"MZ")


class FindPackage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-dotnet-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_found_by_display_name_not_language_pack(self):
        image(self.root)
        s = odis.find_package(odis.Image(str(self.root)), ".NET Framework Runtime 4.8")
        self.assertIsNotNone(s)
        self.assertEqual(s["file"], "3rdParty/NetFx/48/netfx_full.exe")
        self.assertEqual(s["params"], "/q /norestart")
        self.assertEqual(s["successCodes"], [5100])
        self.assertTrue(s["present"])
        self.assertIn("%REL%", s["condition"])
        self.assertEqual(s["installAs"], "prerequisite")

    def test_other_folder(self):
        image(self.root, folder="ThirdParty/dotnet")
        s = odis.find_package(odis.Image(str(self.root)), ".NET Framework Runtime 4.8")
        self.assertEqual(s["file"], "ThirdParty/dotnet/netfx_full.exe")

    def test_absent(self):
        image(self.root, with_dotnet=False)
        self.assertIsNone(odis.find_package(odis.Image(str(self.root)), ".NET Framework Runtime 4.8"))

    def test_dry_run_plans_it_after_the_packages(self):
        image(self.root)
        prefix = self.root / "prefix"
        env = dict(os.environ, INV_LOGDIR=str(self.root / "logs"), INV_YEAR="2027")
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "install-from-image.py"),
                              str(self.root), "--prefix", str(prefix), "--dry-run"],
                             env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn(".NET Framework 4.8 (3rdParty/NetFx/48/netfx_full.exe", out.stdout)
        self.assertIn("remove Wine Mono", out.stdout)
        self.assertLess(out.stdout.index(".NET Framework 4.8 ("), out.stdout.index("All steps finished"))

    def test_dry_run_opt_out(self):
        image(self.root)
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "install-from-image.py"),
                              str(self.root), "--prefix", str(self.root / "prefix"), "--dry-run",
                              "--no-dotnet48"],
                             env=dict(os.environ, INV_LOGDIR=str(self.root / "logs")),
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("--no-dotnet48", out.stdout)
        self.assertNotIn("remove Wine Mono", out.stdout)


FAKE_WINE = """#!/bin/sh
# Answers only the query dotnet48_present makes, in the form Wine's reg.exe
# writes it (CRLF, the key first). The override is "native" when the test
# put a marker file into the prefix; "reg-error" makes it fail the way a
# wineserver of another version does.
case "$*" in
    *"reg query"*DllOverrides*mscoree*)
        if [ -f "$WINEPREFIX/reg-error" ]; then
            echo "wine client error:0: version mismatch 853/854" >&2; exit 1
        fi
        v=builtin; [ -f "$WINEPREFIX/override-native" ] && v=native
        printf '\\r\\nHKEY_CURRENT_USER\\\\Software\\\\Wine\\\\DllOverrides\\r\\n    mscoree    REG_SZ    %s\\r\\n\\r\\n' "$v" ;;
    --version) echo wine-11.20 ;;
esac
exit 0
"""


class Dotnet48Present(unittest.TestCase):
    """The shell side: dotnet48_present and inv_default_disabled_addins from
    scripts/lib/common.sh, run with a fake wine in a fake prefix."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-dotnet-sh-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.home = root / "home"
        self.prefix = self.home / ".wine-inventor2027"
        inv = self.prefix / "drive_c" / "Program Files" / "Autodesk" / "Inventor 2027" / "Bin"
        inv.mkdir(parents=True)
        (inv / "Inventor.exe").write_bytes(b"")
        self.bin = root / "bin"
        self.bin.mkdir()
        wine = self.bin / "wine"
        wine.write_text(FAKE_WINE)
        wine.chmod(0o755)

    def mscoree(self, mono=False):
        for d in ("system32", "syswow64"):
            p = self.prefix / "drive_c" / "windows" / d
            p.mkdir(parents=True, exist_ok=True)
            (p / "mscoree.dll").write_bytes(b"MZ..WINE_MONO_OVERRIDES.." if mono else b"MZ-microsoft")

    def clr(self, *frameworks):
        for fw in frameworks:
            d = self.prefix / "drive_c" / "windows" / "Microsoft.NET" / fw / "v4.0.30319"
            d.mkdir(parents=True, exist_ok=True)
            (d / "clr.dll").write_bytes(b"MZ")

    def run_finish(self):
        """cfg_disable_addins as finish-install.sh runs it: set -Eeuo pipefail,
        common.sh and configure.sh sourced, output captured."""
        env = {"HOME": str(self.home), "USER": "test", "PATH": "%s:/usr/bin:/bin" % self.bin,
               "INV_YEAR": "2027", "INV_PREFIX": str(self.prefix), "INV_WINE": "system"}
        script = ('set -Eeuo pipefail; source scripts/lib/common.sh; source scripts/lib/configure.sh; '
                  'cfg_disable_addins')
        out = subprocess.run(["bash", "-c", script], cwd=str(ROOT), env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        return out.stdout

    def addin(self, name):
        p = self.prefix / "drive_c" / "Program Files" / "Autodesk" / "Inventor 2027" / "Bin" / "Addins"
        p.mkdir(parents=True, exist_ok=True)
        (p / name).write_text("")
        return p

    def complete(self):
        self.clr("Framework64", "Framework")
        self.mscoree()
        (self.prefix / "override-native").write_bytes(b"")

    def test_finish_install_keeps_3d_pdf_on_when_complete(self):
        self.complete()
        on = self.addin("Anark.Core.addin")
        self.addin("Autodesk.Publisher.Inventor.addin")
        self.addin("autodesk.translatorfusion.inventor.addin")
        out = self.run_finish()
        self.assertTrue((on / "Anark.Core.addin").exists(), out)
        self.assertTrue((on / "Autodesk.Publisher.Inventor.addin").exists(), out)
        self.assertFalse((on / "autodesk.translatorfusion.inventor.addin").exists())
        self.assertIn(".NET Framework 4.8 in the prefix - 3D PDF (Anark, Publisher) on", out)
        self.assertIn("wine: %s/wine" % self.bin, out)
        self.assertIn("prefix: %s" % self.prefix, out)
        self.assertNotIn("Anark", out.split("off by default here:")[1].splitlines()[0])

    def test_finish_install_says_why_it_is_off(self):
        self.clr("Framework64", "Framework")
        (self.prefix / "override-native").write_bytes(b"")
        on = self.addin("Anark.Core.addin")
        out = self.run_finish()
        self.assertFalse((on / "Anark.Core.addin").exists())
        self.assertIn("not in the prefix (no windows/system32/mscoree.dll in %s)" % self.prefix, out)

    def test_finish_install_reg_query_failure_is_named(self):
        self.complete()
        (self.prefix / "reg-error").write_bytes(b"")
        self.addin("Anark.Core.addin")
        out = self.run_finish()
        self.assertIn("DllOverrides mscoree is not native", out)
        self.assertIn("version mismatch", out)
        self.assertIn("wine: %s/wine" % self.bin, out)

    def test_finish_install_moves_them_back_once_complete(self):
        self.addin("Anark.Core.addin")
        self.run_finish()
        self.complete()
        out = self.run_finish()
        on = self.prefix / "drive_c" / "Program Files" / "Autodesk" / "Inventor 2027" / "Bin" / "Addins"
        self.assertTrue((on / "Anark.Core.addin").exists(), out)
        self.assertIn("on (.NET Framework 4.8): Anark.Core.addin", out)

    def run_sh(self):
        env = {"HOME": str(self.home), "USER": "test", "PATH": "%s:/usr/bin:/bin" % self.bin,
               "INV_YEAR": "2027", "INV_PREFIX": str(self.prefix), "WINEPREFIX": str(self.prefix),
               "INV_WINE": "system"}
        script = ('source scripts/lib/common.sh >/dev/null 2>&1; '
                  'if dotnet48_present; then echo PRESENT; else echo MISSING; fi; '
                  'inv_default_disabled_addins')
        out = subprocess.run(["bash", "-c", script], cwd=str(ROOT), env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = out.stdout.split()
        return lines[0], set(lines[1:])

    def test_present_with_clr_and_native_override(self):
        self.clr("Framework64", "Framework")
        self.mscoree()
        (self.prefix / "override-native").write_bytes(b"")
        state, off = self.run_sh()
        self.assertEqual(state, "PRESENT")
        self.assertNotIn("Anark.Core.addin", off)
        self.assertNotIn("Autodesk.Publisher.Inventor.addin", off)
        self.assertIn("Autodesk.SharedViews.Inventor.addin", off)

    def test_missing_without_anything(self):
        state, off = self.run_sh()
        self.assertEqual(state, "MISSING")
        self.assertIn("Anark.Core.addin", off)
        self.assertIn("Autodesk.Publisher.Inventor.addin", off)

    def test_missing_with_clr_but_builtin_mscoree(self):
        self.clr("Framework64", "Framework")
        state, off = self.run_sh()
        self.assertEqual(state, "MISSING")
        self.assertIn("Anark.Core.addin", off)

    def test_missing_without_mscoree(self):
        # clr.dll in both, override native, no mscoree.dll: the setup was cut short
        self.clr("Framework64", "Framework")
        (self.prefix / "override-native").write_bytes(b"")
        state, off = self.run_sh()
        self.assertEqual(state, "MISSING")
        self.assertIn("Anark.Core.addin", off)

    def test_missing_with_mono_mscoree_back(self):
        self.clr("Framework64", "Framework")
        self.mscoree(mono=True)
        (self.prefix / "override-native").write_bytes(b"")
        state, _ = self.run_sh()
        self.assertEqual(state, "MISSING")

    def test_missing_with_native_override_but_one_clr(self):
        self.clr("Framework64")
        (self.prefix / "override-native").write_bytes(b"")
        state, _ = self.run_sh()
        self.assertEqual(state, "MISSING")


# A fake wine for install_dotnet48: a registry of "KEY|VALUE|DATA" lines and
# an uninstall list (printed on stderr, as Wine does) in files of the
# prefix; running the image's installer creates both clr.dll files unless
# the registry still has NDP\v4\Full (then, like the real one, it does
# nothing). Every call is appended to calls.log.
STATE_WINE = r"""#!/bin/bash
reg="$WINEPREFIX/fake-registry"; list="$WINEPREFIX/fake-uninstall"
touch "$reg" "$list"; echo "$*" >> "$WINEPREFIX/calls.log"
case "$1 $2" in
    "uninstaller --list") cat "$list" >&2; exit 0 ;;
    "uninstaller --remove") grep -v "^$3|" "$list" > "$list.n"; mv "$list.n" "$list"; exit 0 ;;
esac
if [ "$1" = reg ]; then
    key="${3,,}"
    case "$2" in
        delete) [ -f "$WINEPREFIX/reg-delete-fails" ] && exit 1
                K="$key" awk -F'|' 'index(tolower($1), ENVIRON["K"]) != 1' "$reg" > "$reg.n"; mv "$reg.n" "$reg"; exit 0 ;;
        add)    v="$5"; d="${*: -2:1}"
                K="$key" V="$v" awk -F'|' 'tolower($1) != ENVIRON["K"] || $2 != ENVIRON["V"]' "$reg" > "$reg.n"
                mv "$reg.n" "$reg"; echo "$key|$v|$d" >> "$reg"; exit 0 ;;
        query)  line="$(K="$key" V="$5" awk -F'|' 'tolower($1) == ENVIRON["K"] && $2 == ENVIRON["V"]' "$reg" | tail -1)"
                [ -n "$line" ] || exit 1
                printf '\n%s\n    %s    REG_SZ    %s\n\n' "$3" "$5" "${line##*|}"; exit 0 ;;
    esac
fi
case "$1" in
    *.exe|*.EXE)
        temp="$WINEPREFIX/drive_c/users/$USER/AppData/Local/Temp"; mkdir -p "$temp"
        if ! grep -qi '^hklm\\software\\microsoft\\net framework setup\\ndp\\v4\\full|release|' "$reg"; then
            for fw in Framework64 Framework; do
                mkdir -p "$WINEPREFIX/drive_c/windows/Microsoft.NET/$fw/v4.0.30319"
                : > "$WINEPREFIX/drive_c/windows/Microsoft.NET/$fw/v4.0.30319/clr.dll"
            done
            # "setup-killed": the files of a setup that was ended half-way
            if [ ! -f "$WINEPREFIX/setup-killed" ]; then
                for d in system32 syswow64; do echo MZ-microsoft > "$WINEPREFIX/drive_c/windows/$d/mscoree.dll"; done
                printf '<html><body><b>Final Result:</b> Installation completed successfully with success code: (0x00000000), "Success"\n</body></html>' \
                    > "$temp/Microsoft .NET Framework 4.8 Setup_20261111_000000000.html"
            fi
        fi
        exit 0 ;;
esac
exit 0
"""

NDP_FULL = r"HKLM\Software\Microsoft\NET Framework Setup\NDP\v4\Full"


def load_installer():
    import importlib.util
    spec = importlib.util.spec_from_file_location("install_from_image", ROOT / "scripts" / "install-from-image.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class InstallDotnet48(unittest.TestCase):
    """install_dotnet48 against the fake wine: removal of wine-mono, the
    NDP keys, the check before the installer, the result check."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-dotnet-run-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.img = root / "image"
        image(self.img)
        self.prefix = root / "prefix"
        (self.prefix / "drive_c" / "windows" / "system32").mkdir(parents=True)
        (self.prefix / "drive_c" / "windows" / "syswow64").mkdir(parents=True)
        for d in ("system32", "syswow64"):
            (self.prefix / "drive_c" / "windows" / d / "mscoree.dll").write_bytes(b"MZ..WINE_MONO_OVERRIDES..")
        b = root / "bin"
        b.mkdir()
        for name, text in (("wine", STATE_WINE), ("wineserver", "#!/bin/sh\nexit 0\n")):
            (b / name).write_text(text)
            (b / name).chmod(0o755)
        self.path = "%s:%s" % (b, os.environ.get("PATH", "/usr/bin:/bin"))
        # wine-mono's keys, as winum-11.20-1 writes them into a new prefix
        (self.prefix / "fake-registry").write_text(
            NDP_FULL.lower() + "|Release|0x82348\n" + NDP_FULL.lower() + "|Version|4.7.03190\n")
        self.mod = load_installer()

    def installer(self):
        import argparse
        os.environ.setdefault("USER", "test")
        a = argparse.Namespace(image=str(self.img), prefix=str(self.prefix), lang="en-US", dry_run=False,
                               no_dotnet48=False)
        old = os.environ.get("PATH")
        os.environ["PATH"] = self.path
        self.addCleanup(lambda: os.environ.__setitem__("PATH", old))
        os.environ["INV_LOGDIR"] = str(self.prefix / "logs")
        inst = self.mod.Installer(a)
        inst.env["PATH"] = self.path
        inst.DOTNET48_QUIET = 0
        inst.prefix_processes = lambda: []
        return inst

    def calls(self):
        return (self.prefix / "calls.log").read_text()

    def test_mono_entry_on_stderr_is_removed(self):
        (self.prefix / "fake-uninstall").write_text("{844FFFE4-801E-5614-B230-1A47C6191569}|||Wine Mono Windows Support\n")
        inst = self.installer()
        self.assertTrue(inst.install_dotnet48(self.mod.odis.Image(str(self.img))))
        self.assertIn("uninstaller --remove {844FFFE4-801E-5614-B230-1A47C6191569}", self.calls())
        self.assertNotIn("WINE_MONO", (self.prefix / "drive_c/windows/system32/mscoree.dll").read_text()
                         if (self.prefix / "drive_c/windows/system32/mscoree.dll").exists() else "")

    def test_built_in_mono_nothing_to_uninstall_keys_deleted(self):
        # winum carries wine-mono (share/wine/mono): no uninstall entry, but
        # NDP\v4\Full is there - it must go anyway, or the installer does nothing
        inst = self.installer()
        self.assertTrue(inst.install_dotnet48(self.mod.odis.Image(str(self.img))))
        self.assertNotIn("uninstaller --remove", self.calls())
        self.assertNotIn("ndp\\v4\\full|release", (self.prefix / "fake-registry").read_text())
        self.assertTrue((self.prefix / "drive_c/windows/Microsoft.NET/Framework64/v4.0.30319/clr.dll").exists())
        self.assertIn("native", (self.prefix / "fake-registry").read_text())
        state = (self.prefix / ".odis-install-state.json").read_text()
        self.assertIn("prerequisite:dotnet48", state)

    def test_keys_left_stop_before_the_installer(self):
        (self.prefix / "reg-delete-fails").write_bytes(b"")
        inst = self.installer()
        self.assertFalse(inst.install_dotnet48(self.mod.odis.Image(str(self.img))))
        self.assertNotIn("netfx_full.exe", self.calls())

    def test_no_files_after_installer_is_a_failure(self):
        # the installer "succeeds" (exit 0) but leaves no clr.dll: not done
        inst = self.installer()
        (self.prefix / "fake-registry").write_text("")
        wine = Path(self.path.split(":")[0]) / "wine"
        wine.write_text(STATE_WINE.replace(': > "$WINEPREFIX', 'true "$WINEPREFIX'))
        self.assertFalse(inst.install_dotnet48(self.mod.odis.Image(str(self.img))))
        self.assertFalse((self.prefix / ".odis-install-state.json").exists())


    def test_setup_cut_short_is_a_failure(self):
        # clr.dll is there but mscoree.dll and the Final Result are not: the
        # state the first clean installation of 75712cc left
        (self.prefix / "setup-killed").write_bytes(b"")
        inst = self.installer()
        self.assertFalse(inst.install_dotnet48(self.mod.odis.Image(str(self.img))))
        self.assertTrue((self.prefix / "drive_c/windows/Microsoft.NET/Framework64/v4.0.30319/clr.dll").exists())
        miss = inst.dotnet48_missing()
        self.assertIn("windows/system32/mscoree.dll", miss)
        self.assertIn("windows/syswow64/mscoree.dll", miss)
        self.assertFalse((self.prefix / ".odis-install-state.json").exists())

    def test_rerun_repairs_a_cut_short_setup(self):
        # rerunning the same command: NDP keys go again, the installer runs again
        (self.prefix / "setup-killed").write_bytes(b"")
        self.assertFalse(self.installer().install_dotnet48(self.mod.odis.Image(str(self.img))))
        (self.prefix / "setup-killed").unlink()
        reg = self.prefix / "fake-registry"
        reg.write_text(reg.read_text() + NDP_FULL.lower() + "|Release|0x80eb1\n")
        self.assertTrue(self.installer().install_dotnet48(self.mod.odis.Image(str(self.img))))
        self.assertEqual(self.installer().dotnet48_missing(), [])

    def test_waits_for_the_setup_processes(self):
        inst = self.installer()
        seen = [["setup.exe", "services.exe"], ["msiexec.exe"], ["mscorsvw.exe", "fnplicensingservice64.exe"],
                ["fnplicensingservice64.exe", "microsoftedgeupdate.exe"]]
        polls = []

        def procs():
            polls.append(1)
            return seen[min(len(polls), len(seen)) - 1]
        inst.prefix_processes = procs
        clock = [0.0]
        self.mod.time.sleep = lambda n: clock.__setitem__(0, clock[0] + n)
        self.addCleanup(lambda: setattr(self.mod.time, "sleep", __import__("time").sleep))
        real_time = self.mod.time.time
        self.mod.time.time = lambda: clock[0]
        self.addCleanup(lambda: setattr(self.mod.time, "time", real_time))
        inst.DOTNET48_QUIET = 10
        self.assertTrue(inst.wait_for_dotnet48_setup())
        # setup, msiexec and mscorsvw seen in polls 1-3; services alone do not count
        self.assertGreaterEqual(len(polls), 4)
        self.assertGreaterEqual(clock[0], 10 + 10)

    def test_wait_gives_up(self):
        inst = self.installer()
        inst.prefix_processes = lambda: ["setup.exe"]
        clock = [0.0]
        real_sleep, real_time = self.mod.time.sleep, self.mod.time.time
        self.mod.time.sleep = lambda n: clock.__setitem__(0, clock[0] + n)
        self.mod.time.time = lambda: clock[0]
        self.addCleanup(lambda: (setattr(self.mod.time, "sleep", real_sleep), setattr(self.mod.time, "time", real_time)))
        inst.DOTNET48_TIMEOUT = 60
        self.assertFalse(inst.wait_for_dotnet48_setup())

    def test_prefix_processes_reads_proc(self):
        inst = self.installer()
        del inst.prefix_processes
        env = dict(os.environ, WINEPREFIX=str(self.prefix))
        p = subprocess.Popen(["bash", "-c", 'exec -a "C:\\\\dotnet48\\\\Setup.exe" sleep 30'], env=env)
        self.addCleanup(p.kill)
        other = subprocess.Popen(["bash", "-c", 'exec -a "C:\\\\x\\\\msiexec.exe" sleep 30'],
                                 env=dict(os.environ, WINEPREFIX="/elsewhere"))
        self.addCleanup(other.kill)
        __import__("time").sleep(0.3)
        names = inst.prefix_processes()
        self.assertIn("setup.exe", names)
        self.assertNotIn("msiexec.exe", names)

    def test_final_result_must_be_success(self):
        inst = self.installer()
        temp = self.prefix / "drive_c" / "users" / os.environ["USER"] / "AppData" / "Local" / "Temp"
        temp.mkdir(parents=True)
        log = temp / "Microsoft .NET Framework 4.8 Setup_20261111_182539591.html"
        log.write_text("<html><body>Exe (...) succeeded.<br>still going</body></html>")
        self.assertIsNone(inst.dotnet48_setup_result(0))
        log.write_text('<html><b>Final Result:</b> Installation failed with error code: (0x80070643)</html>')
        self.assertNotIn("success", inst.dotnet48_setup_result(0).lower())
        log.write_text('<html><b>Final Result:</b> Installation completed successfully with success code: '
                       '(0x00000000), "Success"</html>')
        self.assertIn("Success", inst.dotnet48_setup_result(0))
        self.assertIsNone(inst.dotnet48_setup_result(__import__("time").time() + 60))


if __name__ == "__main__":
    unittest.main()
