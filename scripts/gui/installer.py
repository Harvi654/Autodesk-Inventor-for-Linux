"""Graphical installer for Autodesk Inventor on Linux (GTK 4).

A front end for scripts/install.sh: it checks the system, lets you pick
Autodesk's downloads and the options, then runs install.sh and follows its
output - the phases ("@@phase N TOTAL title" lines, printed when INV_GUI=1),
the numbered steps inside a phase ("[ 3/20] ...") and download percentages.
The sudo password is asked by askpass.py (SUDO_ASKPASS). Everything the
terminal installer does still happens in install.sh; finished work is skipped
when it is run again.

Start it with: bash scripts/install-gui.sh
"""
import glob
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gio, GLib, Gtk, Pango  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
REPO = os.path.dirname(SCRIPTS)
APP_ID = "io.github.harvi654.InventorInstaller"
README = "https://github.com/Harvi654/Autodesk-Inventor-for-Linux#readme"

# install.sh's phases and how long each one takes, roughly (for one progress bar)
PHASES = [
    ("Checking the system", 1),
    ("System packages", 8),
    ("Wine with this project's fixes", 5),
    ("Unpacking the downloads", 14),
    ("Installing Inventor", 40),
    ("Updates", 14),
    ("Setting up Wine for Inventor", 12),
    ("App launcher and browser sign-in", 4),
]
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
SUBSTEP = re.compile(r"^\s*\[\s*(\d+)\s*/\s*(\d+)\]\s*(.*)$")
PERCENT = re.compile(r"(\d{1,3}(?:\.\d+)?)%")
GB = 1024 ** 3


# --------------------------------------------------------------------- system

def project_settings():
    """INV_PREFIX, INV_DATA_DIR, ... as the scripts see them (config.env included),
    and "installs": the installed Inventor releases [(year, prefix)], oldest first."""
    names = ["INV_PREFIX", "INV_DATA_DIR", "INV_DISTRO", "INV_YEAR", "INV_CONFIG_PREFIX"]
    script = ('source "$1/lib/common.sh" >/dev/null 2>&1; printf "%s\\n" '
              + " ".join('"$%s"' % n for n in names) + '; inventor_installs')
    try:
        out = subprocess.run(["bash", "-c", script, "bash", SCRIPTS], capture_output=True,
                             text=True, timeout=30).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        out = []
    vals = dict(zip(names, out[:len(names)] + [""] * len(names)))
    vals["installs"] = [tuple(l.split("\t", 1)) for l in out[len(names):] if "\t" in l]
    home = os.path.expanduser("~")
    vals["INV_YEAR"] = vals["INV_YEAR"] or "2026"
    vals["INV_PREFIX"] = vals["INV_PREFIX"] or os.path.join(home, ".wine-inventor" + vals["INV_YEAR"])
    vals["INV_DATA_DIR"] = vals["INV_DATA_DIR"] or os.path.join(home, "Inventor")
    return vals


YEAR = re.compile(r"^Inventor(?:_Professional)?_(20\d\d)", re.I)


def release_of(path):
    """2027 for Inventor_Professional_2027_..., Inventor_2027.1_Update.exe or such a folder; None else."""
    m = YEAR.match(os.path.basename(path.rstrip("/")))
    return m.group(1) if m else None


def prefix_for(settings, year):
    """Where Inventor <year> is (or goes): its installed prefix; for the very first
    installation the prefix from config.env; else ~/.wine-inventor<year>."""
    for y, p in settings["installs"]:
        if y == year:
            return p
    cfg = settings.get("INV_CONFIG_PREFIX") or ""
    if cfg and not settings["installs"]:
        return cfg
    return os.path.join(os.path.expanduser("~"), ".wine-inventor" + year)


def os_release():
    info = {}
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if "=" in line:
                    k, v = line.rstrip("\n").split("=", 1)
                    info[k] = v.strip('"')
    except OSError:
        pass
    return info


def gpu_names():
    if not shutil.which("lspci"):
        return []
    try:
        out = subprocess.run(["lspci"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [l.split(": ", 1)[-1] for l in out.splitlines() if re.search(r"VGA|3D|Display", l)]


def mem_total_gb():
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1024 / 1024
    except OSError:
        pass
    return 0


def system_checks(settings):
    """[(state, title, detail)] with state 'ok' / 'warn' / 'bad'."""
    checks = []
    rel = os_release()
    ids = (rel.get("ID", "") + " " + rel.get("ID_LIKE", "")).split()
    name = rel.get("PRETTY_NAME", "unknown")
    if any(i in ("arch", "debian", "ubuntu", "fedora") for i in ids):
        checks.append(("ok", "Distribution", name))
    else:
        checks.append(("bad", "Distribution", name + " - supported: Arch, Ubuntu / Debian, Fedora"))
    arch = os.uname().machine
    checks.append(("ok" if arch == "x86_64" else "bad", "Processor", arch))
    mem = mem_total_gb()
    checks.append(("ok" if mem >= 15 else "warn", "Memory",
                   "%.0f GB%s" % (mem, "" if mem >= 15 else " - 16 GB or more recommended")))
    home = os.path.expanduser("~")
    free = shutil.disk_usage(home).free / GB
    if free >= 60:
        checks.append(("ok", "Free disk space", "%.0f GB in %s" % (free, home)))
    elif free >= 40:
        checks.append(("warn", "Free disk space", "%.0f GB - enough without Content Center (~60 GB with it)" % free))
    else:
        checks.append(("bad", "Free disk space", "%.0f GB - at least 40 GB needed" % free))
    gpus = gpu_names()
    if gpus:
        nvidia = any("NVIDIA" in g.upper() for g in gpus)
        checks.append(("warn" if nvidia else "ok", "Graphics", "; ".join(gpus)
                       + (" - needs NVIDIA's own driver with Vulkan" if nvidia else "")))
    else:
        checks.append(("warn", "Graphics", "unknown (lspci not found)"))
    session = os.environ.get("XDG_SESSION_TYPE", "") or ("wayland" if os.environ.get("WAYLAND_DISPLAY") else "x11")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "unknown")
    checks.append(("ok", "Desktop", "%s (%s)" % (desktop, session)))
    checks.append(("ok" if shutil.which("sudo") else "bad", "sudo", "found" if shutil.which("sudo") else "not installed"))
    return checks


def installed_inventor(prefix, year):
    exe = os.path.join(prefix, "drive_c", "Program Files", "Autodesk", "Inventor " + year, "Bin", "Inventor.exe")
    return os.path.isfile(exe)


def find_downloads():
    """Autodesk downloads lying around: [(path, kind)] with kind 'product' / 'update'."""
    home = os.path.expanduser("~")
    roots = []
    for d in (GLib.UserDirectory.DIRECTORY_DOWNLOAD, GLib.UserDirectory.DIRECTORY_DESKTOP):
        p = GLib.get_user_special_dir(d)
        if p and p not in roots and os.path.realpath(p) != os.path.realpath(home):
            roots.append(p)
    roots += [os.path.join(home, "Downloads"), home]
    seen, found = set(), []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for depth in (("*",) if root == home else ("*", "*/*", "*/*/*")):
            for p in glob.glob(os.path.join(root, depth)):
                low = os.path.basename(p).lower()
                if not os.path.isfile(p) or "inventor" not in low or not low.endswith((".exe", ".7z")):
                    continue
                if "webinstall" in low or "create_installer" in low:  # Windows-only web installers
                    continue
                rp = os.path.realpath(p)
                if rp in seen:
                    continue
                seen.add(rp)
                found.append((rp, "update" if "update" in low else "product"))
    return sorted(found)


def cached_media():
    """Downloads unpacked by an earlier run (~/.cache/inventor-on-linux/media)."""
    cache = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
                         "inventor-on-linux", "media")
    return sorted(d for d in glob.glob(os.path.join(cache, "*"))
                  if os.path.isfile(os.path.join(d, ".unpacked")) and "inventor" in os.path.basename(d).lower())


