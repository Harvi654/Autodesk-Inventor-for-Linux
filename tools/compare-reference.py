#!/usr/bin/env python3
"""Compare a Windows reference install with a Wine prefix made by our installer.

The Windows side is the output of tools/capture-state.ps1, run in a clean VM
before and after the install of the same image (folders "before" and "after";
"after/logs" holds the installer's and every MSI package's logs). The Linux
side is the prefix and the install.log of install-from-image.py.

What the Windows install added (after minus before) is checked against the
prefix: ODIS packages, MSI properties passed to each package, files, registry
keys and value names, services, uninstall entries, machine environment.

Only names are printed (plus a few MSI property and environment values, with
user names, SIDs and long hex IDs masked). Registry VALUES are never printed.
The captures themselves stay local; they are never committed.

Usage:
  compare-reference.py CAP_DIR PREFIX --linux-log INSTALL_LOG [...]
                       [--details OUT.md] [--all-groups]
  CAP_DIR      folder with before/ and after/ from capture-state.ps1
  PREFIX       the Wine prefix our installer made from the same image
  INSTALL_LOG  logs/odis-install-<date>/install.log of that install (several
               allowed: a resumed install writes one per run)
The summary goes to stdout; --details writes the full lists to a file.
"""
import argparse
import collections
import csv
import glob
import os
import re
import sys

# Groups whose names contain one of these are "relevant": listed in full.
RELEVANT = re.compile(r"autodesk|adsk|inventor|acad|realdwg|flexnet|macrovision|"
                      r"odis|nastran|anark|rex\b|webview|edgeupdate|vc_?redist|"
                      r"visualc|vcruntime|msvcp|\.netframework|ndp|dotnet|"
                      r"aspnetcore|windowsdesktop|coordinate|geospatial", re.I)
# Windows' own background activity between the two captures: counted, not listed.
NOISE = re.compile(r"\\(prefetch|logfiles|sru|wdi|winevt|spool|tasks_migrated|"
                   r"softwaredistribution|catroot2?|cryptnet|crypt|tokenbroker|"
                   r"notifications|explorer\\(thumb|icon)cache|"
                   r"windows\\(recent|inetcache|webcache|history))\\", re.I)


# --- masking --------------------------------------------------------------------
def mask(s, users=()):
    s = re.sub(r"S-1-5-21(-\d+){3,4}", "SID", s)
    s = re.sub(r"(?i)(\\users\\)(?!public\\|default\\|all users\\)[^\\/\"]+", r"\1USER", s)
    s = re.sub(r"(?i)(/users/)(?!public/)[^/\"]+", r"\1USER", s)
    s = re.sub(r"(?i)(/home/)[^/\"]+", r"\1USER", s)
    s = re.sub(r"\b[0-9A-Fa-f]{16,}\b", "HEX", s)
    for u in users:
        if u and len(u) > 2:
            s = re.sub(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(u), "USER", s, flags=re.I)
    return s


# --- text files of unknown encoding ----------------------------------------------
def read_text(path):
    with open(path, "rb") as f:
        b = f.read()
    if b[:2] in (b"\xff\xfe", b"\xfe\xff") or (len(b) > 3 and b[1:2] == b"\x00" and b[3:4] == b"\x00"):
        return b.decode("utf-16", errors="replace")
    if b[:3] == b"\xef\xbb\xbf":
        b = b[3:]
    return b.decode("utf-8", errors="replace")


# --- registry ---------------------------------------------------------------------
def norm_key(k):
    k = k.strip().strip("\\").lower()
    k = re.sub(r"\\+", r"\\", k)
    return k


WIN_ROOTS = [  # Windows export prefix -> (hive, Wine key prefix)
    ("hkey_local_machine\\system\\currentcontrolset\\", "hklm", "system\\controlset001\\"),
    ("hkey_local_machine\\", "hklm", ""),
    ("hkey_current_user\\", "hkcu", ""),
    ("hkey_users\\.default\\", "hku.default", ""),
    ("hkey_classes_root\\", "hklm", "software\\classes\\"),
]


def win_key_to_wine(k):
    lk = norm_key(k)
    for pre, hive, wpre in WIN_ROOTS:
        if lk.startswith(pre):
            return wow_classes(hive, wpre + lk[len(pre):])
        if lk + "\\" == pre:
            return wow_classes(hive, wpre.rstrip("\\"))
    return None, lk


