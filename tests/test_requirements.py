"""Disk space per filesystem and the memory thresholds of the interactive
front ends (scripts/lib/requirements.py, requirements.env). Fake st_dev and
statvfs, fake /proc/meminfo (INV_MEMINFO): runs in the Nix sandbox."""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
GIB = 1024 ** 3


def load_module():
    spec = importlib.util.spec_from_file_location("requirements", ROOT / "scripts" / "lib" / "requirements.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class DiskPerFilesystem(unittest.TestCase):
    def setUp(self):
        self.r = load_module()
        self.req = self.r.load()
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-req-")
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.home, self.nvme = t / "home", t / "nvme"
        for d in (self.home / ".cache", self.home / ".local/share", self.home / "project", self.nvme):
            d.mkdir(parents=True)
        # two filesystems: everything under home/ (dev 1), nvme/ (dev 2)
        self.free = {1: 100.0, 2: 15.0}

    def dev(self, p):
        p = str(p)
        if p.startswith(str(self.home)):
            return 1
        if p.startswith(str(self.nvme)):
            return 2
        return 0

    def stat(self, p):
        return SimpleNamespace(st_dev=self.dev(p))

    def statvfs(self, p):
        return SimpleNamespace(f_bavail=int(self.free[self.dev(p)] * GIB / 4096), f_frsize=4096)

    def paths(self, prefix):
        return {"prefix": str(prefix), "cache": str(self.home / ".cache/inventor-on-linux/media"),
                "wine": str(self.home / ".local/share/inventor-on-linux"),
                "downloads": str(self.home / "project/downloads")}

    def plan(self, prefix, **kw):
        return self.r.disk_plan(self.paths(prefix), self.req, stat=self.stat, statvfs=self.statvfs, **kw)

    def test_numbers(self):
        self.assertEqual((self.req["REQ_PREFIX_GB"], self.req["REQ_PREFIX_NO_CONTENT_GB"], self.req["REQ_MEDIA_GB"],
                          self.req["REQ_WINE_GB"] + self.req["REQ_DOWNLOADS_GB"], self.req["REQ_CONTENT_GB"],
                          self.req["REQ_MARGIN"]), (20, 13, 11, 1.5, 7.5, 0.10))

    def test_all_on_one_disk_is_added_up(self):
        plan = self.plan(self.home / ".wine-inventor2027")
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["kinds"], ["prefix", "cache", "wine", "downloads"])
        self.assertAlmostEqual(plan[0]["needed"], (20 + 11 + 1 + 0.5) * 1.1)
        self.assertTrue(plan[0]["ok"])
        self.assertEqual(plan[0]["mount"], str(self.home))
        self.free[1] = 35.0
        self.assertFalse(self.plan(self.home / ".wine-inventor2027")[0]["ok"])

    def test_prefix_on_another_disk_is_checked_there(self):
        # the prefix folder does not exist yet: its parent's filesystem counts
        plan = self.plan(self.nvme / "inventor" / "prefix2027")
        self.assertEqual([d["kinds"] for d in plan], [["prefix"], ["cache", "wine", "downloads"]])
        pre, rest = plan
        self.assertAlmostEqual(pre["needed"], 22.0)
        self.assertFalse(pre["ok"])
        self.assertAlmostEqual(rest["needed"], 12.5 * 1.1)
        self.assertTrue(rest["ok"])
        self.assertEqual(self.r.describe(pre), "prefix disk %s: 22 GB needed, 15 GB free" % self.nvme)
        # without Content Center: 13 GB * 1.1 = 14.3, fits in 15
        self.assertTrue(self.plan(self.nvme / "p", content=False)[0]["ok"])

    def test_media_and_wine_only_when_needed(self):
        plan = self.plan(self.home / "p", media=False, wine=False)
        self.assertEqual(plan[0]["kinds"], ["prefix", "downloads"])
        self.assertAlmostEqual(plan[0]["needed"], 20.5 * 1.1)

    def test_repair_needs_little(self):
        plan = self.plan(self.nvme / "p", repair=True)
        self.assertEqual(len(plan), 1)
        self.assertAlmostEqual(plan[0]["needed"], 2 * 1.1)
        self.assertTrue(plan[0]["ok"])

    def test_cli_on_real_folders(self):
        out = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/lib/requirements.py"), "disk",
                              "--prefix", str(self.nvme / "p"), "--cache", str(self.home), "--wine-dir",
                              str(self.home), "--downloads", str(self.home), "--repair"],
                             capture_output=True, text=True)
        self.assertIn(out.returncode, (0, 1), out.stderr)
        self.assertRegex(out.stdout, r"^(ok|short)\tprefix disk .*: 2 GB needed, \d+ GB free\n$")


