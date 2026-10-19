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
    """INV_PREFIX, INV_DATA_DIR, ... as the scripts see them (config.env included)."""
    names = ["INV_PREFIX", "INV_DATA_DIR", "INV_DISTRO", "INV_YEAR"]
    script = 'source "$1/lib/common.sh" >/dev/null 2>&1; printf "%s\\n" ' + " ".join('"$%s"' % n for n in names)
    try:
        out = subprocess.run(["bash", "-c", script, "bash", SCRIPTS], capture_output=True,
                             text=True, timeout=30).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        out = []
    vals = dict(zip(names, out + [""] * len(names)))
    home = os.path.expanduser("~")
    vals["INV_YEAR"] = vals["INV_YEAR"] or "2026"
    vals["INV_PREFIX"] = vals["INV_PREFIX"] or os.path.join(home, ".wine-inventor" + vals["INV_YEAR"])
    vals["INV_DATA_DIR"] = vals["INV_DATA_DIR"] or os.path.join(home, "Inventor")
    return vals


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


def installed_inventor(settings):
    exe = os.path.join(settings["INV_PREFIX"], "drive_c", "Program Files", "Autodesk",
                       "Inventor " + settings["INV_YEAR"], "Bin", "Inventor.exe")
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
                  if os.path.isfile(os.path.join(d, ".unpacked")))


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
        self.set_default_size(820, 640)
        self.settings = project_settings()
        self.proc = None
        self.cancelled = False
        self.running_install = False
        self.last_args = None
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
        header.set_title_widget(label("Autodesk Inventor %s on Linux" % self.settings["INV_YEAR"],
                                      css="heading", wrap=False))
        self.set_titlebar(header)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, vexpand=True)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(self.stack)
        self.nav = Gtk.Box(spacing=8)
        margin(self.nav, 12)
        self.back_btn = Gtk.Button(label="Back")
        self.next_btn = Gtk.Button(label="Next")
        self.next_btn.add_css_class("suggested-action")
        spacer = Gtk.Box(hexpand=True)
        self.nav.append(self.back_btn)
        self.nav.append(spacer)
        self.nav.append(self.next_btn)
        outer.append(Gtk.Separator())
        outer.append(self.nav)
        self.set_child(outer)
        self.back_btn.connect("clicked", self.on_back)
        self.next_btn.connect("clicked", self.on_next)

        self.pages = ["welcome", "downloads", "options", "summary", "progress", "done"]
        self.stack.add_named(self.page_welcome(), "welcome")
        self.stack.add_named(self.page_downloads(), "downloads")
        self.stack.add_named(self.page_options(), "options")
        self.stack.add_named(self.page_summary(), "summary")
        self.stack.add_named(self.page_progress(), "progress")
        self.stack.add_named(self.page_done(), "done")
        self.show_page("welcome")
        self.connect("close-request", self.on_close_request)

    # ------------------------------------------------------------- navigation

    def show_page(self, name):
        self.stack.set_visible_child_name(name)
        self.back_btn.set_visible(name in ("downloads", "options", "summary"))
        self.next_btn.set_visible(name in ("welcome", "downloads", "options", "summary"))
        self.next_btn.set_label("Install" if name == "summary" else "Next")
        if name == "summary":
            self.fill_summary()
        if name == "welcome":
            self.next_btn.set_sensitive(self.checks_ok)
        elif name == "downloads":
            self.update_downloads_state()
        else:
            self.next_btn.set_sensitive(True)

    def on_back(self, *_):
        cur = self.stack.get_visible_child_name()
        self.show_page(self.pages[self.pages.index(cur) - 1])

    def on_next(self, *_):
        cur = self.stack.get_visible_child_name()
        if cur == "summary":
            self.start_install()
        else:
            self.show_page(self.pages[self.pages.index(cur) + 1])

    # ---------------------------------------------------------------- welcome

    def page_welcome(self):
        box = margin(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), 24)
        box.append(label(markup="<span size='x-large' weight='bold'>Install Autodesk Inventor %s</span>"
                         % self.settings["INV_YEAR"]))
        box.append(label("Inventor is installed from Autodesk's own download and runs under Wine - "
                         "no Windows, no virtual machine. You need your own Inventor license "
                         "(an education license works). This is an unofficial community project, "
                         "not made or supported by Autodesk."))

        grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        checks = system_checks(self.settings)
        self.checks_ok = all(s != "bad" for s, _, _ in checks)
        for row, (state, title, detail) in enumerate(checks):
            mark = {"ok": "✓", "warn": "!", "bad": "✗"}[state]
            grid.attach(label(mark, css="state-" + state, wrap=False), 0, row, 1, 1)
            grid.attach(label(title, wrap=False), 1, row, 1, 1)
            grid.attach(label(detail, selectable=True), 2, row, 1, 1)
        frame = Gtk.Frame(label="Your system")
        frame.set_child(margin(grid, 12))
        box.append(frame)
        if not self.checks_ok:
            box.append(label(markup="<b>This system can't run the installation</b> - see the ✗ above."))

        if installed_inventor(self.settings):
            inst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            inst.append(label(markup="<b>Inventor is already installed</b> in %s."
                              % esc(self.settings["INV_PREFIX"])))
            inst.append(label("Next repairs or completes the installation (finished parts are skipped). "
                              "Or start it, or update this project and its Wine:"))
            row = Gtk.Box(spacing=8)
            start = Gtk.Button(label="Start Inventor")
            start.connect("clicked", lambda *_: self.launch_inventor())
            update = Gtk.Button(label="Update project and Wine")
            update.connect("clicked", lambda *_: self.start_update())
            row.append(start)
            row.append(update)
            inst.append(row)
            frame2 = Gtk.Frame()
            frame2.set_child(margin(inst, 12))
            box.append(frame2)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(box)
        return scroll

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
        for p, kind in uniq:
            check = Gtk.CheckButton()
            check.set_active(old.get(p, kind != "unpacked earlier" or not any(k == "product" for _, k in uniq)))
            check.connect("toggled", lambda *_: self.update_downloads_state())
            line = Gtk.Box(spacing=10)
            margin(line, 6)
            line.append(check)
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            text.append(label(os.path.basename(p.rstrip("/")) or p, wrap=False))
            text.append(label("%s · %s · %s" % (kind, human_size(p), os.path.dirname(p)), css="dim-label caption"))
            line.append(text)
            self.dl_list.append(line)
            self.dl_rows.append((p, kind, check))
        if not uniq:
            self.dl_list.append(margin(label("Nothing found in Downloads - use Add files… or Add folder…"), 12))
        self.update_downloads_state()

    def selected_downloads(self):
        return [p for p, _, c in self.dl_rows if c.get_active()]

    def update_downloads_state(self):
        sel = self.selected_downloads()
        installed = installed_inventor(self.settings)
        ok = bool(sel) or installed
        if self.stack.get_visible_child_name() == "downloads":
            self.next_btn.set_sensitive(ok)
        if sel:
            self.dl_hint.set_text("%d selected." % len(sel))
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
        box.append(label("Inventor (Wine prefix): %s\nYour files (drive D: in Inventor): %s\n"
                         "To use other folders set INV_PREFIX / INV_DATA_DIR in config.env "
                         "(see config.env.example) before installing."
                         % (self.settings["INV_PREFIX"], self.settings["INV_DATA_DIR"]), selectable=True))
        return box

    # ---------------------------------------------------------------- summary

    def page_summary(self):
        box = margin(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), 24)
        box.append(label(markup="<span size='large' weight='bold'>Ready to install</span>"))
        self.summary = label("", selectable=True)
        box.append(self.summary)
        return box

    def fill_summary(self):
        distro = self.settings.get("INV_DISTRO", "")
        pk = {"arch": "pacman (updates the system together with the new packages, as Arch requires)",
              "debian": "apt", "fedora": "dnf"}.get(distro, "your package manager")
        sel = self.selected_downloads()
        lines = [
            "<b>What happens</b>",
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
        self.summary.set_markup("\n".join(lines))

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
        self.log(line)

    def tick(self):
        if not self.proc:
            return False
        secs = int(time.time() - self.started)
        self.elapsed.set_text("Elapsed %d:%02d:%02d" % (secs // 3600, secs // 60 % 60, secs % 60))
        if not self.sub_known:
            self.sub.pulse()
        return True

    def run_command(self, args, title, install=False):
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
        if install:
            self.set_phase(1, PHASES[0][0])
        env = dict(os.environ)
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
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
        except OSError:
            pass
        # Wine programs started by the installer keep running in the background
        subprocess.Popen(["bash", "-c", 'source "$1/lib/common.sh" >/dev/null 2>&1; select_wine >/dev/null 2>&1; '
                          'wineserver -k 2>/dev/null; true', "bash", SCRIPTS],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def start_install(self):
        args = ["bash", os.path.join(SCRIPTS, "install.sh")]
        if not self.sw_content.get_active():
            args.append("--no-content")
        if not self.sw_desktop.get_active():
            args.append("--no-desktop")
        sel = self.selected_downloads()
        if not sel:
            sel = cached_media()
        args += sel
        self.last_args = args
        self.run_command(args, "Installing Inventor", install=True)

    def start_update(self):
        script = ('set -e; cd "$1"; echo "Updating this project (git pull)..."; git pull --ff-only; '
                  'echo "Wine..."; bash scripts/get-wine.sh; '
                  'echo "App launcher and file types..."; bash scripts/install-desktop-integration.sh')
        self.last_args = ["bash", "-c", script, "bash", REPO]
        self.run_command(self.last_args, "Updating", install=False)

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
        self.cancel_btn.set_sensitive(False)
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

        if success:
            self.done_title.set_text("Done")
            if self.last_args and "install.sh" in " ".join(self.last_args):
                self.done_text.set_text("Inventor is installed. The first start asks you to sign in with your "
                                        "Autodesk account in your web browser.\n\nYour files go to %s "
                                        "(drive D: in Inventor)." % self.settings["INV_DATA_DIR"])
            else:
                self.done_text.set_text("Finished.")
            button("Start Inventor", self.launch_inventor, suggested=True)
            button("Open my Inventor folder", lambda: self.open_uri(self.settings["INV_DATA_DIR"]))
        else:
            self.done_title.set_text("Stopped" if self.cancelled else "The installation did not finish")
            msg = reason if not self.cancelled else "You stopped it."
            self.done_text.set_text(msg + "\n\nRunning it again continues where it stopped. If it fails again, "
                                    "open an issue on GitHub with the report (button below).")
            button("Try again", lambda: self.run_command(self.last_args, self.run_title,
                                                         install="install.sh" in " ".join(self.last_args)),
                   suggested=True)
            if self.logfile:
                button("Open the log", lambda: self.open_uri(self.logfile))
            button("Create a report", self.make_report)
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

    def launch_inventor(self):
        subprocess.Popen(["bash", os.path.join(SCRIPTS, "launch-inventor.sh")], cwd=REPO,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)

    def on_close_request(self, *_):
        if not self.proc:
            return False
        dlg = Gtk.AlertDialog(message="The installation is still running",
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
    app = Gtk.Application(application_id=APP_ID)
    app.connect("activate", lambda a: (a.get_active_window() or Installer(a)).present())
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