def wow_classes(hive, key):
    """HKLM\\Software\\WOW6432Node\\Classes is Software\\Classes\\Wow6432Node
    (one key, two names); a Windows export lists it under the first, Wine's
    system.reg under the second."""
    pre = "software\\wow6432node\\classes"
    if hive == "hklm" and (key == pre or key.startswith(pre + "\\")):
        return hive, "software\\classes\\wow6432node" + key[len(pre):]
    return hive, key


def parse_windows_reg(path):
    """{(hive, wine_key): {value_name_lower: original_name}}"""
    keys = {}
    cur = None
    for line in read_text(path).splitlines():
        if line.startswith("[") and line.rstrip().endswith("]"):
            name = line.strip()[1:-1]
            if name.startswith("-"):
                cur = None
                continue
            hive, wk = win_key_to_wine(name)
            cur = (hive, wk) if hive else None
            if cur is not None:
                keys.setdefault(cur, {})
            continue
        if cur is None:
            continue
        m = re.match(r'^"((?:[^"\\]|\\.)*)"\s*=', line)
        if m:
            n = m.group(1).replace('\\"', '"').replace("\\\\", "\\")
            keys[cur][n.lower()] = n
        elif line.startswith("@="):
            keys[cur]["@"] = "@"
    return keys


def unescape_wine(s):
    s = re.sub(r"\\x\{?([0-9a-fA-F]{1,4})\}?", lambda m: chr(int(m.group(1), 16)), s)
    return s.replace("\\\\", "\\")


def parse_wine_reg(path, hive):
    """{(hive, key): {value_lower: (name, raw_value)}}"""
    keys = {}
    cur = None
    if not os.path.exists(path):
        return keys
    for line in read_text(path).splitlines():
        if line.startswith("["):
            m = re.match(r"^\[(.*)\]\s*\d*", line)
            if m:
                cur = (hive, norm_key(unescape_wine(m.group(1))))
                keys.setdefault(cur, {})
            continue
        if cur is None:
            continue
        m = re.match(r'^"((?:[^"\\]|\\.)*)"\s*=\s*(.*)$', line)
        if m:
            n = unescape_wine(m.group(1).replace('\\"', '"'))
            keys[cur][n.lower()] = (n, m.group(2))
        elif line.startswith("@="):
            keys[cur]["@"] = ("@", line[2:])
    return keys


def wine_string(raw):
    m = re.match(r'^(?:str\(\d\):)?"((?:[^"\\]|\\.)*)"', raw or "")
    return unescape_wine(m.group(1).replace('\\"', '"')) if m else None


def wine_dword(raw):
    m = re.match(r"^dword:([0-9a-fA-F]{8})", raw or "")
    return int(m.group(1), 16) if m else None


def key_group(key, depth=4):
    return "\\".join(key.split("\\")[:depth])


# --- files ------------------------------------------------------------------------
def read_files_tsv(path):
    out = {}
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        next(f, None)
        for line in f:
            p = line.rstrip("\r\n").split("\t")
            if p and p[0]:
                out[p[0].lower()] = p[0]
    return out


def read_sizes_tsv(path):
    """lower-case path -> size in bytes (second column), where given."""
    out = {}
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        next(f, None)
        for line in f:
            p = line.rstrip("\r\n").split("\t")
            if len(p) > 1 and p[0] and p[1].isdigit():
                out[p[0].lower()] = int(p[1])
    return out


def windows_to_prefix(path, wine_user):
    """C:\\... (Windows) -> path relative to PREFIX/drive_c, lower case."""
    p = path.lower()
    if not p.startswith("c:\\"):
        return None
    p = p[3:]
    p = re.sub(r"^users\\(?!public\\|default\\)[^\\]+\\", "users\\\\%s\\\\" % wine_user.lower(), p)
    return p.replace("\\", "/")


def prefix_files(drive_c):
    out = {}
    for root, dirs, files in os.walk(drive_c, followlinks=False):
        rel = os.path.relpath(root, drive_c)
        for f in files:
            r = f if rel == "." else os.path.join(rel, f)
            out[r.lower()] = r
    return out


