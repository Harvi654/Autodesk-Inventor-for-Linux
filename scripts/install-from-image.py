#!/usr/bin/env python3
"""Install Inventor into a Wine prefix straight from Autodesk's install image.

Does what Autodesk's installer (ODIS) would do, without its UI: reads the
image's manifests (scripts/lib/odis.py), then installs every package in
dependency order - MSI via msiexec /qn, EXE with the silent parameters from
the manifest, ZIP/7Z/ADIX archives unpacked to their target folders.

Usage:
  install-from-image.py IMAGE [--prefix DIR] [--lang en-US]
                        [--from N] [--only N,M] [--redo] [--dry-run]

  IMAGE     the unpacked image (folder with Setup.exe and manifest/), or an
            update: its .exe as downloaded from Autodesk (e.g.
            Inventor_2026.4_Update.exe - unpacked with 7z into
            ~/.cache/inventor-on-linux/media/) or the unpacked folder
            (with bundleManifest.xml). Updates go into the same prefix.
  --prefix  Wine prefix to install into (default ~/.wine-invtest - a TEST
            prefix, so your working one is never touched)
  --from N  start at step N;  --only N,M  run just these steps
  --redo    run steps again even if they finished before
  --dry-run print what would run

Finished steps are remembered in PREFIX/.odis-install-state.json, so after a
failure you can fix things and simply rerun - it continues where it stopped.
Logs: logs/odis-install-<time>/
"""
import argparse
import glob
import json
import os
import shlex
import shutil
import struct
import subprocess
import sys
import time
import urllib.parse
import zipfile


def win_split(cmdline):
    """Split a Windows command line from a manifest into arguments.
    Spaces separate arguments outside double quotes, the quotes are removed and
    backslashes stay as they are (shlex would treat them as escapes:
    M:\\x64\\ASC -> M:x64ASC, and "C:\\Dir\\" -> no closing quotation)."""
    args, cur, quoted, have = [], [], False, False
    for ch in cmdline:
        if ch == '"':
            quoted = not quoted
            have = True
        elif ch in " \t\r\n" and not quoted:
            if have:
                args.append("".join(cur))
            cur, have = [], False
        else:
            cur.append(ch)
            have = True
    if have:
        args.append("".join(cur))
    return args

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import odis  # noqa: E402
import regf  # noqa: E402

PROJECT = os.path.dirname(HERE)
USER = os.environ.get("USER") or "user"
MEDIA_DRIVE = "m:"   # the image is mapped to this drive letter

# MSIX/ADIX "VFS" folder names -> folder below drive_c
VFS = {
    "programfilesx64": "Program Files",
    "programfilesx86": "Program Files (x86)",
    "programfilescommonx64": "Program Files/Common Files",
    "programfilescommonx86": "Program Files (x86)/Common Files",
    "common appdata": "ProgramData",
    "appdata": "users/%s/AppData/Roaming" % USER,
    "local appdata": "users/%s/AppData/Local" % USER,
    "fonts": "windows/Fonts",
    "systemx64": "windows/system32",
    "systemx86": "windows/syswow64",
    "windows": "windows",
}
# Installers that end with an error under Wine although their files are in
# place. name -> (exit codes to accept, glob of a file that must exist,
# name of an Installer method that finishes what the installer skipped)
QUIRKS = {
    # Installs its files, then starts AdskLicensingService as a Windows
    # service. The service does start (its log shows "HTTP server running")
    # but doesn't report "running" to Wine's service manager in time ->
    # error 1053 -> the installer gives up with 69009748 (84 to the shell)
    # and skips its last steps: version.ini (Inventor.msi's licMarkInstall
    # action needs it) and the Current / CurrentSDK links.
    "adsklicensing": ((84,), r"C:\Program Files (x86)\Common Files\Autodesk Shared"
                             r"\AdskLicensing\*\AdskLicensingService\AdskLicensingService.exe",
                      "finish_licensing"),
}

