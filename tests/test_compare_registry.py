"""tools/compare-reference.py, registry: HKLM\\Software\\WOW6432Node\\Classes
(Windows export) is Wine's Software\\Classes\\Wow6432Node; keys Windows
wrote per user in HKCU\\Software\\Classes that the prefix has machine-wide
are counted apart from the missing ones. Synthetic exports."""
import subprocess
import tempfile
import unittest
from pathlib import Path

import image_fixture as fx

AFTER = ("Windows Registry Editor Version 5.00\r\n\r\n"
         "[HKEY_LOCAL_MACHINE\\SOFTWARE\\WOW6432Node\\Classes\\CLSID\\{11111111-0000-0000-0000-000000000000}]\r\n"
         "@=\"x\"\r\n\r\n"
         "[HKEY_CURRENT_USER\\Software\\Classes\\Interface\\{22222222-0000-0000-0000-000000000000}]\r\n"
         "@=\"y\"\r\n\r\n"
         "[HKEY_CURRENT_USER\\Software\\Autodesk\\Missing]\r\n\"A\"=\"1\"\r\n")
SYSTEM = ("WINE REGISTRY Version 2\n\n"
          "[Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{11111111-0000-0000-0000-000000000000}] 1\n@=\"x\"\n\n"
          "[Software\\\\Classes\\\\Interface\\\\{22222222-0000-0000-0000-000000000000}] 1\n@=\"y\"\n")


class CompareRegistry(unittest.TestCase):
    def test_wow_classes_and_per_user(self):
        with tempfile.TemporaryDirectory(prefix="inventor-compare-reg-") as d:
            d = Path(d)
            for side in ("before", "after"):
                (d / "cap" / side).mkdir(parents=True)
                (d / "cap" / side / "files.tsv").write_text("Path\tLength\tTime\n")
            (d / "cap/after/logs").mkdir()
            (d / "cap/before/hklm.reg").write_text("Windows Registry Editor Version 5.00\r\n")
            (d / "cap/after/hklm.reg").write_text(AFTER)
            (d / "pfx/drive_c").mkdir(parents=True)
            (d / "pfx/system.reg").write_text(SYSTEM)
            (d / "pfx/user.reg").write_text("WINE REGISTRY Version 2\n")
            out = subprocess.run(["python3", "-I", str(fx.ROOT / "tools/compare-reference.py"), str(d / "cap"),
                                  str(d / "pfx")], capture_output=True, text=True, check=True).stdout
            self.assertIn("missing in the prefix: 1 keys", out)
            self.assertIn("(HKLM\\Software\\Classes): 1", out)
            self.assertNotIn("wow6432node\\classes", out.lower())


if __name__ == "__main__":
    unittest.main()