def file_group(path, depth):
    parts = path.split("\\")
    # C:\Program Files\Autodesk\Inventor 2027\... -> 4 levels; Windows\System32 -> 3
    return "\\".join(parts[:depth])


def group_depth(path):
    lp = path.lower()
    if re.match(r"c:\\(program files( \(x86\))?|programdata)\\(autodesk|common files)\\", lp):
        return 4
    if lp.startswith("c:\\users\\"):
        return 6
    return 3


# --- MSI logs ---------------------------------------------------------------------
PROP_RE = re.compile(r'([A-Z][A-Z0-9_.]*)=("(?:[^"]*)"|\S*)')
SECRET = re.compile(r"serial|password|token|secret|key\b|_key|prodkey", re.I)
SHOW_VALUE = re.compile(r"^(INSTALLDIR|TARGETDIR|APPDIR|INSTALLLOCATION|TRANSFORMS|"
                        r"LANGUAGE|LANG|ProductLanguage|ADSK_.*|ADLM_.*|REBOOT|"
                        r"ALLUSERS|MSIFASTINSTALL|.*DIR|.*PATH|.*LOCATION)$", re.I)


# Properties the Windows Installer client adds itself when it hands an
# install to the Windows Installer service; ODIS does not pass them, and
# Wine's msiexec (no separate service) has no counterpart.
CLIENT_PROPS = {"CURRENTDIRECTORY", "CLIENTUILEVEL", "MSICLIENTUSESEXTERNALUI", "CLIENTPROCESSID"}


def msi_props(cmdline):
    """NAME=value pairs; a value runs to the next ' NAME=' (Windows logs
    print paths with spaces unquoted)."""
    props = collections.OrderedDict()
    ms = list(re.finditer(r'(?:^|\s)([A-Z][A-Z0-9_.]*)=', cmdline))
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(cmdline)
        props[m.group(1).upper()] = cmdline[m.end():end].strip().strip('"')
    return props


def windows_msi_logs(logdir):
    """{msi_basename_lower: (msi_basename, {PROP: value}, logfile)}"""
    out = {}
    for path in glob.glob(os.path.join(logdir, "**", "*"), recursive=True):
        if not os.path.isfile(path) or os.path.getsize(path) > 200 * 1024 * 1024:
            continue
        try:
            t = read_text(path)
        except OSError:
            continue
        if "Verbose logging started" not in t[:2000]:
            continue
        if re.search(r"virtio|spice|qemu", os.path.basename(path), re.I):
            continue   # the VM's guest tools, installed before the capture
        prod = re.search(r"\*\*\*\*\*\*\* Product: (.+)", t)
        cmds = re.findall(r"Command Line: (.*)", t)
        if not prod:
            continue
        pn = re.search(r"Property\([SC]\): ProductName = (.+)", t)
        name = pn.group(1).strip() if pn else os.path.basename(prod.group(1).strip().replace("\\", "/"))
        cmd = max(cmds, key=len) if cmds else ""
        props = msi_props(cmd)
        key = os.path.basename(prod.group(1).strip().replace("\\", "/")).lower()
        name = "%s (%s)" % (key, name)
        if key not in out or len(props) > len(out[key][1]):
            out[key] = (name, props, os.path.basename(path))
    return out


def linux_msi_runs(logs):
    """{product: (name, {PROP: value})} from install.log: '-> MSI <name> <ver>'
    followed by the '$ wine msiexec /i ...' line."""
    out = {}
    for log in logs:
        pname = None
        for line in read_text(log).splitlines():
            m = re.match(r"^\s*-> MSI (.+?)(?: [0-9][0-9.]*)?\s*$", line)
            if m:
                pname = m.group(1).strip()
                continue
            m = re.search(r"\$ wine msiexec /[ip] ('[^']*'|\S+)(.*)$", line)
            if not m:
                continue
            base = ntbase(m.group(1).strip("'"))
            out[base.lower()] = ("%s (%s)" % (base.lower(), pname or base), msi_props(m.group(2).replace("'", "")))
            pname = None
    return out


def ntbase(p):
    return re.split(r"[\\/]", p)[-1]


