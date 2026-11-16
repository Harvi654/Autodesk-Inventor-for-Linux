"""INV_DXVK=none / INV_VKD3D=none: the prefix gets no DXVK or vkd3d-proton.

The Nix package installs Inventor this way and adds both as layers at
launch; the prefix must then hold neither their DLLs nor their overrides.
"""
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def run(script, **env):
    with tempfile.TemporaryDirectory() as tmp:
        prefix = pathlib.Path(tmp) / "prefix"
        for d in ("drive_c/windows/system32", "drive_c/windows/syswow64"):
            (prefix / d).mkdir(parents=True)
        full_env = {
            "PATH": os.environ["PATH"],
            "HOME": tmp,
            "INV_PREFIX": str(prefix),
            "DOWNLOAD_DIR": str(pathlib.Path(tmp) / "downloads"),
            **env,
        }
        r = subprocess.run(
            ["bash", "-c",
             "source scripts/lib/common.sh >/dev/null 2>&1; "
             'P_C="$INV_PREFIX/drive_c"; LOGDIR="$HOME"; '
             'wine_reg_add() { echo "REG $*"; }; '
             'curl() { echo "CURL $*"; return 1; }; '
             + script],
            cwd=str(ROOT), env=full_env, capture_output=True, text=True)
        files = sorted(str(p.relative_to(prefix)) for p in prefix.rglob("*") if p.is_file())
        return r, files


class GraphicsNone(unittest.TestCase):
    def test_none_installs_nothing(self):
        r, files = run("install_dxvk; install_vkd3d", INV_DXVK="none", INV_VKD3D="none")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(files, [])
        self.assertNotIn("CURL", r.stdout)
        regs = [line for line in r.stdout.splitlines() if line.startswith("REG ")]
        # Only Inventor's own d3dcompiler_47, which is not DXVK's.
        self.assertEqual(len(regs), 1, regs)
        self.assertIn("d3dcompiler_47", regs[0])
        self.assertIn("native", regs[0])

    def test_labels(self):
        r, _ = run('echo "$(dxvk_label)|$(vkd3d_label)"', INV_DXVK="none", INV_VKD3D="none")
        self.assertEqual(r.stdout.strip().splitlines()[-1], "provided elsewhere|provided elsewhere")
        r, _ = run('echo "$(dxvk_label)|$(vkd3d_label)"', INV_VKD3D="off")
        self.assertEqual(r.stdout.strip().splitlines()[-1], "2.7.1, pinned|off")


if __name__ == "__main__":
    unittest.main()
