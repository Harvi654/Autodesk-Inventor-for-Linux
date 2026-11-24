"""Synthetic prefix tests for the companion-product capture."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


TOOL = Path(__file__).resolve().parents[1] / "tools/companion-capture.py"
SPEC = importlib.util.spec_from_file_location("companion_capture", TOOL)
capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture)


SYSTEM = r'''WINE REGISTRY Version 2
#arch=win64

[Software\\Classes\\CLSID\\{native}] 12
@="Generic class"

[Software\\Classes\\CLSID\\{native}\\InprocServer32] 12
@="C:\\Windows\\System32\\mscoree.dll"
"CodeBase"="file:///C:/Users/SampleUser/NEiInventor.dll"
"Password"="private-marker"
"PublicKeyToken"="private-marker"
"ApiKey"="private-marker"
"Multi"=hex(7):41,00,00,00,\
  42,00,00,00,00,00
"Unsigned"=dword:ffffffff
"Qword"=hex(b):ff,ff,ff,ff,ff,ff,ff,ff
"Binary"=hex:0c,0d,ab
"Strange"="a|b\n100%"

[Software\\Classes\\CLSID\\{native}\\Identity] 12
@="private-marker"

[Software\\Classes\\CLSID\\{inventor}\\InprocServer32] 12
@="C:\\Program Files\\Autodesk\\Inventor 2027\\Bin\\Generic.dll"

[Software\\Classes\\Wow6432Node\\CLSID\\{wow}\\InprocServer32] 12
@="D:\\Autodesk\\Inventor Nastran 2027\\Generic.dll"

[Software\\Classes\\CLSID\\{unrelated}\\InprocServer32] 12
@="C:\\Windows\\System32\\unrelated.dll"
"Token"="Nastran private-marker"

[Software\\Classes\\TypeLib\\{lib}\\1.0] 12
@="NEi type library"

[Software\\Classes\\Interface\\{iface}] 12
@="NEWPF interface"

[Software\\Classes\\AppID\\{app}] 12
"NEProgressFlag"=dword:00000001

[Software\\Classes\\Installer\\Products\\Sensitive] 12
@="Unrelated subtype Nastran outside-scope"

[Software\\Classes\\PlainAlias] 12
@="Nastran tool"

[Software\\Classes\\PlainAlias\\CLSID] 12
@="{native}"

[Software\\Classes\\OtherProg.1\\CLSID] 12
@="{unrelated}"

[Software\\Classes\\Wow6432Node\\NEi.Prog.1\\CLSID] 12
@="{wow}"

[Software\\Classes\\NEProgress.1\\CLSID] 12
@="{native}"

[Software\\Autodesk\\Nastran\\Install] 12
"SerialNumber"="private-marker"
"InstallDir"="C:\\Program Files\\Autodesk\\Inventor Nastran 2027"
"Location"="\\\\SAMPLEHOST\\share\\SampleUser"
"Sid"="S-1-5-21-123456-456789-789123-1000"
"LicenseSettings"="private-marker"

[Software\\Autodesk\\Nastran\\Licenses] 12
@="private-marker"

[Software\\Autodesk\\IDSDK\\Nastran] 12
@="private-marker"

[Software\\Autodesk\\Inventor\\Addins] 12
"NotMachine"="outside-scope"

[System\\CurrentControlSet\\Control\\Session Manager\\Environment] 12
"Path"=str(2):" %SystemRoot%\\System32 ; C:\\Users\\SampleUser\\bin ;C:\\Autodesk\\AdskLicensing\\bin"
"SomethingElse"="outside-scope"

[System\\CurrentControlSet\\Control\\ComputerName\\ComputerName] 12
"ComputerName"="SAMPLEHOST"

[Software\\Microsoft\\.NETFramework] 12
"InstallRoot"="C:\\Windows\\Microsoft.NET\\Framework64"

[Software\\Microsoft\\.NETFramework\\Policy\\v4.0] 12
"30319"="4.0.30319"

[Software\\Microsoft\\.NETFramework\\Policy\\v2.0] 12
"OutOfScope"="outside-scope"

[Software\\Wow6432Node\\Microsoft\\Fusion] 12
"LogFailures"=dword:00000001
'''

USER = r'''WINE REGISTRY Version 2

[Software\\Classes\\NEWPFUI.NEWPFUIImpl] 10
@="Main ProgID"

[Software\\Classes\\NEWPFUI.NEWPFUIImpl\\CLSID] 10
@="{native}"

[Software\\Autodesk\\Inventor\\RegistryVersion31.0\\AddIns\\{managed}] 10
"LoadOnStartUp"=dword:00000001

[Software\\Autodesk\\Inventor\\RegistryVersion30.0\\AddIns] 10
@="outside-scope"

[Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Shell Folders] 10
"AppData"="C:\\Users\\SampleUser\\AppData\\Roaming"

[Environment] 10
"Path"="C:\\Users\\SampleUser\\bin;;C:\\tools"
"Temp"="outside-scope"
'''


class CompanionCaptureTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.prefix = Path(temp.name)
        self.drive = self.prefix / "drive_c"
        self.drive.mkdir()
        (self.prefix / "system.reg").write_text(SYSTEM, encoding="utf-8")
        (self.prefix / "user.reg").write_text(USER, encoding="utf-8")

    def file(self, path, payload=b"synthetic fixture"):
        file = self.drive / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(payload)
        return file

    def test_registry_scope_and_masking(self):
        text = "\n".join(capture.capture(self.prefix))
        for item in ("{native}", "{inventor}", "{wow}", "{lib}", "{iface}", "{app}", "nei.prog.1",
                     "neprogress.1", "newpfui.newpfuiimpl", "{managed}", "policy\\v4.0",
                     "wow6432node\\microsoft\\fusion", "plainalias"):
            self.assertIn(item, text)
        for item in ("private-marker", "outside-scope", "sampleuser", "samplehost", "S-1-5-21",
                     "{unrelated}", "adsklicensing", "idsdk", "\\identity", "\\licenses", "v2.0"):
            self.assertNotIn(item.lower(), text.lower())
        for name in ("password", "publickeytoken", "apikey", "serialnumber", "licensesettings"):
            self.assertIn(f" | {name} | REG_SZ | <masked>", text)
        self.assertIn(r"file:///<profile>/NEiInventor.dll", text)
        self.assertIn(r"\\<machine>\share\<user>", text)
        self.assertIn(" | sid | REG_SZ | <sid>", text)
        self.assertIn(" | multi | REG_MULTI_SZ | A ; B", text)
        self.assertIn(" | unsigned | REG_DWORD | 4294967295", text)
        self.assertIn(" | qword | REG_QWORD | 18446744073709551615", text)
        self.assertIn(" | binary | REG_BINARY | 0c0dab", text)
        self.assertIn(" | strange | REG_SZ | a%7Cb%0A100%25", text)
        self.assertIn(r"%25SystemRoot%25\System32 ; <profile>\bin ; <masked>", text)
        self.assertIn(r"<profile>\bin ;  ; C:\tools", text)

    def test_wine_saved_product_key_and_control_set(self):
        # Section and metadata layout emitted by Wine 11.22 for a synthetic reg add.
        reg = self.prefix / "system.reg"
        reg.write_text(r"""WINE REGISTRY Version 2