def dir_size(path):
    """Bytes in a folder (du), None if it is not there."""
    if not os.path.exists(path):
        return None
    try:
        out = subprocess.run(["du", "-sb", path], capture_output=True, text=True, timeout=600).stdout
        return int(out.split()[0])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def fmt_bytes(n):
    if n is None:
        return "not there"
    if n >= GB:
        return "%.1f GB" % (n / GB)
    return "%.0f MB" % (n / 1024 / 1024)


def wine_running():
    try:
        return subprocess.run(["pgrep", "-x", "wineserver"], capture_output=True).returncode == 0
    except OSError:
        return False


def project_version():
    try:
        out = subprocess.run(["git", "-C", REPO, "describe", "--tags", "--always"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return out or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def prefix_not_ours(pre):
    """A prefix folder exists that this installer did not make (install.sh refuses it)."""
    return os.path.isdir(os.path.join(pre, "drive_c")) and \
        not os.path.isfile(os.path.join(pre, ".odis-install-state.json"))


PART = re.compile(r"^(.*)_(\d{3})_(\d{3})\.(exe|7z)$", re.I)


def download_problems(paths):
    """Warnings about the selected downloads: missing parts, unfinished browser downloads."""
    problems = []
    groups = {}
    for p in paths:
        m = PART.match(os.path.basename(p))
        if m:
            key = (os.path.dirname(p), m.group(1).lower(), int(m.group(3)))
            groups.setdefault(key, (m.group(1), set()))[1].add(int(m.group(2)))
    for (folder, _, total), (base, have) in groups.items():
        missing = [i for i in range(1, total + 1) if i not in have]
        if missing:
            problems.append("part %s of %d of %s is not selected - Autodesk's download comes in %d files"
                            % (", ".join(str(i) for i in missing), total, base, total))
    for folder in {os.path.dirname(p) for p in paths if os.path.isfile(p)}:
        for f in glob.glob(os.path.join(folder, "*")):
            low = f.lower()
            if "inventor" in low and low.endswith((".part", ".crdownload", ".download", ".partial")):
                problems.append("unfinished browser download: %s - wait until it is complete"
                                % os.path.basename(f))
    return problems


# known failures -> what to do (matched against the installer's output)
HINTS = [
    ("No space left on device", "The disk is full. Free some space (see the Uninstall page for what the "
                                "installation uses) and try again."),
    ("no password was provided", "The password prompt was closed. Try again and enter your password."),
    ("incorrect password", "The password was wrong. Try again."),
    ("a password is required", "sudo needs your password. Try again and enter it in the password window."),
    ("is not in the sudoers file", "Your user may not use sudo. Ask the administrator of this computer, "
                                   "or add your user to the 'wheel' (Arch, Fedora) / 'sudo' (Ubuntu) group."),
    ("Could not resolve host", "No internet connection (or GitHub is not reachable). Check the network "
                               "and try again."),
    ("curl: (7)", "The download server could not be reached. Check the network and try again."),
    ("checksum mismatch", "A download was damaged or changed. Try again; if it repeats, open an issue."),
    ("enable [multilib]", "Arch: enable the [multilib] repository in /etc/pacman.conf, run "
                          "'sudo pacman -Syu', then try again."),
    ("was not made by this installer", "A Wine prefix with this name already exists. Remove or rename it, "
                                       "or set another INV_PREFIX in config.env."),
    ("close Inventor", "Close Inventor (and other Wine programs) first, then try again."),
    ("none of the downloads is the Inventor installer", "Select the Inventor download itself, not only "
                                                         "the update."),
    ("downloads of several Inventor releases", "Select the downloads of one Inventor release at a time "
                                               "(e.g. only 2027), install it, then run the installer again "
                                               "for the other one."),
    ("not an Inventor download", "One of the selected files is not an Inventor download (e.g. the web "
                                 "installer). Select the ..._db_... files."),
]


def human_size(path):
    try:
        if os.path.isdir(path):
            return "folder"
        n = os.path.getsize(path)
    except OSError:
        return ""
    return "%.1f GB" % (n / GB) if n >= GB else "%.0f MB" % (n / 1024 / 1024)


# ------------------------------------------------------------------------- UI

def margin(widget, m):
    for side in ("top", "bottom", "start", "end"):
        getattr(widget, "set_margin_" + side)(m)
    return widget


def label(text="", markup=None, css=None, wrap=True, xalign=0.0, selectable=False):
    lb = Gtk.Label(xalign=xalign, wrap=wrap, selectable=selectable)
    if markup is not None:
        lb.set_markup(markup)
    else:
        lb.set_text(text)
    if css:
        for c in css.split():
            lb.add_css_class(c)
    return lb


def esc(s):
    return GLib.markup_escape_text(s)


CSS = """
.phase-done { color: #26a269; }
.phase-now { font-weight: bold; }
.phase-todo { opacity: 0.55; }
.state-ok { color: #26a269; font-weight: bold; }
.state-warn { color: #c88800; font-weight: bold; }
.state-bad { color: #e01b24; font-weight: bold; }
.log { font-family: monospace; font-size: 9pt; }
.big { font-size: 15pt; font-weight: bold; }
"""


class Installer(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Autodesk Inventor on Linux")
        self.set_default_size(820, 680)
        self.settings = project_settings()
        self.proc = None
        self.cancelled = False
        self.running_install = False
        self.last_args = None
        self.last_env = {}
        self.logfile = None
        self.errors = []

        provider = Gtk.CssProvider()
        if hasattr(provider, "load_from_string"):      # GTK 4.12+
            provider.load_from_string(CSS)
        else:
            try:
                provider.load_from_data(CSS, -1)
            except TypeError:
                provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(self.get_display(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        header = Gtk.HeaderBar()
        header.set_title_widget(label("Autodesk Inventor on Linux", css="heading", wrap=False))
        self.set_titlebar(header)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, vexpand=True)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(self.stack)
        self.nav = Gtk.Box(spacing=8)
        margin(self.nav, 12)
        self.back_btn = Gtk.Button(label="Back")
        self.next_btn = Gtk.Button(label="Next")
        self.next_btn.add_css_class("suggested-action")
        self.quit_btn = Gtk.Button(label="Cancel")
        self.quit_btn.connect("clicked", lambda *_: self.close())
        spacer = Gtk.Box(hexpand=True)
        self.nav_hint = label("", css="dim-label caption")
        self.nav.append(self.back_btn)
        self.nav.append(self.nav_hint)
        self.nav.append(spacer)
        self.nav.append(self.quit_btn)
        self.nav.append(self.next_btn)
        outer.append(Gtk.Separator())
        outer.append(self.nav)
        self.set_child(outer)
        self.back_btn.connect("clicked", self.on_back)
        self.next_btn.connect("clicked", self.on_next)

        self.pages = ["welcome", "downloads", "options", "summary", "progress", "done"]
        self.stack.add_named(self.page_welcome(), "welcome")
        # every page scrolls, so the window fits small screens (and GTK does not complain)
        for name, page in (("downloads", self.page_downloads()), ("options", self.page_options()),
                           ("summary", self.page_summary()), ("progress", self.page_progress()),
                           ("done", self.page_done()), ("uninstall", self.page_uninstall())):
            scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
            scroll.set_child(page)
            self.stack.add_named(scroll, name)
        self.mode = "install"
        self.inhibit_cookie = 0
        self.recent = []
        self.show_page("welcome")
        self.connect("close-request", self.on_close_request)

    # ---------------------------------------------------------------- target

    def selected_releases(self):
        """Inventor releases of the selected downloads (from their names)."""
        return sorted({y for y in (release_of(p) for p in self.selected_downloads()) if y})

    def target(self):
        """(year, prefix) the next run installs or repairs: the release of the selected
        downloads; with none selected the newest installed one (a repair)."""
        rels = self.selected_releases() if hasattr(self, "dl_rows") else []
        if rels:
            year = rels[-1]
        elif self.settings["installs"]:
            year = self.settings["installs"][-1][0]
        else:
            year = self.settings["INV_YEAR"]
        return year, prefix_for(self.settings, year)

    def target_installed(self):
        year, prefix = self.target()
        return installed_inventor(prefix, year)

    # ------------------------------------------------------------- navigation

    def show_page(self, name):
        self.stack.set_visible_child_name(name)
        wizard = name in ("welcome", "downloads", "options", "summary", "uninstall")
        self.back_btn.set_visible(name in ("downloads", "options", "summary", "uninstall"))
        self.next_btn.set_visible(wizard)
        self.quit_btn.set_visible(wizard)
        self.nav_hint.set_text("")
        self.next_btn.remove_css_class("destructive-action")
        self.next_btn.add_css_class("suggested-action")
        self.next_btn.set_label({"summary": "Repair" if self.target_installed() else "Install",
                                 "uninstall": "Uninstall…"}.get(name, "Next"))
        if name == "summary":
            self.fill_summary()
        if name == "options":
            year, prefix = self.target()
            self.where.set_text("Inventor %s (Wine prefix): %s\nYour files (drive D: in Inventor): %s\n"
                                "To use other folders set INV_PREFIX / INV_DATA_DIR in config.env "
                                "(see config.env.example) before installing."
                                % (year, prefix, self.settings["INV_DATA_DIR"]))
        if name == "welcome":
            self.next_btn.set_sensitive(self.checks_ok)
        elif name == "downloads":
            self.update_downloads_state()
        elif name == "summary":
            self.next_btn.set_sensitive(self.summary_ok)
        elif name == "uninstall":
            self.next_btn.remove_css_class("suggested-action")
            self.next_btn.add_css_class("destructive-action")
            self.refresh_uninstall()
        else:
            self.next_btn.set_sensitive(True)

    def on_back(self, *_):
        cur = self.stack.get_visible_child_name()
        if cur == "uninstall":
            self.show_page("welcome")
            return
        self.show_page(self.pages[self.pages.index(cur) - 1])

    def on_next(self, *_):
        cur = self.stack.get_visible_child_name()
        if cur == "summary":
            self.check_wine_then(self.start_install)
        elif cur == "uninstall":
            self.confirm_uninstall()
        else:
            self.show_page(self.pages[self.pages.index(cur) + 1])

    def alert(self, message, detail, buttons, callback):
        dlg = Gtk.AlertDialog(message=message, detail=detail, buttons=buttons,
                              cancel_button=0, default_button=0)

        def done(d, res):
            try:
                idx = d.choose_finish(res)
            except GLib.Error:
                return
            callback(idx)
        dlg.choose(self, None, done)

    def check_wine_then(self, action):
        """Inventor (Wine) must not run while installing or removing."""
        if not wine_running():
            action()
            return

        def chosen(idx):
            if idx == 1:
                self.kill_wine()
                GLib.timeout_add(2500, lambda: (action(), False)[1])
        self.alert("Inventor or another Wine program is running",
                   "Close Inventor first (save your work), or let the installer end all Wine programs.",
                   ["Cancel", "End Wine programs and continue"], chosen)

    def kill_wine(self):
        subprocess.Popen(["bash", "-c", 'source "$1/lib/common.sh" >/dev/null 2>&1; select_wine >/dev/null 2>&1; '
                          'wineserver -k 2>/dev/null; true', "bash", SCRIPTS],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ---------------------------------------------------------------- welcome

    def page_welcome(self):
        box = margin(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), 24)
        box.append(label(markup="<span size='x-large' weight='bold'>Install Autodesk Inventor</span>"))
        box.append(label("Inventor is installed from Autodesk's own download and runs under Wine - "
                         "no Windows, no virtual machine. You need your own Inventor license "
                         "(an education license works). This is an unofficial community project, "
                         "not made or supported by Autodesk. Several releases (e.g. 2026 and 2027) "
                         "can be installed side by side, each in its own Wine prefix."))

        grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        checks = system_checks(self.settings)
        self.checks_ok = all(s != "bad" for s, _, _ in checks)
        for row, (state, title, detail) in enumerate(checks):
            mark = {"ok": "✓", "warn": "!", "bad": "✗"}[state]
            grid.attach(label(mark, css="state-" + state, wrap=False), 0, row, 1, 1)
            grid.attach(label(title, wrap=False), 1, row, 1, 1)
            grid.attach(label(detail), 2, row, 1, 1)
        # all fine: one line, the details folded away (the page fits the window
        # with several installed releases); a warning or a problem: open
        worst = "bad" if not self.checks_ok else ("warn" if any(s == "warn" for s, _, _ in checks) else "ok")
        summary = {"ok": "✓ Your system is suitable", "warn": "! Your system - see the notes",
                   "bad": "✗ Your system can't run the installation"}[worst]
        exp = Gtk.Expander(expanded=worst != "ok")
        exp.set_label_widget(label(summary, css="state-" + worst, wrap=False))
        exp.set_child(margin(grid, 12))
        box.append(exp)
        if not self.checks_ok:
            box.append(label(markup="<b>This system can't run the installation</b> - see the ✗ above."))
        cfg = self.settings.get("INV_CONFIG_PREFIX") or ""
        if cfg and prefix_not_ours(cfg) and not self.settings["installs"]:
            box.append(label(markup="<b>Note:</b> %s already exists but was not made by this installer. "
                             "The installation refuses to use it - remove or rename it first, or set another "
                             "INV_PREFIX in config.env." % esc(cfg)))
        if wine_running():
            box.append(label(markup="<b>Note:</b> Inventor or another Wine program is running. "
                             "Close it before you install, repair or uninstall."))

        if self.settings["installs"]:
            inst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            inst.append(label(markup="<b>Installed</b>"))
            for year, prefix in self.settings["installs"]:
                row = Gtk.Box(spacing=8)
                text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
                text.append(label(markup="<b>Inventor %s</b>" % esc(year)))
                text.append(label(prefix, css="dim-label caption"))
                row.append(text)
                start = Gtk.Button(label="Start", valign=Gtk.Align.CENTER)
                start.connect("clicked", lambda _b, p=prefix: self.launch_inventor(p))
                row.append(start)
                inst.append(row)
            inst.append(label("Next installs another release (from its download) or repairs an installed "
                              "one - finished parts are skipped. Or update this project and its Wine:"))
            update = Gtk.Button(label="Update project and Wine", halign=Gtk.Align.START)
            update.connect("clicked", lambda *_: self.start_update())
            inst.append(update)
            frame2 = Gtk.Frame()
            frame2.set_child(margin(inst, 12))
            box.append(frame2)

        foot = Gtk.Box(spacing=8)
        foot.append(label("Version %s" % project_version(), css="dim-label caption", wrap=False))
        foot.append(Gtk.Box(hexpand=True))
        help_btn = Gtk.Button(label="Help")
        help_btn.connect("clicked", lambda *_: self.open_web(README))
        foot.append(help_btn)
        if self.anything_installed():
            uninst = Gtk.Button(label="Uninstall…")
            uninst.connect("clicked", lambda *_: self.show_page("uninstall"))
            foot.append(uninst)
        box.append(Gtk.Box(vexpand=True))
        box.append(foot)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(box)
        return scroll

    def anything_installed(self):
        return any(os.path.exists(p) for _, _, p, _ in self.uninstall_items())

    # -------------------------------------------------------------- uninstall

    def uninstall_items(self):
        """(key, title, path, default); "rel:2027" = that release: its prefix and menu entry."""
        s = self.settings
        data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        cache = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "inventor-on-linux")
        items = [("rel:" + y, "Inventor %s - the program in its Wine prefix, its app menu entry" % y, p, True)
                 for y, p in s["installs"]]
        if not s["installs"]:
            items.append(("desktop", "App menu entries, file types, browser sign-in handler",
                          os.path.join(data_home, "applications", "autodesk-inventor-%s.desktop" % s["INV_YEAR"]),
                          True))
        return items + [
            ("wine", "This project's Wine", os.path.join(data_home, "inventor-on-linux"), True),
            ("cache", "Unpacked downloads (Autodesk's files in Downloads stay)", cache, True),
            ("data", "YOUR Inventor files - parts, assemblies, drawings", s["INV_DATA_DIR"], False),
            ("project", "This installer and its scripts (the one-command line brings it back)", REPO, False),
        ]

    def page_uninstall(self):
        box = margin(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), 24)
        box.append(label(markup="<span size='large' weight='bold'>Uninstall</span>"))
        box.append(label("Choose what to remove. Your own Inventor files are kept unless you tick them. "
                         "System packages installed for Wine stay - they are ordinary packages of your "
                         "distribution."))
        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        self.un_checks = {}
        self.un_sizes = {}
        for row, (key, title, path, default) in enumerate(self.uninstall_items()):
            check = Gtk.CheckButton(active=default)
            check.connect("toggled", lambda *_: self.update_uninstall_state())
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            text.append(label(markup=("<b>%s</b>" if key == "data" else "%s") % esc(title)))
            text.append(label(path, css="dim-label caption"))
            size = label("…", css="dim-label", wrap=False, xalign=1.0)
            grid.attach(check, 0, row, 1, 1)
            grid.attach(text, 1, row, 1, 1)
            grid.attach(size, 2, row, 1, 1)
            text.set_hexpand(True)
            self.un_checks[key] = check
            self.un_sizes[key] = size
        box.append(grid)
        self.un_note = label("")
        box.append(self.un_note)
        return box

    def refresh_uninstall(self):
        items = self.uninstall_items()
        for key, _, path, _ in items:
            self.un_sizes[key].set_text("…")

        def work():
            for key, _, path, _ in items:
                n = None if key == "desktop" and not os.path.exists(path) else \
                    (0 if key == "desktop" else dir_size(path))
                txt = ("in the menu" if os.path.exists(path) else "not there") if key == "desktop" else fmt_bytes(n)
                GLib.idle_add(self.un_sizes[key].set_text, txt)
        threading.Thread(target=work, daemon=True).start()
        self.update_uninstall_state()

    def update_uninstall_state(self):
        chosen = [k for k, c in self.un_checks.items() if c.get_active()]
        self.next_btn.set_sensitive(bool(chosen))
        if "data" in chosen:
            self.un_note.set_markup("<b>Your own Inventor files will be deleted.</b> Copy what you want to keep first.")
        elif "project" in chosen:
            self.un_note.set_text("The installer removes itself last; this window closes then.")
        else:
            self.un_note.set_text("")

    def confirm_uninstall(self):
        chosen = [k for k, c in self.un_checks.items() if c.get_active()]
        titles = {k: t for k, t, _, _ in self.uninstall_items()}
        detail = "\n".join("• " + titles[k] for k in chosen)
        if "data" in chosen:
            detail += "\n\nYOUR INVENTOR FILES (%s) WILL BE DELETED - this cannot be undone." % self.settings["INV_DATA_DIR"]

        def chosen_cb(idx):
            if idx == 1:
                # each release with its own prefix, then the shared parts (the project last)
                un = os.path.join(SCRIPTS, "uninstall.sh")
                cmds = []
                for k in chosen:
                    if k.startswith("rel:"):
                        year = k[4:]
                        prefix = dict(self.settings["installs"])[year]
                        cmds.append("INV_YEAR=%s INV_PREFIX=%s bash %s --yes --prefix --desktop"
                                    % (year, shlex.quote(prefix), shlex.quote(un)))
                rest = [k for k in chosen if not k.startswith("rel:")]
                if rest:
                    cmds.append("bash %s --yes %s" % (shlex.quote(un), " ".join("--" + k for k in rest)))
                args = ["bash", "-c", "set -e; " + "; ".join(cmds)]
                self.last_args = args
                self.check_wine_then(lambda: self.run_command(args, "Uninstalling", mode="uninstall"))
        self.alert("Remove these?", detail, ["Cancel", "Remove"], chosen_cb)

    # -------------------------------------------------------------- downloads

    def page_downloads(self):
        box = margin(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), 24)
        box.append(label(markup="<span size='large' weight='bold'>Autodesk's download</span>"))
        box.append(label(markup="Download Inventor in your Autodesk account with <b>Browser download</b> "
                         "(Windows, your language) - all parts, e.g. <tt>…_db_001_002.exe</tt> and "
                         "<tt>…_db_002_002.7z</tt>. Updates such as <tt>Inventor_2026.4_Update.exe</tt> "
                         "are optional. Found on this computer:"))
        self.dl_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.dl_list.add_css_class("boxed-list")
        # with downloads of several releases: which one to install now
        self.rel_bar = Gtk.Box(spacing=8, visible=False)
        box.append(self.rel_bar)
        scroll = Gtk.ScrolledWindow(vexpand=True, min_content_height=200)
        scroll.set_child(self.dl_list)
        box.append(scroll)
        row = Gtk.Box(spacing=8)
        add_files = Gtk.Button(label="Add files…")
        add_files.connect("clicked", self.on_add_files)
        add_dir = Gtk.Button(label="Add folder…")
        add_dir.connect("clicked", self.on_add_folder)
        rescan = Gtk.Button(label="Search again")
        rescan.connect("clicked", lambda *_: self.fill_downloads())
        row.append(add_files)
        row.append(add_dir)
        row.append(rescan)
        box.append(row)
        self.dl_hint = label("")
        box.append(self.dl_hint)
        self.dl_rows = []
        self.fill_downloads()
        return box

    def fill_downloads(self, extra=()):
        old = {p: c.get_active() for p, _, c in self.dl_rows}
        paths = [(p, k) for p, k in find_downloads()]
        for p in cached_media():
            paths.append((p, "unpacked earlier"))
        for p in extra:
            paths.append((p, "folder" if os.path.isdir(p) else
                          ("update" if "update" in os.path.basename(p).lower() else "product")))
        for p, _, _ in self.dl_rows:  # keep what was added by hand
            if p not in [q for q, _ in paths]:
                paths.append((p, "added"))
        child = self.dl_list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.dl_list.remove(child)
            child = nxt
        self.dl_rows = []
        uniq = []
        for p, k in paths:
            if p not in [q for q, _ in uniq]:
                uniq.append((p, k))
        # one release is selected by default: the newest one not installed yet,
        # else the newest (a repair); buttons above the list switch to another
        rels = sorted({y for y in (release_of(p) for p, _ in uniq) if y})
        installed = {y for y, _ in self.settings["installs"]}
        new = [y for y in rels if y not in installed]
        self.default_release = (new or rels or [None])[-1]
        defaults = self.default_selection(uniq, self.default_release)
        for p, kind in uniq:
            check = Gtk.CheckButton()
            check.set_active(old.get(p, p in defaults))
            check.connect("toggled", lambda *_: self.update_downloads_state())
            line = Gtk.Box(spacing=10)
            margin(line, 6)
            line.append(check)
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            text.append(label(os.path.basename(p.rstrip("/")) or p, wrap=False))
            rel = release_of(p)
            text.append(label("%s%s · %s · %s" % ("Inventor %s · " % rel if rel else "", kind, human_size(p),
                                                  os.path.dirname(p)), css="dim-label caption"))
            line.append(text)
            self.dl_list.append(line)
            self.dl_rows.append((p, kind, check))
        if not uniq:
            self.dl_list.append(margin(label("Nothing found in Downloads - use Add files… or Add folder…"), 12))
        self.fill_release_bar(rels, installed)
        self.update_downloads_state()

    def default_selection(self, rows, year):
        """Paths selected for release <year>: one copy of each file; a download unpacked
        earlier only when there is no fresh one of that release."""
        mine = [(p, k) for p, k in rows if release_of(p) in (year, None)]
        have_product = any(k == "product" for _, k in mine)
        names_on, chosen = set(), set()
        for p, kind in mine:
            name = os.path.basename(p.rstrip("/")).lower()
            if (kind != "unpacked earlier" or not have_product) and name not in names_on:
                names_on.add(name)
                chosen.add(p)
        return chosen

    def fill_release_bar(self, rels, installed):
        child = self.rel_bar.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.rel_bar.remove(child)
            child = nxt
        self.rel_bar.set_visible(len(rels) > 1)
        if len(rels) < 2:
            return
        self.rel_bar.append(label("Downloads of %d releases - install:" % len(rels), wrap=False))
        for y in rels:
            b = Gtk.Button(label="Inventor %s%s" % (y, " (repair)" if y in installed else ""))
            b.connect("clicked", lambda _b, y=y: self.select_release(y))
            self.rel_bar.append(b)

    def select_release(self, year):
        chosen = self.default_selection([(p, k) for p, k, _ in self.dl_rows], year)
        for p, _, check in self.dl_rows:
            check.set_active(p in chosen)
        self.update_downloads_state()

    def selected_downloads(self):
        return [p for p, _, c in self.dl_rows if c.get_active()]

    def update_downloads_state(self):
        sel = self.selected_downloads()
        installed = bool(self.settings["installs"])
        rels = self.selected_releases()
        ok = (bool(sel) or installed) and len(rels) <= 1
        if self.stack.get_visible_child_name() == "downloads":
            self.next_btn.set_sensitive(ok)
        problems = download_problems(sel)
        if len(rels) > 1:
            problems.insert(0, "downloads of several releases are selected (%s) - install one release at a "
                               "time" % ", ".join(rels))
        if sel and problems:
            self.dl_hint.set_markup("<b>Check:</b> " + esc("; ".join(problems)))
        elif sel:
            year, prefix = self.target()
            self.dl_hint.set_text("%d selected - Inventor %s, %s." % (
                len(sel), year, "repair of the installation in " + prefix if self.target_installed()
                else "new installation into " + prefix))
        elif installed:
            self.dl_hint.set_text("Nothing selected - fine for a repair of the existing installation "
                                  "only if its unpacked download is still in the cache.")
        else:
            self.dl_hint.set_text("Select Autodesk's download to continue.")

    def on_add_files(self, *_):
        dlg = Gtk.FileDialog(title="Autodesk's download (.exe / .7z)")
        filt = Gtk.FileFilter()
        filt.set_name("Autodesk downloads (*.exe, *.7z)")
        filt.add_pattern("*.exe")
        filt.add_pattern("*.7z")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filt)
        dlg.set_filters(filters)

        def done(d, res):
            try:
                files = d.open_multiple_finish(res)
            except GLib.Error:
                return
            paths = [files.get_item(i).get_path() for i in range(files.get_n_items())]
            self.fill_downloads(extra=[p for p in paths if p])
        dlg.open_multiple(self, None, done)

    def on_add_folder(self, *_):
        dlg = Gtk.FileDialog(title="Folder with Autodesk's download")

        def done(d, res):
            try:
                f = d.select_folder_finish(res)
            except GLib.Error:
                return
            if f and f.get_path():
                self.fill_downloads(extra=[f.get_path()])
        dlg.select_folder(self, None, done)

    # ---------------------------------------------------------------- options

    def page_options(self):
        box = margin(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16), 24)
        box.append(label(markup="<span size='large' weight='bold'>Options</span>"))

        def option(title, detail, active):
            row = Gtk.Box(spacing=12)
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            text.append(label(markup="<b>%s</b>" % esc(title)))
            text.append(label(detail, css="dim-label"))
            sw = Gtk.Switch(active=active, valign=Gtk.Align.CENTER)
            row.append(text)
            row.append(sw)
            box.append(row)
            return sw

        self.sw_content = option("Content Center libraries",
                                 "Standard parts - screws, nuts, profiles - also needed by Frame Generator "
                                 "and Design Accelerator. About 12.7 GB.", True)
        self.sw_desktop = option("App launcher and file types",
                                 "\"Autodesk Inventor\" in your app menu, sign-in through your browser, "
                                 ".ipt/.iam/.idw files open in Inventor with a double-click.", True)
        box.append(Gtk.Separator())
        box.append(label(markup="<b>Where things go</b>"))
        self.where = label("", selectable=True)
        box.append(self.where)
        return box

    # ---------------------------------------------------------------- summary

    def page_summary(self):
        box = margin(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), 24)
        box.append(label(markup="<span size='large' weight='bold'>Ready to install</span>"))
        self.summary = label("", selectable=True)
        self.summary_ok = True
        box.append(self.summary)
        return box

    def fill_summary(self):
        distro = self.settings.get("INV_DISTRO", "")
        pk = {"arch": "pacman (updates the system together with the new packages, as Arch requires)",
              "debian": "apt", "fedora": "dnf"}.get(distro, "your package manager")
        sel = self.selected_downloads()
        year, prefix = self.target()
        repair = self.target_installed()
        lines = [
            "<b>Inventor %s is already installed</b> in %s - this run checks every step and does only what is "
            "missing or broken (a repair). Finished parts are skipped, your files are not touched." %
            (esc(year), esc(prefix)), "",
        ] if repair else ["<b>Inventor %s</b> goes into %s." % (esc(year), esc(prefix)), ""]
        others = [y for y, _ in self.settings["installs"] if y != year]
        if others and not repair:
            lines += ["Inventor %s stays as it is - each release has its own prefix and menu entry."
                      % " and ".join(others), ""]
        lines += [
            "<b>What happens</b>" if not repair else "<b>The steps</b>",
            "1. System packages are installed with %s - this asks for your password once." % esc(pk),
            "2. This project's Wine (~220 MB) is downloaded and checked against its SHA-256.",
            "3. The downloads are unpacked (~10 GB, several minutes).",
            "4. Autodesk's installers run under Wine (15-40 minutes)%s."
            % ("" if self.sw_content.get_active() else ", without Content Center"),
            "5. Updates, Wine settings, fonts%s." % (", app launcher" if self.sw_desktop.get_active() else ""),
            "",
            "<b>Downloads</b>",
        ] + ["• " + esc(os.path.basename(p.rstrip("/"))) for p in sel] + [
            "",
            "You can stop at any time; running the installer again continues where it stopped.",
        ]
        # disk space: prefix (with or without Content Center), unpacked download, Wine
        need = (25 if self.sw_content.get_active() else 12) + 1
        if not any(os.path.isdir(p) for p in cached_media()) or any(not os.path.isdir(p) for p in sel):
            need += 15
        if repair:
            need = 2
        free = shutil.disk_usage(os.path.expanduser("~")).free / GB
        self.summary_ok = free >= need
        lines += ["", "<b>Disk space</b>: about %d GB needed, %.0f GB free%s" %
                  (need, free, "" if self.summary_ok else
                   " - <b>not enough</b>. Free some space, or turn off Content Center.")]
        self.summary.set_markup("\n".join(lines))
        self.next_btn.set_sensitive(self.summary_ok)

    # --------------------------------------------------------------- progress

    def page_progress(self):
        box = margin(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10), 24)
        self.prog_title = label("Installing…", css="big")
        box.append(self.prog_title)

        self.phase_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.phase_labels = []
        for i, (title, _) in enumerate(PHASES):
            lb = label("·  %d. %s" % (i + 1, title), css="phase-todo")
            self.phase_box.append(lb)
            self.phase_labels.append(lb)
        box.append(self.phase_box)

        self.overall = Gtk.ProgressBar(show_text=True)
        box.append(self.overall)
        self.phase_now = label("", markup="")
        box.append(self.phase_now)
        self.sub = Gtk.ProgressBar()
        box.append(self.sub)
        self.sub_label = label("", css="dim-label")
        box.append(self.sub_label)
        self.detail = label("", css="dim-label caption", wrap=False)
        self.detail.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(self.detail)
        self.elapsed = label("", css="dim-label caption")
        box.append(self.elapsed)

        self.log_view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                                     wrap_mode=Gtk.WrapMode.CHAR)
        self.log_view.add_css_class("log")
        self.log_buf = self.log_view.get_buffer()
        self.log_end = self.log_buf.create_mark(None, self.log_buf.get_end_iter(), False)
        scroll = Gtk.ScrolledWindow(vexpand=True, min_content_height=180)
        scroll.set_child(self.log_view)
        exp = Gtk.Expander(label="Details (installer output)", expanded=True, vexpand=True)
        exp.set_child(scroll)
        box.append(exp)

        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        # after the run: back to the result page ("Show details" leads here)
        self.result_btn = Gtk.Button(label="Back to the result", visible=False)
        self.result_btn.add_css_class("suggested-action")
        self.result_btn.connect("clicked", lambda *_: self.show_page("done"))
        row.append(self.result_btn)
        self.cancel_btn = Gtk.Button(label="Stop")
        self.cancel_btn.add_css_class("destructive-action")
        self.cancel_btn.connect("clicked", self.on_cancel)
        row.append(self.cancel_btn)
        box.append(row)
        return box

    def log(self, text):
        buf = self.log_buf
        buf.insert(buf.get_end_iter(), text + "\n")
        lines = buf.get_line_count()
        if lines > 4000:
            cut = buf.get_iter_at_line(lines - 3000)
            if isinstance(cut, tuple):  # GTK 4: (found, iter)
                cut = cut[1]
            buf.delete(buf.get_start_iter(), cut)
        buf.move_mark(self.log_end, buf.get_end_iter())
        self.log_view.scroll_mark_onscreen(self.log_end)

    def set_phase(self, n, title):
        self.phase = n
        self.sub_fraction = None
        self.sub_known = False
        for i, lb in enumerate(self.phase_labels):
            for c in ("phase-done", "phase-now", "phase-todo"):
                lb.remove_css_class(c)
            name = PHASES[i][0] if i != n - 1 or not title else title.rstrip(".")
            if i < n - 1:
                lb.set_text("✓  %d. %s" % (i + 1, PHASES[i][0]))
                lb.add_css_class("phase-done")
            elif i == n - 1:
                lb.set_text("▶  %d. %s" % (i + 1, name))
                lb.add_css_class("phase-now")
            else:
                lb.set_text("·  %d. %s" % (i + 1, PHASES[i][0]))
                lb.add_css_class("phase-todo")
        self.phase_now.set_markup("<b>Step %d of %d:</b> %s" % (n, len(PHASES), esc(title.rstrip("."))))
        self.sub_label.set_text("")
        self.update_overall()

    def update_overall(self):
        if not self.running_install or not self.phase:
            return
        total = sum(w for _, w in PHASES)
        done = sum(w for _, w in PHASES[:self.phase - 1])
        cur = PHASES[self.phase - 1][1] * (self.sub_fraction or 0.0)
        frac = min(1.0, (done + cur) / total)
        self.overall.set_fraction(frac)
        self.overall.set_text("%d %%" % round(frac * 100))
        if self.sub_fraction is not None:
            self.sub.set_fraction(self.sub_fraction)

    def handle_line(self, raw):
        line = ANSI.sub("", raw).rstrip()
        if not line.strip():
            return
        if line.startswith("@@phase "):
            parts = line.split(" ", 3)
            try:
                self.set_phase(int(parts[1]), parts[3] if len(parts) > 3 else "")
            except (ValueError, IndexError):
                pass
            self.skip_bracket = True
            return
        m = SUBSTEP.match(line)
        if m and self.skip_bracket:
            self.skip_bracket = False
            self.log(line)
            return
        self.skip_bracket = False
        if line.lstrip().startswith("log:"):
            self.logfile = line.split("log:", 1)[1].strip()
        if m:
            k, n = int(m.group(1)), int(m.group(2))
            if n > 0:
                self.sub_known = True
                self.sub_fraction = max(0.0, min(1.0, (k - 1) / n))
                self.sub_label.set_text("%d/%d  %s" % (k, n, m.group(3)))
                self.update_overall()
        elif "#" in line and PERCENT.search(line):
            pct = float(PERCENT.findall(line)[-1])
            self.sub_known = True
            self.sub_fraction = max(0.0, min(1.0, pct / 100))
            self.sub_label.set_text("downloading… %d %%" % pct)
            self.update_overall()
            return  # curl's progress bar: not into the log, line by line
        elif "ERROR" in line or "installation stopped" in line:
            self.errors.append(line.strip())
        elif line.startswith("    ") and not self.sub_known:
            self.sub_label.set_text(line.strip()[:160])
        self.detail.set_text(line.strip()[:200])
        self.recent.append(line)
        if len(self.recent) > 600:
            del self.recent[:200]
        self.log(line)

    def tick(self):
        if not self.proc:
            return False
        secs = int(time.time() - self.started)
        self.elapsed.set_text("Elapsed %d:%02d:%02d" % (secs // 3600, secs // 60 % 60, secs % 60))
        if not self.sub_known:
            self.sub.pulse()
        return True

    def run_command(self, args, title, install=False, mode=None, env_extra=None):
        self.mode = mode or ("install" if install else "update")
        self.recent = []
        self.show_page("progress")
        self.prog_title.set_text(title)
        self.phase_box.set_visible(install)
        self.overall.set_visible(install)
        self.phase_now.set_visible(install)
        self.log_buf.set_text("")
        self.errors = []
        self.logfile = None
        self.cancelled = False
        self.running_install = install
        self.phase = 0
        self.sub_fraction = None
        self.sub_known = False
        self.skip_bracket = False
        self.overall.set_fraction(0)
        self.overall.set_text("0 %")
        self.sub.set_fraction(0)
        self.sub_label.set_text("starting…")
        self.detail.set_text("")
        self.run_title = title
        self.cancel_btn.set_sensitive(True)
        self.cancel_btn.set_visible(True)
        self.result_btn.set_visible(False)
        if install:
            self.set_phase(1, PHASES[0][0])
        env = dict(os.environ)
        env.update(env_extra or {})
        env.update({"INV_GUI": "1", "INV_NONINTERACTIVE": "1",
                    "SUDO_ASKPASS": os.path.join(HERE, "askpass.py"),
                    "PYTHONUNBUFFERED": "1", "TERM": "dumb"})
        self.log("$ " + " ".join(args))
        try:
            self.proc = subprocess.Popen(args, cwd=REPO, env=env, stdin=subprocess.DEVNULL,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         start_new_session=True)
        except OSError as e:
            self.finish(False, str(e))
            return
        self.started = time.time()
        app = self.get_application()
        if app and not self.inhibit_cookie:   # no sleep or screen lock in the middle of it
            self.inhibit_cookie = app.inhibit(self, Gtk.ApplicationInhibitFlags.SUSPEND |
                                              Gtk.ApplicationInhibitFlags.IDLE, title)
        GLib.timeout_add(250, self.tick)
        threading.Thread(target=self.reader, args=(self.proc,), daemon=True).start()

    def reader(self, proc):
        buf = b""
        while True:
            chunk = proc.stdout.read1(65536) if hasattr(proc.stdout, "read1") else proc.stdout.read(4096)
            if not chunk:
                break
            buf += chunk
            parts = re.split(rb"[\r\n]", buf)
            buf = parts.pop()
            for p in parts:
                GLib.idle_add(self.handle_line, p.decode("utf-8", "replace"))
        if buf:
            GLib.idle_add(self.handle_line, buf.decode("utf-8", "replace"))
        code = proc.wait()
        GLib.idle_add(self.on_exit, proc, code)

    def on_exit(self, proc, code):
        if proc is not self.proc:
            return False
        self.proc = None
        self.finish(code == 0 and not self.cancelled,
                    "stopped" if self.cancelled else (self.errors[-1] if self.errors else "exit code %d" % code))
        return False

    def on_cancel(self, *_):
        if not self.proc:
            return
        dlg = Gtk.AlertDialog(message="Stop the installation?",
                              detail="Running the installer again later continues where it stopped.",
                              buttons=["Continue installing", "Stop"], cancel_button=0, default_button=0)

        def done(d, res):
            try:
                if d.choose_finish(res) == 1:
                    self.stop_process()
            except GLib.Error:
                pass
        dlg.choose(self, None, done)

    def stop_process(self):
        if not self.proc:
            return
        self.cancelled = True
        self.cancel_btn.set_sensitive(False)
        self.sub_label.set_text("stopping…")
        self.recent.append("(stopped by you)")
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
        except OSError:
            pass
        # Wine programs started by the installer keep running in the background
        self.kill_wine()

    def start_install(self):
        args = ["bash", os.path.join(SCRIPTS, "install.sh")]
        if not self.sw_content.get_active():
            args.append("--no-content")
        if not self.sw_desktop.get_active():
            args.append("--no-desktop")
        year, prefix = self.target()
        sel = self.selected_downloads()
        if not sel:   # a repair: the release's download unpacked earlier
            sel = [p for p in cached_media() if release_of(p) == year]
        args += ["--prefix", prefix] + sel
        self.last_args = args
        self.last_env = {"INV_YEAR": year}
        self.installed_target = (year, prefix)
        self.run_command(args, "Installing Inventor %s" % year, install=True, mode="install",
                         env_extra=self.last_env)

    def start_update(self):
        script = ('set -e; cd "$1"; echo "Updating this project..."; bash scripts/update-project.sh; '
                  'echo "Wine..."; bash scripts/get-wine.sh; '
                  'echo "App launcher and file types..."; bash scripts/install-desktop-integration.sh')
        self.last_args = ["bash", "-c", script, "bash", REPO]
        self.check_wine_then(lambda: self.run_command(self.last_args, "Updating", mode="update"))

    # ------------------------------------------------------------------- done

    def page_done(self):
        box = margin(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14), 24)
        self.done_title = label("", css="big")
        box.append(self.done_title)
        self.done_text = label("", selectable=True)
        box.append(self.done_text)
        self.done_buttons = Gtk.Box(spacing=8)
        box.append(self.done_buttons)
        return box

    def finish(self, success, reason):
        self.running_install = False
        app = self.get_application()
        if app and self.inhibit_cookie:
            app.uninhibit(self.inhibit_cookie)
            self.inhibit_cookie = 0
        if app and not self.is_active():   # the user may be elsewhere after 20-40 minutes
            try:
                n = Gio.Notification.new("Inventor on Linux: " + ("done" if success else "did not finish"))
                n.set_body(self.run_title if success else reason)
                app.send_notification("finished", n)
            except Exception:  # noqa: BLE001 - a notification is a nicety
                pass
        self.cancel_btn.set_visible(False)
        self.result_btn.set_visible(True)
        child = self.done_buttons.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.done_buttons.remove(child)
            child = nxt

        def button(text, cb, suggested=False):
            b = Gtk.Button(label=text)
            if suggested:
                b.add_css_class("suggested-action")
            b.connect("clicked", lambda *_: cb())
            self.done_buttons.append(b)

        if success and self.mode == "uninstall":
            self.done_title.set_text("Removed")
            gone_self = "--project" in " ".join(self.last_args or [])
            self.done_text.set_text("The selected parts are removed." + (
                "\n\nThe installer itself is removed as well. To install again later:\n"
                "bash <(curl -fsSL https://raw.githubusercontent.com/Harvi654/Autodesk-Inventor-for-Linux/main/get.sh)"
                if gone_self else ""))
            button("Close", self.close, suggested=True)
            self.show_page("done")
            return
        if success:
            self.done_title.set_text("Done")
            if self.mode == "install":
                year, _ = self.installed_target
                text = ("Inventor %s is installed - in the app menu as \"Autodesk Inventor %s\". The first start "
                        "asks you to sign in with your Autodesk account in your web browser.\n\nYour files go to "
                        "%s (drive D: in Inventor)." % (year, year, self.settings["INV_DATA_DIR"]))
                if "hyprland" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower():
                    text += ("\n\nHyprland: add this line to ~/.config/hypr/hyprland.conf for Inventor's windows:\n"
                             "source = %s/config/hyprland-inventor.conf" % REPO)
                self.done_text.set_text(text)
            else:
                self.done_text.set_text("Finished.")
            if self.mode == "install":
                button("Start Inventor %s" % self.installed_target[0],
                       lambda: self.launch_inventor(self.installed_target[1]), suggested=True)
            button("Open my Inventor folder", lambda: self.open_uri(self.settings["INV_DATA_DIR"]))
        else:
            what = {"install": "The installation", "update": "The update", "uninstall": "Uninstalling"}[self.mode]
            self.done_title.set_text("Stopped" if self.cancelled else "%s did not finish" % what)
            msg = reason if not self.cancelled else "You stopped it."
            text = "\n".join(self.recent[-80:])
            hints = [h for pat, h in HINTS if pat.lower() in text.lower()]
            if hints and not self.cancelled:
                msg += "\n\nWhat to do: " + hints[-1]
            self.done_text.set_text(msg + "\n\nRunning it again continues where it stopped. If it fails again, "
                                    "open an issue on GitHub with the report (button below).")
            mode = self.mode
            button("Try again", lambda: self.check_wine_then(
                lambda: self.run_command(self.last_args, self.run_title, install=mode == "install", mode=mode,
                                         env_extra=self.last_env if mode == "install" else None)),
                suggested=True)
            if self.logfile:
                button("Open the log", lambda: self.open_uri(self.logfile))
            button("Create a report", self.make_report)
            button("Open an issue", lambda: self.open_web(
                "https://github.com/Harvi654/Autodesk-Inventor-for-Linux/issues/new"))
        button("Show details", lambda: self.show_page("progress"))
        button("Close", self.close)
        self.show_page("done")

    def make_report(self):
        out = os.path.join(os.path.expanduser("~"), "inventor-report.txt")
        with open(out, "w") as f:
            subprocess.run(["bash", os.path.join(SCRIPTS, "report.sh")], stdout=f, stderr=subprocess.STDOUT)
        self.done_text.set_text(self.done_text.get_text() + "\n\nReport written to %s - check it for "
                                "personal data before you share it." % out)
        self.open_uri(os.path.dirname(out))

    def open_uri(self, path):
        try:
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(path).get_uri(), None)
        except GLib.Error as e:
            self.log("could not open %s: %s" % (path, e.message))

    def open_web(self, url):
        try:
            Gio.AppInfo.launch_default_for_uri(url, None)
        except GLib.Error as e:
            self.log("could not open %s: %s" % (url, e.message))

    def launch_inventor(self, prefix):
        subprocess.Popen(["bash", os.path.join(SCRIPTS, "launch-inventor.sh")], cwd=REPO,
                         env=dict(os.environ, INV_PREFIX=prefix),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)

    def on_close_request(self, *_):
        if not self.proc:
            return False
        dlg = Gtk.AlertDialog(message="The installer is still working",
                              detail="Stop it and close? Running the installer again continues where it stopped.",
                              buttons=["Keep running", "Stop and close"], cancel_button=0, default_button=0)

        def done(d, res):
            try:
                if d.choose_finish(res) == 1:
                    self.stop_process()
                    GLib.timeout_add(1500, lambda: (self.destroy(), False)[1])
            except GLib.Error:
                pass
        dlg.choose(self, None, done)
        return True


def main():
    if os.geteuid() == 0:
        sys.exit("run the installer as your normal user, not as root")
    Gtk.Window.set_default_icon_name("inventor-on-linux")  # X11; on Wayland the .desktop file named APP_ID
    app = Gtk.Application(application_id=APP_ID)
    app.connect("activate", lambda a: (a.get_active_window() or Installer(a)).present())
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
