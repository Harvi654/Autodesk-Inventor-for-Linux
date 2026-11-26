"""Runs nix/post-install.sh (the Nix installation's prefix setup) on a fake
prefix, with stub wine and wineserver programs that record what they were
asked to do."""
import os
import sys
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "nix" / "post-install.sh"


class PostInstall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-post-install-")
        self.root = Path(self.tmp.name)
        self.prefix = self.root / "prefix"
        self.c = self.prefix / "drive_c"
        self.year = "2027"
        inv = self.c / f"Program Files/Autodesk/Inventor {self.year}"
        (inv / "Bin/Addins").mkdir(parents=True)
        (inv / "Bin/CER").mkdir()
        (inv / "Bin/Inventor.exe").write_text("exe")
        (inv / "Bin/CER/senddmp.exe").write_text("exe")
        for name in ["Autodesk.AssistantAddin.Inventor.addin", "Autodesk.SharedViews.Inventor.addin"]:
            (inv / "Bin/Addins" / name).write_text("addin")
        lic = self.c / "Program Files (x86)/Common Files/Autodesk Shared/AdskLicensing"
        (lic / "15.1.0.1/AdskLicensingAgent").mkdir(parents=True)
        (lic / "15.1.0.1/AdskLicensingSDK").mkdir()
        (lic / "Current?").mkdir()
        idmgr = self.c / "Program Files/Autodesk/AdskIdentityManager"
        (idmgr / "1.2.3/SSOPlugin/Current").mkdir(parents=True)
        (idmgr / "1.2.3/SSOPlugin/Current/IdSDKPlugin.dll").write_text("dll")
        (self.c / f"Program Files/Common Files/Autodesk Shared/Components/{self.year}/29.0.1").mkdir(parents=True)
        (self.c / f"Program Files/Common Files/Autodesk Shared/RealDWG Shared {self.year}").mkdir(parents=True)
        (self.c / "windows/system32").mkdir(parents=True)
        (self.c / "windows/system32/bcp47langs.dll").write_text("dll")
        (self.prefix / "dosdevices").mkdir()
        (self.prefix / "dosdevices/m:").symlink_to(self.root)
        self.calls = self.root / "wine.log"
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        # The wine stub logs every call. `reg add` stores the value in a small
        # database, and `reg query` answers from it in the format Wine prints.
        self.db = self.root / "registry.tsv"
        self.db.write_text("")
        wine = bin_dir / "wine"
        wine.write_text(f"""#!{sys.executable}
import sys
args = sys.argv[1:]
with open({str(self.calls)!r}, "a") as log:
    log.write(" ".join(args) + "\\n")
def opt(name):
    return args[args.index(name) + 1] if name in args else ""
if args[:2] == ["reg", "add"]:
    data, kind = opt("/d"), opt("/t") or "REG_SZ"
    if kind == "REG_DWORD":
        data = hex(int(data))
    with open({str(self.db)!r}, "a") as db:
        db.write("\\t".join((args[2].lower(), opt("/v").lower(), kind, data)) + "\\n")
elif args[:2] == ["reg", "query"]:
    found = None
    for line in open({str(self.db)!r}):
        key, name, kind, data = line.rstrip("\\n").split("\\t")
        if key == args[2].lower() and name == opt("/v").lower():
            found = (kind, data)
    if found is None:
        sys.exit(1)
    print("\\r\\n%s\\r\\n    %s    %s    %s\\r\\n" % (args[2], opt("/v"), found[0], found[1]))
""")
        wine.chmod(0o755)
        server = bin_dir / "wineserver"
        server.write_text(f"#!{shutil.which('bash')}\nprintf 'wineserver %s\\n' \"$*\" >> {self.calls}\n")
        server.chmod(0o755)
        self.env = dict(os.environ, WINEPREFIX=str(self.prefix), INV_YEAR=self.year, USER="nixbld",
                        PATH=str(bin_dir) + os.pathsep + os.environ["PATH"])

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self):
        return subprocess.run(["bash", str(SCRIPT)], env=self.env, capture_output=True, text=True)

    def test_sets_up_the_prefix(self):
        out = self.run_script()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        inv = self.c / f"Program Files/Autodesk/Inventor {self.year}"
        lic = self.c / "Program Files (x86)/Common Files/Autodesk Shared/AdskLicensing"
        self.assertEqual(os.readlink(lic / "Current"), "15.1.0.1")
        self.assertFalse((lic / "Current?").exists())
        self.assertEqual(os.readlink(lic / "CurrentSDK"), "15.1.0.1/AdskLicensingSDK")
        agent = lic / "15.1.0.1/AdskLicensingAgent"
        self.assertTrue((agent / "SSOPlugin/Current/IdSDKPlugin.dll").is_file())
        self.assertIn("IdSDKPlugin.dll", (agent / "IDSDKVersionCompatibility.config").read_text())
        self.assertTrue((inv / "Addins.disabled/Autodesk.AssistantAddin.Inventor.addin").is_file())
        self.assertTrue((inv / "Bin/Addins/Autodesk.SharedViews.Inventor.addin").is_file())
        self.assertTrue((inv / "Bin/CER/senddmp.exe.disabled").is_file())
        self.assertTrue((self.c / "windows/system32/bcp47langs.dll.disabled").is_file())
        self.assertFalse((self.prefix / "dosdevices/m:").is_symlink())
        rdwg = self.c / f"users/nixbld/AppData/Roaming/Autodesk/Inventor {self.year}/RealDWGSettings.xml"
        data = rdwg.read_bytes()
        self.assertTrue(data.startswith(b"\xff\xfe"))
        self.assertIn(f'InstallDirectory="C:\\Program Files\\Common Files\\Autodesk Shared\\RealDWG Shared {self.year}"',
                      data[2:].decode("utf-16-le"))
        calls = self.calls.read_text()
        self.assertIn(f"SharedComponents\\{self.year} /v Version /t REG_EXPAND_SZ /d 29.0.1", calls)
        self.assertIn("Services\\AdskLicensingService /v Start /t REG_DWORD /d 3", calls)
        # Path names the version-independent Current link, which points at
        # the installed Shared Components version
        self.assertIn(f"Components\\{self.year}\\Current;C:\\Program Files\\Autodesk\\Inventor {self.year}\\Bin", calls)
        asc = self.c / f"Program Files/Common Files/Autodesk Shared/Components/{self.year}"
        self.assertEqual(os.readlink(asc / "Current"), "29.0.1")

    def test_runs_twice(self):
        self.assertEqual(self.run_script().returncode, 0)
        out = self.run_script()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_fails_without_licensing(self):
        shutil.rmtree(self.c / "Program Files (x86)/Common Files/Autodesk Shared/AdskLicensing")
        out = self.run_script()
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("no AdskLicensing", out.stdout)


    def test_keeps_a_junction_with_contents(self):
        lic = self.c / "Program Files (x86)/Common Files/Autodesk Shared/AdskLicensing"
        (lic / "Current?/kept.txt").write_text("x")
        out = self.run_script()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue((lic / "Current?/kept.txt").is_file())
        self.assertIn("is not empty - left alone", out.stdout)

    def test_fixes_unexpanded_public_paths(self):
        (self.prefix / "system.reg").write_text(
            'WINE REGISTRY Version 2\n\n'
            '[Software\\\\Autodesk\\\\TaskScheduler] 1\n'
            '"LogFile"="%PUBLIC%\\\\Documents\\\\log.txt"\n'
            '"Other"=str(2):"%PUBLIC%\\\\x"\n\n'
            '[Software\\\\Wow6432Node\\\\Microsoft\\\\Windows\\\\HTML Help] 1\n'
            '@="%PUBLIC%\\\\Documents\\\\help.chm"\n')
        out = self.run_script()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        calls = self.calls.read_text()
        self.assertIn("reg add HKLM\\Software\\Autodesk\\TaskScheduler /v LogFile /t REG_SZ "
                      "/d C:\\users\\Public\\Documents\\log.txt /f", calls)
        self.assertNotIn("/v Other", calls)
        # a default value (@) keeps its empty name: /ve, not a named value
        self.assertIn("reg add HKLM\\Software\\Wow6432Node\\Microsoft\\Windows\\HTML Help /ve /t REG_SZ "
                      "/d C:\\users\\Public\\Documents\\help.chm /f", calls)

    def test_fails_when_a_value_does_not_stick(self):
        wine = Path(self.env["PATH"].split(os.pathsep)[0]) / "wine"
        wine.write_text(wine.read_text().replace("hex(int(data))", "'0x9' if True else data"))
        out = self.run_script()
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("expected '0x3'", out.stdout)

    def test_stops_wine(self):
        self.assertEqual(self.run_script().returncode, 0)
        lines = self.calls.read_text().splitlines()
        self.assertEqual(lines[0], "wineserver -k")
        self.assertEqual(lines[-2:], ["wineserver -k", "wineserver --wait"])


    def test_a_lingering_wine_child_does_not_hang_it(self):
        # `wine reg query` starts a service that keeps the inherited stdout
        # open and outlives it, as licensing or Edge update do under Wine
        wine = Path(self.env["PATH"].split(os.pathsep)[0]) / "wine"
        wine.write_text(wine.read_text().replace(
            'elif args[:2] == ["reg", "query"]:\n',
            'elif args[:2] == ["reg", "query"]:\n'
            '    import subprocess; subprocess.Popen(["sleep", "60"])\n'))
        out = subprocess.run(["bash", str(SCRIPT)], env=self.env, capture_output=True, text=True, timeout=40)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


    def test_turns_off_the_assistant_in_programdata(self):
        # 2027.2 and later keep the Assistant's .addin file in ProgramData, in
        # a folder per version (migration 0013); another add-in stays on
        pd = self.c / f"ProgramData/Autodesk/Inventor {self.year}/Addins"
        (pd / "Assistant/31.20.33400").mkdir(parents=True)
        (pd / "Assistant/31.20.33400/Autodesk.AssistantAddin.Inventor.addin").write_text("addin")
        (pd / "Assistant/31.20.33400/AutodeskAssistantAddin.dll").write_text("dll")
        (pd / "Other").mkdir()
        (pd / "Other/Other.Inventor.addin").write_text("addin")
        out = self.run_script()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        inv = self.c / f"Program Files/Autodesk/Inventor {self.year}"
        off = inv / "Addins.disabled/programdata/Assistant/31.20.33400/Autodesk.AssistantAddin.Inventor.addin"
        self.assertTrue(off.is_file())
        self.assertFalse((pd / "Assistant/31.20.33400/Autodesk.AssistantAddin.Inventor.addin").exists())
        self.assertTrue((pd / "Assistant/31.20.33400/AutodeskAssistantAddin.dll").is_file())
        self.assertTrue((pd / "Other/Other.Inventor.addin").is_file())

    def test_leaves_an_assistant_copy_that_is_already_off(self):
        pd = self.c / f"ProgramData/Autodesk/Inventor {self.year}/Addins/Assistant/1.0"
        pd.mkdir(parents=True)
        (pd / "Autodesk.AssistantAddin.Inventor.addin").write_text("on")
        inv = self.c / f"Program Files/Autodesk/Inventor {self.year}"
        off = inv / "Addins.disabled/programdata/Assistant/1.0"
        off.mkdir(parents=True)
        (off / "Autodesk.AssistantAddin.Inventor.addin").write_text("off")
        out = self.run_script()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual((pd / "Autodesk.AssistantAddin.Inventor.addin").read_text(), "on")
        self.assertEqual((off / "Autodesk.AssistantAddin.Inventor.addin").read_text(), "off")

if __name__ == "__main__":
    unittest.main()