def odis_packages_windows(logdir):
    names = set()
    for path in glob.glob(os.path.join(logdir, "**", "*"), recursive=True):
        if not os.path.isfile(path) or os.path.getsize(path) > 200 * 1024 * 1024:
            continue
        try:
            t = read_text(path)
        except OSError:
            continue
        for m in re.finditer(r"Installation of package: (.+?) is successful", t):
            names.add(m.group(1).strip())
    return names


def windows_package_logs(logdir):
    """Stems of ODIS' per-package logs (%TEMP%\\<package>_install.log)."""
    out = set()
    for path in glob.glob(os.path.join(logdir, "*_install.log")):
        b = os.path.basename(path)
        b = re.sub(r"^C__Users_[^_]+_AppData_Local_Temp_", "", b)
        b = re.sub(r"(_[0-9][0-9.]*)?_install\.log$", "", b)
        out.add(b)
    return out


def our_packages(logs):
    done, skipped = [], []
    for log in logs:
        for line in read_text(log).splitlines():
            m = re.match(r"^\[\s*\d+/\d+\] (.+?)( - already done)?$", line)
            if m:
                done.append(m.group(1).strip())
            m = re.match(r"^skip\s+(\S+): (.*)$", line)
            if m:
                skipped.append("%s (%s)" % (m.group(1), m.group(2)))
    return list(dict.fromkeys(done)), list(dict.fromkeys(skipped))


def norm_pkg(n):
    n = n.lower()
    n = re.sub(r"\b(20\d\d|x64|x86|64-bit|- english|english|\d+(\.\d+)+)\b", " ", n)
    n = re.sub(r"[^a-z0-9]+", " ", n)
    return " ".join(n.split())