;; All keys relative to REGISTRY\\Machine

#arch=win64

[Software\\Autodesk\\Autodesk Inventor Nastran 2027\\2027.0.0\\AppInfo] 1795477316
#time=1dd7ba43a0ef50e
"DisplayName"="Nastran fixture"
"Components"=str(7):"Engine\0UI\0"
"Legacy spacing" = "read me"
"Escaped"="one\001two\e"
[Software\\Autodesk\\Autodesk Inventor Nastran 2027\\2027.0.0\\Panel \[fixture\]] 1795477316
#time=1dd7ba43a0ef50e
@="Panel"

[System\\ControlSet001\\Control\\Session Manager\\Environment] 1795477316
#time=1dd7ba439aac93a
"Path"=str(2):"C:\\active"
[System\\ControlSet002\\Control\\Session Manager\\Environment] 1795477316
"Path"=str(2):"C:\\inactive"
[System\\CurrentControlSet] 1795477316
#link
[System\\Select] 1795477316
"Current"=dword:00000001
""", encoding="utf-8")
        rows = set(capture.capture(self.prefix))
        appinfo = (r"REG HKLM\software\autodesk\autodesk inventor nastran 2027"
                   r"\2027.0.0\appinfo")
        self.assertIn(appinfo + " | displayname | REG_SZ | Nastran fixture", rows)
        self.assertIn(appinfo + " | components | REG_MULTI_SZ | Engine ; UI", rows)
        self.assertIn(appinfo + " | legacy spacing | REG_SZ | read me", rows)
        self.assertIn(appinfo + " | escaped | REG_SZ | one%01two%1B", rows)
        self.assertIn(appinfo.removesuffix("appinfo") +
                      "panel [fixture] |  | REG_SZ | Panel", rows)
        env_row = r"REG HKLM\system\currentcontrolset\control\session manager\environment"
        self.assertIn(env_row + r" | path | REG_EXPAND_SZ | C:\active", rows)
        self.assertFalse(any("inactive" in row or "controlset001" in row for row in rows))

    def test_size_hash_names_only_and_link_exclusion(self):
        shared = "ProgramData/Autodesk/Inventor 2027/AddIns"
        user = "Users/SampleUser/AppData/Roaming/Autodesk/Inventor 2027/Addins"
        product = "Program Files/Autodesk/Inventor Nastran 2027"
        gac = "Windows/Microsoft.NET/assembly/GAC_MSIL"
        paths = [self.file(f"{shared}/Shared.Addin"), self.file(f"{user}/User.Addin"),
                 self.file(f"{product}/Bin/NEi.dll")]
        never_hash = [self.file(f"{gac}/NEWPFUI/v4/NEWPFUI.dll"),
                      self.file("Windows/assembly/GAC_MSIL/NEi.Core/v2/fixture.dll"),
                      self.file(f"{gac}/Generic/v4/Generic.dll"),
                      self.file(f"{product}/Licenses/local.lic")]
        (paths[0].parent / "external.addin").symlink_to(never_hash[0])
        with patch.object(capture, "digest", wraps=capture.digest) as digest:
            rows = list(capture.capture(self.prefix))
        self.assertCountEqual([call.args[0] for call in digest.call_args_list], paths)
        sha = hashlib.sha256(b"synthetic fixture").hexdigest()
        self.assertIn(f"FILE <profile>/appdata/roaming/autodesk/inventor 2027/addins/user.addin | 17 | {sha}", rows)
        for file in never_hash[:2]:
            self.assertIn(f"FILE {file.relative_to(self.drive).as_posix().lower()} | - | -", rows)
        self.assertFalse(any("generic.dll" in row and row.startswith("FILE ") for row in rows))
        self.assertFalse(any("local.lic" in row or "external.addin" in row for row in rows))

    def test_fusion_only_whitelisted_fields_and_names(self):
        self.file("fusionlog/Default/SampleUser.HTM", '''<pre>
LOG: DisplayName = SharedViews &amp; More
Calling assembly : NEWPF, C:\\Users\\SampleUser\\NEWPFUI.dll
Bind result: hr = 0x80070002
LOG: Appbase = private-marker
</pre>
'''.encode("utf-16"))
        self.file("fusionlog/Empty.HTM", b"LOG: Appbase = private-marker")
        self.file("fusionlog/identity/hidden.htm", b"Bind result: private-marker")
        self.assertFalse(any(row.startswith("FUSION ") for row in capture.capture(self.prefix)))
        rows = sorted(row for row in capture.capture(self.prefix, include_fusion=True)
                      if row.startswith("FUSION "))
        self.assertEqual(rows, [
            "FUSION default/<user>.htm | bind result | hr = 0x80070002",
            r"FUSION default/<user>.htm | calling assembly | NEWPF, <profile>\NEWPFUI.dll",
            "FUSION default/<user>.htm | displayname | SharedViews & More",
            "FUSION default/<user>.htm | file | ",
            "FUSION empty.htm | file | ",
        ])

    def test_compare_groups_and_limits(self):
        previous = self.prefix / "old.txt"
        current = self.prefix / "new.txt"
        previous.write_text("REG HKCU\\software\\classes\\clsid\\{a} | name | REG_SZ | old\n"
                            "FILE data/removed.dll | 1 | a\n", encoding="utf-8")
        current.write_text("REG HKCU\\software\\classes\\clsid\\{a} | name | REG_SZ | new\n"
                           + "".join(f"FILE data/added-{i:02}.dll | 1 | b\n" for i in range(47)),
                           encoding="utf-8")
        groups = capture.comparison(capture.read_capture(previous), capture.read_capture(current))
        screen, full = io.StringIO(), io.StringIO()
        capture.report(groups, screen, 40)
        capture.report(groups, full)
        self.assertIn("[FILE data] added=47 removed=1 changed=0", screen.getvalue())
        self.assertIn("... 8 more changes", screen.getvalue())
        self.assertNotIn("removed.dll", screen.getvalue())
        self.assertIn("- FILE data/removed.dll", full.getvalue())
        self.assertIn(r"[REG HKCU\software\classes\clsid] added=0 removed=0 changed=1", full.getvalue())


if __name__ == "__main__":
    unittest.main()