class Memory(unittest.TestCase):
    def setUp(self):
        self.r = load_module()
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-mem-")
        self.addCleanup(self.tmp.cleanup)

    def meminfo(self, kb):
        p = Path(self.tmp.name) / ("meminfo-%d" % kb)
        p.write_text("MemTotal:       %d kB\nMemFree:         123456 kB\n" % kb)
        return str(p)

    def test_thresholds(self):
        # what machines report: 32 GB, 16 GB (about 15.5 GiB), 8 GB, 4 GB
        cases = [(32_786_000, "ok"), (16_303_216, "ok"), (15_000_000, "warn"),
                 (7_969_000, "warn"), (7_800_000, "low"), (3_900_000, "low")]
        for kb, level in cases:
            self.assertEqual(self.r.mem_check(path=self.meminfo(kb))[0], level, kb)
        text = self.r.mem_check(path=self.meminfo(7_969_000))[1]
        self.assertIn("16 GB or more recommended; with 8 GB Inventor starts but is not usable for work", text)

    def test_unreadable_is_not_a_stop(self):
        self.assertEqual(self.r.mem_check(path=str(Path(self.tmp.name) / "none"))[0], "ok")

    def test_from_the_shell_with_inv_meminfo(self):
        env = dict(os.environ, INV_MEMINFO=self.meminfo(7_969_000), HOME=self.tmp.name)
        out = subprocess.run(["bash", "-c", 'source scripts/lib/common.sh >/dev/null 2>&1; '
                              'echo "$REQ_RAM_GIB $REQ_PREFIX_GB"; inv_requirements mem'],
                             cwd=str(ROOT), env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = out.stdout.splitlines()
        self.assertEqual(lines[0], "15 20")
        self.assertTrue(lines[1].startswith("warn\tmemory: 7.6 GiB - 16 GB or more recommended"), lines[1])


class OnlyTheFrontEnds(unittest.TestCase):
    def test_nix_build_path_does_not_check(self):
        # install-from-image.py and finish-install.sh run in the Nix build
        for f in ("scripts/install-from-image.py", "scripts/finish-install.sh"):
            text = (ROOT / f).read_text()
            self.assertNotIn("inv_requirements", text, f)
            self.assertNotIn("meminfo", text, f)

    def test_front_ends_use_the_shared_numbers(self):
        for f in ("scripts/install.sh", "scripts/check-system.sh"):
            text = (ROOT / f).read_text()
            self.assertIn("inv_requirements mem", text, f)
            self.assertIn("inv_requirements disk", text, f)
            self.assertNotIn("df ", text, f)
        gui = (ROOT / "scripts/gui/installer.py").read_text()
        self.assertIn("requirements.disk_plan", gui)
        self.assertIn("requirements.mem_check", gui)
        self.assertNotIn("disk_usage", gui)
        for f in ("scripts/install.sh", "scripts/install-from-image.py", "scripts/gui/installer.py"):
            self.assertNotIn("12.7", (ROOT / f).read_text(), f)


if __name__ == "__main__":
    unittest.main()