# --- report -----------------------------------------------------------------------
class Report:
    def __init__(self, users, all_groups):
        self.summary, self.details = [], []
        self.users, self.all = users, all_groups

    def m(self, s):
        return mask(s, self.users)

    def h(self, title):
        for out in (self.summary, self.details):
            out.append("\n## " + title + "\n")

    def line(self, s, detail_only=False):
        s = self.m(s)
        self.details.append(s)
        if not detail_only:
            self.summary.append(s)

    def groups(self, title, items, depth_of, limit=25, everything=False):
        """items: list of original-case strings; grouped, relevant ones
        listed (every group with everything=True)."""
        by = collections.OrderedDict()
        for it in sorted(items, key=str.lower):
            by.setdefault(depth_of(it), []).append(it)
        show = lambda g: everything or self.all or RELEVANT.search(g)
        rel = [(g, v) for g, v in by.items() if show(g)]
        other = [(g, v) for g, v in by.items() if not show(g)]
        self.line("%s: %d in %d groups (%d relevant)" % (title, len(items), len(by), len(rel)))
        for g, v in rel:
            self.line("- `%s`: %d" % (g, len(v)))
            for it in v[:limit]:
                self.line("    - `%s`" % it, detail_only=True)
            if len(v) > limit:
                self.line("    - ... %d more" % (len(v) - limit), detail_only=True)
        if other:
            self.line("- other groups (Windows background, system): %d groups, %d items" %
                      (len(other), sum(len(v) for _, v in other)))
            for g, v in other:
                self.line("    - `%s`: %d" % (g, len(v)), detail_only=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cap")
    ap.add_argument("prefix")
    ap.add_argument("--linux-log", action="append", default=[])
    ap.add_argument("--details")
    ap.add_argument("--all-groups", action="store_true", help="list every group, not only Autodesk-related")
    a = ap.parse_args()
    before, after = os.path.join(a.cap, "before"), os.path.join(a.cap, "after")
    drive_c = os.path.join(a.prefix, "drive_c")
    users_dir = os.path.join(drive_c, "users")
    wine_users = [u for u in os.listdir(users_dir) if u.lower() not in ("public", "default")] if os.path.isdir(users_dir) else []
    wine_user = wine_users[0] if wine_users else "user"
    win_users = set()
    for p in read_files_tsv(os.path.join(after, "files.tsv")).values():
        m = re.match(r"(?i)c:\\users\\([^\\]+)\\", p)
        if m and m.group(1).lower() not in ("public", "default", "all users"):
            win_users.add(m.group(1))
    r = Report(list(win_users) + wine_users + [os.environ.get("USER", "")], a.all_groups)
    r.summary.append("# Windows reference install vs. Wine prefix\n")
    r.details.append("# Windows reference install vs. Wine prefix (details)\n")

    # 1. ODIS packages
    r.h("1. Packages")
    win_pk = odis_packages_windows(os.path.join(after, "logs"))
    ours, skipped = our_packages(a.linux_log)
    wn = {norm_pkg(x): x for x in win_pk}
    on = {norm_pkg(x): x for x in ours}
    r.line("AdIX packages ODIS reported successful on Windows: %d" % len(win_pk))
    for k in sorted(set(wn) - set(on)):
        r.line("- AdIX package only on Windows: `%s`" % wn[k])
    for s in skipped:
        r.line("- we skip: %s" % s)
    stems = windows_package_logs(os.path.join(after, "logs"))
    r.line("Windows per-package install logs (%d): %s" % (len(stems), ", ".join("`%s`" % x for x in sorted(stems, key=str.lower))))
    r.line("Our packages (%d): %s" % (len(ours), ", ".join("`%s`" % x for x in ours)))

    # 2. MSI properties
    r.h("2. MSI properties per package (names; values only for paths/ADSK/ADLM, masked)")
    wmsi = windows_msi_logs(os.path.join(after, "logs"))
    lmsi = linux_msi_runs(a.linux_log)
    r.line("Windows MSI logs: %d packages; our msiexec runs: %d" % (len(wmsi), len(lmsi)))
    for k in sorted(set(wmsi) | set(lmsi)):
        wn_, wp, wlog = wmsi.get(k, (None, {}, None))
        ln_, lp = lmsi.get(k, (None, {}))
        name = wn_ or ln_
        if wn_ is None:
            r.line("- `%s`: only ours (no Windows MSI log)" % name)
            continue
        if ln_ is None:
            r.line("- `%s`: only on Windows (we never ran it as MSI)" % name)
            continue
        client = [p for p in wp if p in CLIENT_PROPS and p not in lp]
        miss = [p for p in wp if p not in lp and p not in CLIENT_PROPS]
        extra = [p for p in lp if p not in wp]
        diff = [p for p in wp if p in lp and wp[p] != lp[p] and not SECRET.search(p)]
        if client:
            r.line("- `%s`: Windows Installer client's own properties (ignored): %s"
                   % (name, ", ".join("`%s`" % p for p in client)), detail_only=True)
        if not (miss or extra or diff):
            r.line("- `%s`: same property names (%d)" % (name, len(wp)), detail_only=True)
            continue
        r.line("- `%s`:" % name)
        for p in miss:
            v = "" if SECRET.search(p) or not SHOW_VALUE.match(p) else " = `%s`" % wp[p]
            r.line("    - Windows passes `%s`%s, we don't" % (p, v))
        for p in extra:
            r.line("    - we pass `%s`, Windows doesn't" % p)
        for p in diff:
            if SHOW_VALUE.match(p):
                r.line("    - `%s`: Windows `%s`, ours `%s`" % (p, wp[p], lp[p]))
            else:
                r.line("    - `%s`: different value" % p)

    # 3. Files
    r.h("3. Files the Windows install added, missing in the prefix")
    fb = read_files_tsv(os.path.join(before, "files.tsv"))
    fa = read_files_tsv(os.path.join(after, "files.tsv"))
    added = [fa[k] for k in fa if k not in fb and not NOISE.search(k)]
    noise = sum(1 for k in fa if k not in fb and NOISE.search(k))
    pf = prefix_files(drive_c)
    missing = []
    for p in added:
        rel = windows_to_prefix(p, wine_user)
        if rel is not None and rel not in pf:
            missing.append(p)
    r.line("Windows added %d files (%d more in Windows' own logs/caches, ignored); "
           "%d of them are not in the prefix" % (len(added), noise, len(missing)))
    r.groups("missing in the prefix", missing, lambda p: file_group(p, group_depth(p)))

    r.h("3a. Files the install added, on both sides with a different size (another build)")
    # e.g. a shared file two packages install in different builds: which one
    # Windows kept has to be the one the prefix has
    sizes = read_sizes_tsv(os.path.join(after, "files.tsv"))
    differ = []
    for k, p in fa.items():
        rel = windows_to_prefix(p, wine_user)
        # only what the install added: Windows' own fonts against Wine's are
        # no install difference
        if k in fb or rel is None or rel not in pf or k not in sizes or NOISE.search(k):
            continue
        # Autodesk's folders, the shared Public Documents and the fonts
        # packages install (AIGDT___.TTF from two packages in two sizes)
        if not re.match(r"(program files( \(x86\))?/(autodesk|common files/autodesk shared)|programdata/autodesk|"
                        r"users/public/documents/autodesk|windows/fonts)/", rel):
            continue
        try:
            ours = os.path.getsize(os.path.join(drive_c, pf[rel]))
        except OSError:
            continue
        if ours != sizes[k]:
            differ.append("%s (Windows %d, prefix %d bytes)" % (p, sizes[k], ours))
    r.groups("different size", differ, lambda p: file_group(p.split(" (Windows ")[0], group_depth(p)),
             everything=True)

    r.h("3b. Autodesk files only in the prefix")
    win_all = {windows_to_prefix(v, wine_user) for v in fa.values()}
    ours_only = []
    for k, v in pf.items():
        if re.match(r"(program files( \(x86\))?/(autodesk|common files/autodesk shared)|programdata/autodesk)/", k) \
                and k not in win_all:
            ours_only.append("C:\\" + v.replace("/", "\\"))
    r.groups("only in the prefix", ours_only, lambda p: file_group(p, group_depth(p)))

    # 4. Registry
    r.h("4. Registry keys and value names the Windows install added, missing in the prefix")
    wine = {}
    for hive, fn in (("hklm", "system.reg"), ("hkcu", "user.reg"), ("hku.default", "userdef.reg")):
        wine.update(parse_wine_reg(os.path.join(a.prefix, fn), hive))
    # Wine writes no section for a key that has only subkeys: its ancestors
    # count as present
    wine_keys = set(wine)
    for hive, key in list(wine):
        parts = key.split("\\")
        for i in range(1, len(parts)):
            wine_keys.add((hive, "\\".join(parts[:i])))
    rb, ra = {}, {}
    for f in sorted(glob.glob(os.path.join(before, "*.reg"))):
        rb.update(parse_windows_reg(f))
    for f in sorted(glob.glob(os.path.join(after, "*.reg"))):
        ra.update(parse_windows_reg(f))
    new_keys, new_vals = [], []
    for k, vals in ra.items():
        if k not in rb:
            new_keys.append(k)
        else:
            for v in vals:
                if v not in rb[k]:
                    new_vals.append((k, vals[v]))
    miss_keys = [k for k in new_keys if k not in wine_keys]
    # written per user on Windows (HKCU\Software\Classes), machine-wide in
    # the prefix (HKLM\Software\Classes): both are HKEY_CLASSES_ROOT
    per_user = {k for k in miss_keys if k[0] == "hkcu" and k[1].startswith("software\\classes\\")
                and ("hklm", k[1]) in wine_keys}
    miss_keys = [k for k in miss_keys if k not in per_user]
    miss_vals = []
    for k in new_keys:
        if k in wine_keys:
            for v, name in ra[k].items():
                if v not in wine.get(k, {}):
                    miss_vals.append((k, name))
    for k, name in new_vals:
        if k not in wine_keys:
            miss_vals.append((k, name))
        elif name.lower() not in wine.get(k, {}):
            miss_vals.append((k, name))
    r.line("Windows added %d keys and %d values in existing keys; missing in the prefix: "
           "%d keys, %d value names" % (len(new_keys), len(new_vals), len(miss_keys), len(miss_vals)))
    r.line("keys Windows wrote per user (HKCU\\Software\\Classes) that the prefix has machine-wide "
           "(HKLM\\Software\\Classes): %d" % len(per_user))
    r.groups("per user on Windows, machine-wide in the prefix", ["%s:%s" % k for k in sorted(per_user)],
             lambda s: key_group(s, 4), limit=5)
    r.groups("keys missing in the prefix", ["%s:%s" % k for k in miss_keys],
             lambda s: key_group(s, 5))
    r.groups("value names missing in the prefix (key present or added)",
             ["%s:%s -> %s" % (k[0], k[1], n) for k, n in miss_vals],
             lambda s: key_group(s.split(" -> ")[0], 5))

    # 5. Services
    r.h("5. Services")
    def services(p):
        try:
            with open(p, encoding="utf-8-sig") as f:
                return {row["Name"]: row for row in csv.DictReader(f)}
        except OSError:
            return {}
    sb, sa = services(os.path.join(before, "services.csv")), services(os.path.join(after, "services.csv"))
    start_names = {"Boot": 0, "System": 1, "Auto": 2, "Manual": 3, "Disabled": 4}
    for n in sorted(set(sa) - set(sb)):
        row = sa[n]
        k = ("hklm", "system\\controlset001\\services\\" + n.lower())
        if k not in wine:
            r.line("- `%s` (%s, %s): not in the prefix" % (n, row.get("StartMode"), mask(row.get("PathName", ""))))
        else:
            st = wine_dword(wine[k].get("start", (None, None))[1])
            r.line("- `%s`: Windows start %s, prefix Start=%s" % (n, row.get("StartMode"), st))
    if not set(sa) - set(sb):
        r.line("- no new services on Windows")

    # 6. Uninstall entries
    r.h("6. Uninstall entries (Programs and Features)")
    def uninst(p):
        try:
            with open(p, encoding="utf-8-sig") as f:
                return {(row.get("PSChildName") or ""): row for row in csv.DictReader(f)}
        except OSError:
            return {}
    ub, ua = uninst(os.path.join(before, "uninstall.csv")), uninst(os.path.join(after, "uninstall.csv"))
    wine_dn = {}
    for (hive, key), vals in wine.items():
        if hive == "hklm" and re.search(r"\\uninstall\\[^\\]+$", key):
            dn = wine_string(vals.get("displayname", (None, None))[1])
            if dn:
                wine_dn[key.rsplit("\\", 1)[1]] = dn
    for code in sorted(set(ua) - set(ub), key=lambda c: (ua[c].get("DisplayName") or "")):
        row = ua[code]
        here = code.lower() in wine_dn
        r.line("- %s `%s` %s (%s)" % ("ok     " if here else "MISSING", row.get("DisplayName"),
                                      row.get("DisplayVersion"), code), detail_only=here)
    win_codes = {c.lower() for c in ua}
    for code, dn in sorted(wine_dn.items(), key=lambda x: x[1]):
        if code not in win_codes and RELEVANT.search(dn):
            r.line("- only ours: `%s` (%s)" % (dn, code))

    # 7. Environment, tasks
    r.h("7. Machine environment and scheduled tasks")
    def envf(p):
        d = {}
        try:
            for line in read_text(p).splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    d[k.strip()] = v
        except OSError:
            pass
        return d
    eb, ea = envf(os.path.join(before, "env-machine.txt")), envf(os.path.join(after, "env-machine.txt"))
    wenv = wine.get(("hklm", "system\\controlset001\\control\\session manager\\environment"), {})
    for k in sorted(ea):
        if eb.get(k) == ea[k]:
            continue
        if k.lower() == "path":
            old = {x.lower() for x in eb.get(k, "").split(";")}
            wp = (wine_string(wenv.get("path", (None, None))[1]) or "").lower().split(";")
            for x in ea[k].split(";"):
                if x and x.lower() not in old:
                    r.line("- PATH += `%s` (%s)" % (x, "in prefix" if x.lower() in wp else "not in prefix"))
        else:
            r.line("- `%s` = `%s` (%s)" % (k, ea[k], "in prefix" if k.lower() in wenv else "not in prefix"))
    def tasks(p):
        try:
            with open(p, encoding="utf-8-sig") as f:
                return {(row["TaskPath"] + row["TaskName"]) for row in csv.DictReader(f)}
        except OSError:
            return set()
    for t in sorted(tasks(os.path.join(after, "tasks.csv")) - tasks(os.path.join(before, "tasks.csv"))):
        r.line("- new scheduled task on Windows: `%s` (Wine has no task scheduler)" % t)

    print("\n".join(r.summary))
    if a.details:
        with open(a.details, "w") as f:
            f.write("\n".join(r.details) + "\n")
        print("\nfull lists: %s" % mask(a.details, r.users))


if __name__ == "__main__":
    main()