# A Windows exit code reaches Linux only as its low byte: msiexec's 1603
# shows up as 67. The usual Windows Installer codes:
MSI_RC = {
    67: " (= 1603, fatal error during installation - see the .msi/.msp log)",
    69: " (= 1605, product not installed)",
    82: " (= 1618, another installation is in progress)",
    99: " (= 1635, patch package could not be opened)",
    100: " (= 1636, patch package could not be opened)",
    106: " (= 1642, patch does not apply to the installed product)",
}

ADIX_META = {"appxmanifest.xml", "appxblockmap.xml", "appxsignature.p7x",
             "[content_types].xml", "registry.dat", "user.dat", "userclasses.dat"}


class Installer:
    def __init__(self, a):
        self.a = a
        self.image = os.path.abspath(a.image)
        self.prefix = os.path.abspath(os.path.expanduser(a.prefix))
        self.c = os.path.join(self.prefix, "drive_c")
        self.logdir = os.path.join(os.environ.get("INV_LOGDIR", os.path.join(PROJECT, "logs")),
                                   time.strftime("odis-install-%Y%m%d-%H%M%S"))
        self.state_file = os.path.join(self.prefix, ".odis-install-state.json")
        self.env = dict(os.environ, WINEPREFIX=self.prefix,
                        WINEDEBUG=os.environ.get("WINEDEBUG", "fixme-all"))
        self.vars = {
            "commonprogramfiles": r"C:\Program Files\Common Files",
            "commonprogramfiles(x86)": r"C:\Program Files (x86)\Common Files",
            "programfiles": r"C:\Program Files",
            "programfiles(x86)": r"C:\Program Files (x86)",
            "programdata": r"C:\ProgramData",
            "install_dest": r"C:\Program Files\Autodesk",
            "adsk_odis_metadata_base_location": r"C:\ProgramData\Autodesk\ODIS",
            "temp": r"C:\users\%s\AppData\Local\Temp" % USER,
            "tmp": r"C:\users\%s\AppData\Local\Temp" % USER,
            "inv_locale": a.lang,
            "media_root": MEDIA_DRIVE.upper(),
            "install_source": MEDIA_DRIVE.upper(),
        }

    # --- helpers ------------------------------------------------------------
    def expand(self, s, extra=None, step=None):
        """Replace %VAR% (case-insensitive), including the step's manifest
        properties (which may refer to other variables). Unknown ones stay."""
        if not s:
            return s
        v = dict(self.vars, **(extra or {}))
        for k, val in ((step or {}).get("properties") or {}).items():
            v[k.lower()] = val
        for _ in range(5):
            new = self._sub(s, v)
            if new == s:
                break
            s = new
        return s

    @staticmethod
    def _sub(s, v):
        out, i = [], 0
        while i < len(s):
            j = s.find("%", i)
            k = s.find("%", j + 1) if j >= 0 else -1
            if j < 0 or k < 0:
                out.append(s[i:]); break
            name = s[j + 1:k].lower()
            if name in v:
                out.append(s[i:j] + v[name]); i = k + 1
            else:
                out.append(s[i:k]); i = k
        return "".join(out)

    def unix(self, winpath):
        """C:\\Foo\\Bar -> PREFIX/drive_c/Foo/Bar"""
        p = winpath.replace("\\", "/")
        if p[:2].lower() == "c:":
            return os.path.join(self.c, p[2:].lstrip("/"))
        if p[:2].lower() == MEDIA_DRIVE:
            return os.path.join(self.image, p[2:].lstrip("/"))
        raise ValueError("not a C: or %s path: %s" % (MEDIA_DRIVE, winpath))

    def media(self, rel):
        return MEDIA_DRIVE.upper() + "\\" + rel.replace("/", "\\")

    def log(self, msg):
        print(msg, flush=True)
        os.makedirs(self.logdir, exist_ok=True)
        with open(os.path.join(self.logdir, "install.log"), "a") as f:
            f.write(msg + "\n")

    def run(self, argv, logname):
        self.log("      $ " + " ".join(shlex.quote(x) for x in argv))
        if self.a.dry_run:
            return 0
        with open(os.path.join(self.logdir, logname), "ab") as out:
            t0 = time.time()
            rc = subprocess.call(argv, env=self.env, stdout=out, stderr=subprocess.STDOUT)
        hint = MSI_RC.get(rc, "") if argv[1:2] == ["msiexec"] else ""
        self.log("        exit code %d%s after %.1fs" % (rc, hint, time.time() - t0))
        return rc

    # --- prefix -------------------------------------------------------------
    def prepare(self):
        os.makedirs(self.logdir, exist_ok=True)
        if self.a.dry_run:
            return
        if not os.path.isdir(self.c):
            self.log("creating Wine prefix %s" % self.prefix)
            subprocess.check_call(["wineboot", "-i"], env=self.env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.check_call(["wineserver", "-w"], env=self.env)
        subprocess.call(["wine", "reg", "add", r"HKCU\Software\Wine", "/v", "Version",
                         "/d", "win10", "/f"], env=self.env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        link = os.path.join(self.prefix, "dosdevices", MEDIA_DRIVE)
        if os.path.islink(link) or os.path.exists(link):
            os.remove(link)
        os.symlink(self.image, link)

    def state(self):
        try:
            with open(self.state_file) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def mark_done(self, key):
        if self.a.dry_run:
            return
        st = self.state()
        st[key] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(self.state_file, "w") as f:
            json.dump(st, f, indent=1)

    # --- package types ------------------------------------------------------
    def do_msi(self, s, logname, media=None):
        winlog = r"C:\odis-logs\%s.msi.log" % os.path.splitext(logname)[0]
        os.makedirs(os.path.join(self.c, "odis-logs"), exist_ok=True)
        extra = {"media_root": media} if media else None
        argv = ["wine", "msiexec", "/i", (media + "\\" + s["file"].replace("/", "\\"))
                if media else self.media(s["file"]), "/qn", "/norestart", "/l*v", winlog]
        argv += win_split(self.expand(s["params"], extra, s))
        # Autodesk MSIs have the launch condition "ADSK_ODIS_SETUP OR Installed"
        # ("needs to be run from Setup.exe"); ODIS sets this property.
        argv.append("ADSK_ODIS_SETUP=1")
        for k, v in s["msiProperties"].items():
            v = self.expand(v, extra, s)
            if "%" not in v:          # leave out ones only ODIS can fill in
                argv.append("%s=%s" % (k, v))
        rc = self.run(argv, logname)
        return rc in (0, 1641, 3010)  # 3010/1641 = success, reboot wanted

    def do_msp(self, s, logname, media=None):
        """Update patch for an installed product (msiexec finds the target)."""
        winlog = r"C:\odis-logs\%s.msp.log" % os.path.splitext(logname)[0]
        os.makedirs(os.path.join(self.c, "odis-logs"), exist_ok=True)
        patch = (media + "\\" + s["file"].replace("/", "\\")) if media else self.media(s["file"])
        # Windows Installer reinstalls the features a patch touches on its
        # own; Wine's MsiApplyPatch only adds PATCH=... - without REINSTALL
        # every component stays "no change", nearly all files are skipped
        # and the old DLLs remain next to the new Inventor.exe (it then dies
        # at start with 0xc06d007f, a missing delay-load import).
        rc = self.run(["wine", "msiexec", "/p", patch, "/qn", "/norestart", "/l*v", winlog,
                       "REINSTALL=ALL", "REINSTALLMODE=omus", "ADSK_ODIS_SETUP=1"], logname)
        return rc in (0, 1641, 3010)

    def do_exe(self, s, logname, media=None):
        exe = (media + "\\" + s["file"].replace("/", "\\")) if media else self.media(s["file"])
        extra = {"media_root": media} if media else None
        argv = ["wine", exe] + win_split(self.expand(s["params"], extra, s))
        rc = self.run(argv, logname)
        if rc == 250 and s["name"].lower() == "adsklicensing":
            # Some filesystems cannot represent the installer's NTFS junction.
            # Repair only this diagnosed failure, then rerun the vendor installer
            # so its remaining service/registration actions still execute.
            installer_log = self.unix(r"C:\users\%s\AppData\Local\Temp\AdskLicensing-install.log" % USER)
            try:
                with open(installer_log, encoding="utf-8", errors="replace") as f:
                    details = f.read()
            except OSError:
                details = ""
            if ("Error code=LIC-INST-ERROR-250." in details and
                    "Creating 'Current' link to" in details and
                    glob.glob(self.unix(QUIRKS["adsklicensing"][1]))):
                self.log("        licensing junction failed; repairing links and retrying once")
                if not self.finish_licensing():
                    return False
                rc = self.run(argv, "retry-" + logname)
                if rc == 63:
                    with open(installer_log, encoding="utf-8", errors="replace") as f:
                        details = f.read()
                    if ("Error code=LIC-INST-ERROR-69009471." in details and
                            "Starting Windows service during installation-skip workflow failed" in details and
                            "(error code 1053)" in details):
                        self.log("        licensing registered; Wine cannot report the service as running")
                        return self.finish_licensing()
        if rc in (0, 1641, 3010):
            return True
        q = QUIRKS.get(s["name"].lower())
        if q and rc in q[0] and glob.glob(self.unix(q[1])):
            self.log("        known Wine quirk for %s, files are installed - finishing it" % s["name"])
            return getattr(self, q[2])() if len(q) > 2 else True
        return False

    def finish_licensing(self):
        base = self.unix(r"C:\Program Files (x86)\Common Files\Autodesk Shared\AdskLicensing")
        vers = sorted((d for d in os.listdir(base)
                       if d[:1].isdigit() and os.path.isdir(os.path.join(base, d))),
                      key=lambda v: [int(x) for x in v.split(".") if x.isdigit()])
        if not vers:
            return False
        ver = vers[-1]
        with open(os.path.join(base, "version.ini"), "w", newline="\r\n") as f:
            f.write("[General]\nversion=%s\n" % ver)
        # Plain relative symlinks, like the junctions look on an NTFS mount.
        # Wine follows them; its own reparse-point version ("Current?") does
        # not resolve from Linux, so replace it.
        for name, target in (("Current", ver), ("CurrentSDK", ver + "/AdskLicensingSDK")):
            for junk in (name, name + "?"):
                p = os.path.join(base, junk)
                if os.path.islink(p) or os.path.isfile(p):
                    os.remove(p)
                elif os.path.isdir(p):
                    os.rmdir(p)   # empty placeholder; never delete real content
            os.symlink(target, os.path.join(base, name))
        self.log("        version.ini (%s), Current, CurrentSDK written" % ver)
        return True

    def target_dir(self, s):
        loc = self.expand(s.get("installLocation") or "", step=s)
        if not loc or "%" in loc:
            raise RuntimeError("no usable installLocation (%r) for %s" % (s.get("installLocation"), s["name"]))
        return self.unix(loc)

    def do_zip(self, s, logname, path):
        dest = self.target_dir(s)
        self.log("      unzip -> %s" % dest)
        if not self.a.dry_run:
            os.makedirs(dest, exist_ok=True)
            with zipfile.ZipFile(path) as z:
                z.extractall(dest)
        return self.do_actions(s, logname)

    def do_7z(self, s, logname, path):
        dest = self.target_dir(s)
        sevenzip = shutil.which("7zz") or shutil.which("7z") or shutil.which("7za")
        if not sevenzip:
            raise RuntimeError("7z not found - install the 7zip (Arch) / p7zip-full (Debian) package")
        return self.run([sevenzip, "x", "-y", "-o" + dest, path], logname) == 0

    def do_adix(self, s, logname, path):
        """ADIX = Autodesk's MSIX-style package: VFS/<KnownFolder>/... files."""
        written, regs = 0, []
        def place(name, read):
            nonlocal written
            parts = urllib.parse.unquote(name).replace("\\", "/").split("/")
            if len(parts) == 1 and parts[0].lower() in ADIX_META:
                if parts[0].lower().endswith(".dat"):
                    regs.append(parts[0])
                    if not self.a.dry_run:
                        with open(os.path.join(self.logdir, "%s-%s" % (s["name"], parts[0])), "wb") as f:
                            f.write(read())
                return
            if parts[0] != "VFS" or len(parts) < 3 or not parts[-1]:
                return
            base = VFS.get(parts[1].lower())
            if base is None:
                self.log("      WARN unknown VFS folder %r - skipped %s" % (parts[1], name))
                return
            dst = os.path.join(self.c, base, *parts[2:])
            if not self.a.dry_run:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "wb") as f:
                    f.write(read())
            written += 1
        if os.path.isdir(path):
            for d, _, files in os.walk(path):
                for fn in files:
                    full = os.path.join(d, fn)
                    place(os.path.relpath(full, path), lambda full=full: open(full, "rb").read())
        else:
            with zipfile.ZipFile(path) as z:
                for info in z.infolist():
                    if not info.is_dir():
                        place(info.filename, lambda info=info: z.read(info))
        self.log("      %d files placed" % written)
        for hive in regs:
            if not self.import_hive(s, os.path.join(self.logdir, "%s-%s" % (s["name"], hive)), logname):
                return False
        return written > 0

    def import_hive(self, s, path, logname):
        """Registry.dat of an ADIX package -> .reg -> wine regedit."""
        if self.a.dry_run:
            return True
        tokens = {}
        for src, dst in (s.get("pathMappings") or {}).items():
            tokens[src] = self.expand(dst, step=s)
        try:
            with open(path, "rb") as f:
                text = regf.to_reg(f.read(), tokens)
        except (ValueError, IndexError, struct.error) as e:
            self.log("      ERROR can't read %s: %s" % (os.path.basename(path), e))
            return False
        keys = text.count("\r\n[")
        os.makedirs(os.path.join(self.c, "odis-logs"), exist_ok=True)
        name = os.path.splitext(os.path.basename(path))[0] + ".reg"
        with open(os.path.join(self.c, "odis-logs", name), "w", encoding="utf-16", newline="") as f:
            f.write(text)
        rc = self.run(["wine", "regedit", "/S", "C:\\odis-logs\\" + name], logname)
        self.log("      registry: %d keys from %s imported" % (keys, os.path.basename(path)))
        return rc == 0

    def do_actions(self, s, logname, media=None):
        ok = True
        for act in s["actions"]:
            if act["type"] not in ("preInstall", "postInstall"):
                continue
            path = act["path"] or ""
            if "%INSTALLERPATH%" in path or "Installer.exe" in path:
                ok = self.nested_bundle(act, logname, s) and ok
                continue
            exe = self.expand(path, {"install_source": media} if media else None, s)
            if "%" in exe:
                self.log("      skip action %s %s (unknown variable)" % (act["type"], path))
                continue
            rc = self.run(["wine", exe.replace("/", "\\")] + win_split(self.expand(act["params"], step=s)), logname)
            if rc != 0:
                self.log("      WARN %s action returned %d" % (act["type"], rc))
        return ok

    def nested_bundle(self, act, logname, step):
        """ODIS action that installs another bundle (e.g. Shared Components)."""
        args = win_split(self.expand(act["params"], step=step))
        opt = {args[i]: args[i + 1] for i in range(len(args) - 1) if args[i].startswith("--")}
        if opt.get("--install_mode") != "install" or "--mount_point" not in opt:
            return True
        mount = opt["--mount_point"]
        self.log("      nested bundle in %s" % mount)
        if self.a.dry_run:
            return True
        img = odis.Image(self.unix(mount))
        manifest = os.path.relpath(self.unix(opt["--manifest"]), img.root)
        steps, skipped, missing = odis.plan_bundle(img, manifest, self.a.lang)
        for n, why in skipped:
            self.log("        skip %s: %s" % (n, why))
        for n, rel, chain in missing:
            self.log("        MISSING manifest %s (%s)" % (rel, chain))
        ok = not missing
        for i, sub in enumerate(steps, 1):
            # the inner manifests use the outer package's properties
            # (e.g. ASC_BASE_PATH from pkg.asc.xml)
            sub["properties"] = dict(step.get("properties") or {}, **(sub.get("properties") or {}))
            ok = self.install_step(sub, "%s-sub%02d" % (os.path.splitext(logname)[0], i), img, mount) and ok
        return ok

    # --- driver -------------------------------------------------------------
    def use_preinstalled_webview2(self, step):
        if not self.a.preinstalled_webview2 or step["name"].lower() != "webview2":
            return False
        runtime = os.path.join(self.c, "Program Files (x86)", "Microsoft", "EdgeWebView",
                               "Application", "*", "msedgewebview2.exe")
        if not any(os.path.isfile(path) for path in glob.glob(runtime)):
            raise RuntimeError("--preinstalled-webview2 requires msedgewebview2.exe in the prefix")
        self.log("      using the preinstalled WebView2 runtime")
        return True

    def install_step(self, s, tag, img, media=None):
        self.log("  -> %s %s %s" % (s["type"], s["display"], s["version"]))
        path = img.find(s["file"])
        if not path:
            self.log("     ERROR %s not in image" % s["file"]); return False
        logname = tag + ".log"
        try:
            if self.use_preinstalled_webview2(s):
                return True
            return self._install(s, logname, path, media)
        except Exception as e:  # noqa: BLE001 - report and stop cleanly
            self.log("     ERROR %s: %s" % (type(e).__name__, e))
            return False

    def _install(self, s, logname, path, media):
        t = s["type"]
        if self.a.dry_run and t in ("ZIP", "7Z", "ADIX"):
            self.log("      unpack %s (%s)" % (s["file"], t))
            return self.do_actions(s, logname, media)
        if t == "MSI":
            ok = self.do_msi(s, logname, media)
        elif t == "MSP":
            ok = self.do_msp(s, logname, media)
        elif t == "EXE":
            ok = self.do_exe(s, logname, media) and self.do_actions(s, logname, media)
        elif t == "ZIP":
            ok = self.do_zip(s, logname, path)
        elif t == "7Z":
            # e.g. Shared Components' asc-install-helper-tool runs
            # ASCRegistryTool.exe --registry set afterwards
            ok = self.do_7z(s, logname, path) and self.do_actions(s, logname, media)
        elif t == "ADIX":
            # e.g. REX Framework registers REX.exe (/RegServer) afterwards
            ok = self.do_adix(s, logname, path) and self.do_actions(s, logname, media)
        else:
            self.log("     WARN don't know how to install type %s - skipped" % t); return True
        if not ok:
            self.log("     FAILED - see %s" % os.path.join(self.logdir, logname))
        return ok

    def main(self):
        img = odis.Image(self.image)
        kind = odis.image_kind(self.image)
        if kind == "update":
            upi, name = odis.bundle_id(self.image)
            self.key_prefix = "update%s:" % upi
            steps, skipped, missing = odis.plan_bundle(img, odis.bundle_manifest(self.image), self.a.lang)
            if not os.path.isfile(os.path.join(self.prefix, ".odis-install-state.json")):
                sys.exit("no Inventor installed in %s yet - install the product image first" % self.prefix)
            self.restore_originals()
        else:
            self.key_prefix = ""
            apps = self.a.app
            if not apps:
                # like ODIS: Inventor plus the Content Center libraries
                # (app.dclibrary.xml, ~12.7 GB installed) when the image has them
                apps = ["inventor"]
                if not self.a.no_content and img.find("manifest/app.dclibrary.xml"):
                    apps.append("dclibrary")
            steps, skipped, missing = odis.plan(img, apps, self.a.lang, extra=self.a.extra)
        if missing:
            for n, rel, chain in missing:
                print("missing manifest %s (needed by %s)" % (rel, chain))
            sys.exit(1)
        self.prepare()
        only = {int(x) for x in self.a.only.split(",")} if self.a.only else None
        done = self.state()
        self.log("image  %s\nprefix %s\nlogs   %s" % (self.image, self.prefix, self.logdir))
        for n, why in skipped:
            self.log("skip   %s: %s" % (n, why))
        for i, s in enumerate(steps, 1):
            if (only and i not in only) or i < self.a.start:
                continue
            key = self.key_prefix + s["manifest"]
            if key in done and not self.a.redo:
                self.log("[%2d/%d] %s - already done" % (i, len(steps), s["display"])); continue
            self.log("[%2d/%d] %s" % (i, len(steps), s["display"]))
            t0 = time.time()
            if s["type"] in ("MSI", "MSP"):
                self.licensing_service()
            ok = self.install_step(s, "%02d-%s" % (i, s["name"]), img)
            if ok:
                self.mark_done(key)
                self.log("     done in %ds" % (time.time() - t0))
            elif s["ignoreFailure"]:
                self.log("     failed, but the manifest allows that - continuing")
            else:
                self.stop_licensing_service()
                self.log("\nStopped at step %d. Fix it and rerun the same command to continue." % i)
                sys.exit(1)
        self.stop_licensing_service()
        self.log("\nAll steps finished.")

    def restore_originals(self):
        """Put back what finish-install.sh moved aside (disabled add-ins,
        InteractiveTutorial, the CER reporter). An update patches the files
        in place; a file that isn't where the MSI put it can't be patched
        (PatchFiles 1603) - and Wine's rollback then leaves Inventor
        unregistered. Run finish-install.sh again after the update."""
        if self.a.dry_run:
            return
        inv = os.path.join(self.c, "Program Files", "Autodesk", "Inventor " + os.environ.get("INV_YEAR", "2026"))
        off = os.path.join(inv, "Addins.disabled")
        moved = []
        if os.path.isdir(off):
            for f in os.listdir(off):
                if f.lower().endswith(".addin"):
                    shutil.move(os.path.join(off, f), os.path.join(inv, "Bin", "Addins", f))
                    moved.append(f)
            for f, sub in (("InteractiveTutorial.dll", ""), ("InteractiveTutorial.resources.dll", "en-US")):
                src = os.path.join(off, "libs", f)
                if os.path.isfile(src):
                    shutil.move(src, os.path.join(inv, "Bin", sub, f))
                    moved.append(f)
        cer = os.path.join(inv, "Bin", "CER", "senddmp.exe")
        if os.path.isfile(cer + ".disabled") and not os.path.exists(cer):
            os.rename(cer + ".disabled", cer)
            moved.append("senddmp.exe")
        if moved:
            self.log("restored for the update: %s" % ", ".join(moved))
            self.log("run finish-install.sh again afterwards (it disables them again)")

    # Autodesk MSIs register the product with the licensing service through
    # custom actions (licIsSvcUpgraded, licMarkInstall ...), which talk to the
    # running service. Under Wine it can't be started as a Windows service
    # (it never reports "running" -> 1053/1077), so run it as a plain
    # process - exactly what launch-inventor.sh does.
    _lic_proc = None

    def licensing_service(self):
        if self.a.dry_run or self._lic_proc is not None:
            return
        exe = glob.glob(self.unix(QUIRKS["adsklicensing"][1]))
        if not exe:
            return
        win = "C:\\" + os.path.relpath(sorted(exe)[-1], self.c).replace("/", "\\")
        self.log("      starting the licensing service as a process (%s)" % win)
        out = open(os.path.join(self.logdir, "licensing-service.log"), "ab")
        self._lic_proc = subprocess.Popen(["wine", win], env=self.env, stdout=out, stderr=subprocess.STDOUT)
        time.sleep(8)   # it answers on 127.0.0.1:44511 within a few seconds

    def stop_licensing_service(self):
        if self._lic_proc is None:
            return
        subprocess.call(["wine", "taskkill", "/f", "/im", "AdskLicensingService.exe"], env=self.env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self._lic_proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self._lic_proc.kill()
        self._lic_proc = None


def unpack_exe(exe, dry_run=False):
    """Autodesk's downloaded .exe files are 7-Zip self-extractors."""
    name = os.path.splitext(os.path.basename(exe))[0]
    dest = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
                        "inventor-on-linux", "media", name)
    marker = os.path.join(dest, ".unpacked")
    if os.path.isfile(marker):
        return dest
    sevenzip = shutil.which("7zz") or shutil.which("7z") or shutil.which("7za")
    if not sevenzip:
        sys.exit("7z not found - install the 7zip (Arch) / p7zip-full (Debian) package")
    print("unpacking %s -> %s" % (exe, dest), flush=True)
    if dry_run:
        return dest
    os.makedirs(dest, exist_ok=True)
    if subprocess.call([sevenzip, "x", "-y", "-o" + dest, exe], stdout=subprocess.DEVNULL) != 0:
        sys.exit("could not unpack %s with 7z" % exe)
    # some packages put the image one folder deeper
    if odis.image_kind(dest) is None:
        subs = [os.path.join(dest, d) for d in os.listdir(dest) if os.path.isdir(os.path.join(dest, d))]
        hits = [d for d in subs if odis.image_kind(d)]
        if len(hits) == 1:
            dest = hits[0]
    open(os.path.join(dest, ".unpacked"), "w").close()
    return dest


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("image")
    ap.add_argument("--prefix", default="~/.wine-invtest")
    ap.add_argument("--prepared-prefix", action="store_true",
                    help="allow installation into a prepared Wine base prefix (for declarative builds)")
    ap.add_argument("--preinstalled-webview2", action="store_true",
                    help="reuse an existing WebView2 runtime after verifying its executable")
    ap.add_argument("--lang", default="en-US")
    ap.add_argument("--from", dest="start", type=int, default=1)
    ap.add_argument("--only")
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--app", action="append",
                    help="application manifest(s) to install (default: inventor; "
                         "dclibrary = Content Center libraries)")
    ap.add_argument("--no-content", action="store_true",
                    help="leave out the Content Center libraries (~12.7 GB)")
    ap.add_argument("--with", dest="extra", action="append", default=[],
                    help="also install this optional package, e.g. Content Center "
                         "libraries (names: scripts/odis-plan.py IMAGE, under skipped)")
    a = ap.parse_args()
    if os.path.isfile(a.image):
        a.image = unpack_exe(a.image, a.dry_run)
    if odis.image_kind(a.image) is None:
        sys.exit("%s is neither an install image (manifest/app.*.xml) nor an update (Bundle setup.xml)" % a.image)
    prefix = os.path.expanduser(a.prefix)
    if (os.path.isdir(os.path.join(prefix, "drive_c")) and not a.dry_run and not a.prepared_prefix and
            not os.path.isfile(os.path.join(prefix, ".odis-install-state.json"))):
        sys.exit("refusing to install into %s: it exists and was not made by this installer "
                 "(e.g. a prefix copied from Windows) - move it away or choose another --prefix" % prefix)
    Installer(a).main()


if __name__ == "__main__":
    main()
