"""tools/adix-registry-names.py compares the key and value NAMES of an ADIX
package's Registry.reg with its Registry.dat. A synthetic hive (regf, the
records scripts/lib/regf.py reads) and .reg in a synthetic zip."""
import importlib.util
import io
import struct
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "adix-registry-names.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("adix_registry_names", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def hive(tree):
    """A minimal regf file. tree: (name, [value names], [subtrees])."""
    data = bytearray()

    def cell(payload):
        off = len(data)
        size = (len(payload) + 4 + 7) & ~7
        data.extend(struct.pack("<i", -size) + payload + b"\0" * (size - 4 - len(payload)))
        return off

    def vk(name):
        n = name.encode("latin-1")
        return cell(b"vk" + struct.pack("<HIIIH", len(n), 0x80000004, 1, 4, 1) + b"\0\0" + n)

    def nk(node):
        name, values, subs = node
        sub_offs = [nk(s) for s in subs]
        val_offs = [vk(v) for v in values]
        sl = cell(b"li" + struct.pack("<H", len(sub_offs)) + b"".join(struct.pack("<I", o) for o in sub_offs)) \
            if sub_offs else 0xFFFFFFFF
        vl = cell(b"".join(struct.pack("<I", o) for o in val_offs)) if val_offs else 0xFFFFFFFF
        n = name.encode("latin-1")
        rec = bytearray(0x4C)
        rec[0:2] = b"nk"
        struct.pack_into("<H", rec, 2, 0x20)
        struct.pack_into("<I", rec, 0x14, len(sub_offs))
        struct.pack_into("<I", rec, 0x1C, sl)
        struct.pack_into("<I", rec, 0x24, len(val_offs))
        struct.pack_into("<I", rec, 0x28, vl)
        struct.pack_into("<H", rec, 0x48, len(n))
        return cell(bytes(rec) + n)

    root = nk(tree)
    head = bytearray(0x1000)
    head[0:4] = b"regf"
    struct.pack_into("<I", head, 0x24, root)
    return bytes(head) + bytes(data)


DAT = hive(("ROOT", [], [("REGISTRY", [], [("MACHINE", [], [("SOFTWARE", [], [("Autodesk", [], [
    ("Materials", ["Version", "Path"], [("Library", ["Name"], [])])])])])])]))

REG_SAME = ("Windows Registry Editor Version 5.00\r\n\r\n"
            "[HKEY_LOCAL_MACHINE\\SOFTWARE\\Autodesk\\Materials]\r\n\"Version\"=\"5\"\r\n\"Path\"=\"x\"\r\n\r\n"
            "[HKEY_LOCAL_MACHINE\\SOFTWARE\\Autodesk\\Materials\\Library]\r\n\"Name\"=hex:01,02,\\\r\n  03\r\n")
REG_MORE = REG_SAME + ("\r\n[HKEY_LOCAL_MACHINE\\SOFTWARE\\Autodesk\\Materials]\r\n\"Extra\"=dword:00000001\r\n"
                       "\r\n[HKEY_CURRENT_USER\\Software\\Autodesk\\Materials]\r\n@=\"u\"\r\n"
                       "\r\n[-HKEY_LOCAL_MACHINE\\SOFTWARE\\Old]\r\n")


def adix(reg_text, encoding="utf-16"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Registry.dat", DAT)
        z.writestr("Registry.reg", reg_text.encode(encoding))
        z.writestr("Icon.png", b"png")
    return buf.getvalue()


class AdixRegistryNames(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-adix-reg-")
        self.addCleanup(self.tmp.cleanup)
        self.mod = load_tool()

    def run_tool(self, data, *args):
        p = Path(self.tmp.name) / "CM.adix"
        p.write_bytes(data)
        return subprocess.run(["python3", "-I", str(TOOL), str(p)] + list(args),
                              capture_output=True, text=True, check=True).stdout

    def test_same_names(self):
        out = self.run_tool(adix(REG_SAME))
        self.assertIn("Registry.dat: 4 keys, 3 value names; Registry.reg: 2 keys, 3 value names", out)
        self.assertIn("Registry.reg holds nothing the .dat does not have", out)

    def test_more_in_the_reg(self):
        out = self.run_tool(adix(REG_MORE, "utf-8"), "--details")
        self.assertIn("Registry.reg holds MORE than the .dat", out)
        self.assertIn("hklm\\software\\autodesk\\materials -> extra", out)
        self.assertIn("keys only in Registry.reg: 1", out)
        self.assertIn("hkcu\\software\\autodesk\\materials", out)
        self.assertIn("deletions in Registry.reg: 1", out)
        # values (data) are never printed
        self.assertNotIn("dword", out)
        self.assertNotIn('"u"', out)

    def test_msix_root_names_in_the_reg(self):
        # Material Library's Registry.reg names its keys like the hive does
        reg = REG_SAME.replace("HKEY_LOCAL_MACHINE", "REGISTRY\\MACHINE")
        out = self.run_tool(adix(reg))
        self.assertIn("Registry.reg holds nothing the .dat does not have", out)
        self.assertNotIn("only in", out)
        names, _ = self.mod.names_from_reg("[REGISTRY\\USER\\[{AppVCurrentUserSID}]\\Software\\X]\n\"a\"=\"1\"\n")
        self.assertEqual(names, {"hkcu\\software\\x": {"a"}})

    def test_dat_names(self):
        names = self.mod.names_from_dat(DAT)
        self.assertEqual(names["hklm\\software\\autodesk\\materials"], {"version", "path"})

    def test_image_folder_without_reg(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("Registry.dat", DAT)
        (Path(self.tmp.name) / "x.adix").write_bytes(buf.getvalue())
        r = subprocess.run(["python3", "-I", str(TOOL), self.tmp.name], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no ADIX package with a Registry.reg", r.stderr)


if __name__ == "__main__":
    unittest.main()
