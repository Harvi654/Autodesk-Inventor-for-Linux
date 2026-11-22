"""install-from-image.py and install.sh: small robustness fixes from a code
review (2026-11-22) - atomic state files, an unpack cache that notices a
newer download with the same name, waiting for the licensing service's port
instead of a fixed sleep - and the Windows command-line splitting the
installer relies on."""
import importlib.util
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

from shell_fixture import fixture_path, shell_script

ROOT = Path(__file__).resolve().parents[1]


def load_installer():
    spec = importlib.util.spec_from_file_location("install_from_image", ROOT / "scripts" / "install-from-image.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Unpacks by creating "<out>/<IMAGE_SUB>/IMAGE" and counts its calls.
FAKE_7Z = """#!/bin/sh
out=
for a in "$@"; do case "$a" in -o*) out="${a#-o}" ;; esac; done
mkdir -p "$out/${IMAGE_SUB:-.}"
: > "$out/${IMAGE_SUB:-.}/IMAGE"
echo x >> "$CALLS"
"""


class WinSplit(unittest.TestCase):
    """Manifests write Windows paths with backslashes, also right before a
    closing quote. Windows' own argv rules would read \\" as a literal quote;
    the installer keeps backslashes as they are on purpose."""

    def setUp(self):
        self.ins = load_installer()

    def test_backslash_before_closing_quote_stays(self):
        line = 'INSTALLDIR="C:\\Program Files\\Autodesk\\AutoCAD 2027\\" /qn'
        self.assertEqual(self.ins.win_split(line),
                         ['INSTALLDIR=C:\\Program Files\\Autodesk\\AutoCAD 2027\\', '/qn'])

    def test_plain_paths_and_spaces(self):
        self.assertEqual(self.ins.win_split(r'M:\x64\ASC\setup.exe  --mode unattended'),
                         [r'M:\x64\ASC\setup.exe', '--mode', 'unattended'])
        self.assertEqual(self.ins.win_split(r'"C:\A B\c.exe" "" x'), [r'C:\A B\c.exe', '', 'x'])


class AtomicJson(unittest.TestCase):
    def setUp(self):
        self.ins = load_installer()
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-atomic-")
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "state.json")

    def test_writes_and_leaves_no_temporary_file(self):
        self.ins.write_json_atomic(self.path, {"a": 1})
        self.assertEqual(json.loads(Path(self.path).read_text()), {"a": 1})
        self.assertEqual(os.listdir(self.tmp.name), ["state.json"])

    def test_failed_write_keeps_the_old_file(self):
        self.ins.write_json_atomic(self.path, {"a": 1})
        with self.assertRaises(TypeError):
            self.ins.write_json_atomic(self.path, {"a": object()})
        self.assertEqual(json.loads(Path(self.path).read_text()), {"a": 1})
        self.assertEqual(os.listdir(self.tmp.name), ["state.json"])


