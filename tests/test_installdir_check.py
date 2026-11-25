"""tools/installdir-check.py: INSTALLDIR of Windows' MSI command lines next
to each MSI package's installLocation (does ODIS pass %INSTALL_DEST% to
MSIs without one?). Synthetic image and MSI logs."""
import subprocess
import tempfile
import unittest
from pathlib import Path

import image_fixture as fx

TOOL = fx.ROOT / "tools" / "installdir-check.py"


def msi_log(product, cmdline):
    return ("=== Verbose logging started: 11/15/2026  22:47:00  Build type: SHIP UNICODE 5.00.10011.00 ===\n"
            "MSI (s) (00:00) [22:47:00:000]: ******* Product: C:\\ProgramData\\cache\\%s\n"
            "MSI (s) (00:00) [22:47:00:000]: Command Line: %s\n" % (product, cmdline))


class InstallDirCheck(unittest.TestCase):
    def build(self, hive_dir, other_dir):
        t = Path(self.tmp.name)
        img, cap = t / "image", t / "cap"
        fx.write(img, "manifest/app.inventor.xml", fx.app_xml("Inventor 2027", [
            ("HIVE", "x64/hive/pkg.hive.xml", ""), ("Other", "x64/o/pkg.o.xml", ""),
            ("InvPrivate", "x64/inv/pkg.inv.xml", "")]))
        fx.write(img, "x64/hive/pkg.hive.xml", fx.package_xml("Hive", "MSI", "x64/hive/adsk-hive-host.msi"))
        fx.write(img, "x64/o/pkg.o.xml", fx.package_xml("Other", "MSI", "x64/o/other.msi"))
        fx.write(img, "x64/inv/pkg.inv.xml", fx.package_xml("Inv", "MSI", "x64/inv/InvPrivate.msi",
                                                            install_location="%INV_INSTALL_PATH%"))
        fx.write(cap, "after/logs/a.log", msi_log("adsk-hive-host.msi", "ADSK_ODIS_SETUP=1 INSTALLDIR=" + hive_dir))
        fx.write(cap, "after/logs/b.log", msi_log("other.msi", "ADSK_ODIS_SETUP=1 INSTALLDIR=" + other_dir))
        fx.write(cap, "after/logs/c.log", msi_log(
            "InvPrivate.msi", r"MSIFASTINSTALL=7 INSTALLDIR=C:\Program Files\Autodesk\Inventor 2027\ REBOOT=ReallySuppress"))
        return subprocess.run(["python3", "-I", str(TOOL), str(cap), str(img)],
                              capture_output=True, text=True, check=True).stdout

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-installdir-check-")
        self.addCleanup(self.tmp.cleanup)

    def test_all_get_install_dest(self):
        out = self.build(r"C:\Program Files\Autodesk", "C:\\Program Files\\Autodesk\\")
        self.assertIn(r"| HIVE | adsk-hive-host.msi | - | C:\Program Files\Autodesk |", out)
        self.assertIn(r"| InvPrivate | InvPrivate.msi | %INV_INSTALL_PATH% | C:\Program Files\Autodesk\Inventor 2027\ |",
                      out)
        self.assertIn("MSI packages without an installLocation: 2", out)
        self.assertIn("Verdict: every one Windows ran got INSTALLDIR = %INSTALL_DEST%", out)

    def test_different(self):
        out = self.build(r"C:\Program Files\Autodesk", r"C:\Program Files\Other")
        self.assertIn("Verdict: not the same for all", out)


if __name__ == "__main__":
    unittest.main()