class WaitForLicensing(unittest.TestCase):
    """The licensing service's port is its own choice per installation and
    is read from AdskLicensingService.data each time."""

    def setUp(self):
        self.ins = load_installer()
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-licensing-")
        self.addCleanup(self.tmp.cleanup)
        self.data = os.path.join(self.tmp.name, "AdskLicensingService.data")

    def free_port(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def test_reads_the_address(self):
        Path(self.data).write_text('{"Version":"x","Addr":"127.0.0.1:39843","Other":1}')
        self.assertEqual(self.ins.licensing_addr(self.data), ("127.0.0.1", 39843))
        self.assertIsNone(self.ins.licensing_addr(self.data + ".missing"))
        Path(self.data).write_text("{}")
        self.assertIsNone(self.ins.licensing_addr(self.data))

    def test_follows_a_port_written_while_waiting(self):
        Path(self.data).write_text('{"Addr":"127.0.0.1:%d"}' % self.free_port())   # old, nobody there
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        port = srv.getsockname()[1]

        def start_service():
            time.sleep(0.6)
            srv.listen(1)
            Path(self.data).write_text('{"Addr":"127.0.0.1:%d"}' % port)
        threading.Thread(target=start_service, daemon=True).start()
        try:
            waited = self.ins.wait_for_addr(lambda: self.ins.licensing_addr(self.data), 10, step=0.1)
        finally:
            srv.close()
        self.assertIsNotNone(waited)
        self.assertLess(waited, 5)

    def test_gives_up_after_the_timeout(self):
        start = time.monotonic()
        self.assertIsNone(self.ins.wait_for_addr(lambda: None, 1, step=0.1))
        self.assertIsNone(self.ins.wait_for_addr(lambda: ("127.0.0.1", self.free_port()), 1, step=0.1))
        self.assertLess(time.monotonic() - start, 6)

    def test_gives_up_when_the_process_ended(self):
        start = time.monotonic()
        self.assertIsNone(self.ins.wait_for_addr(lambda: None, 30, alive=lambda: False, step=0.1))
        self.assertLess(time.monotonic() - start, 5)


class UnpackCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-unpack-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        b = root / "bin"
        b.mkdir()
        (b / "7z").write_text(shell_script(FAKE_7Z))
        (b / "7z").chmod(0o755)
        self.calls = root / "calls"
        self.env = {"PATH": fixture_path(b), "XDG_CACHE_HOME": str(root / "cache"),
                    "CALLS": str(self.calls), "IMAGE_SUB": "inner"}
        self.saved = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)
        self.addCleanup(self.restore_env)
        self.ins = load_installer()
        self.ins.odis.image_kind = lambda d: "product" if os.path.isfile(os.path.join(d, "IMAGE")) else None
        self.exe = root / "Inventor_2027_Update.exe"
        self.exe.write_bytes(b"one")
        self.cache = root / "cache" / "inventor-on-linux" / "media" / "Inventor_2027_Update"

    def restore_env(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def count(self):
        return len(self.calls.read_text().splitlines()) if self.calls.exists() else 0

    def test_nested_image_is_cached(self):
        first = self.ins.unpack_exe(str(self.exe))
        self.assertEqual(first, str(self.cache / "inner"))
        second = self.ins.unpack_exe(str(self.exe))
        self.assertEqual(second, first)
        self.assertEqual(self.count(), 1)

    def test_newer_download_with_the_same_name_unpacks_again(self):
        self.ins.unpack_exe(str(self.exe))
        (self.cache / "inner" / "OLD-ONLY").write_text("x")
        self.exe.write_bytes(b"a newer, longer download")
        os.utime(self.exe, (time.time() + 10, time.time() + 10))
        image = self.ins.unpack_exe(str(self.exe))
        self.assertEqual(self.count(), 2)
        self.assertFalse((Path(image) / "OLD-ONLY").exists())

    def test_marker_without_stamp_unpacks_again(self):
        self.cache.mkdir(parents=True)
        (self.cache / "IMAGE").write_text("")
        (self.cache / ".unpacked").write_text("")      # written by older versions
        self.ins.unpack_exe(str(self.exe))
        self.assertEqual(self.count(), 1)


class InstallShUnpack(unittest.TestCase):
    """install.sh's own unpack() writes the same stamp and unpacks a newer
    download with the same name again."""

    def run_unpack(self, root, *parts):
        fn = subprocess.run(["sed", "-n", "/^unpack() {/,/^}/p", str(ROOT / "scripts" / "install.sh")],
                            capture_output=True, text=True, check=True).stdout
        script = ("set -e\nCACHE=%s\nREQ_MEDIA_GB=1\ninfo() { :; }\nfind_image() { echo \"$1\"; }\n%s\nunpack \"$@\"\n"
                  % (root / "cache", fn))
        env = dict(os.environ, PATH=fixture_path(root / "bin"), CALLS=str(root / "calls"), IMAGE_SUB=".")
        return subprocess.run(["bash", "-c", script, "unpack", *map(str, parts)],
                              capture_output=True, text=True, env=env, check=True).stdout.strip()

    def test_stamp_and_reunpack(self):
        with tempfile.TemporaryDirectory(prefix="inventor-unpack-sh-") as d:
            root = Path(d)
            (root / "bin").mkdir()
            (root / "bin" / "7z").write_text(shell_script(FAKE_7Z))
            (root / "bin" / "7z").chmod(0o755)
            exe = root / "Inventor_2027_db_001_002.exe"
            data = root / "Inventor_2027_db_002_002.7z"
            exe.write_bytes(b"stub")
            data.write_bytes(b"data")
            dest = Path(self.run_unpack(root, exe, data))
            stamp = (dest / ".unpacked").read_text().splitlines()[0]
            self.assertEqual(stamp, "Inventor_2027_db_002_002.7z:4:%d" % int(data.stat().st_mtime))
            self.run_unpack(root, exe, data)
            self.assertEqual(len((root / "calls").read_text().splitlines()), 1)
            data.write_bytes(b"newer data")
            self.run_unpack(root, exe, data)
            self.assertEqual(len((root / "calls").read_text().splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
