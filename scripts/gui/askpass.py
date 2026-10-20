#!/usr/bin/env -S python3 -I
"""Password prompt for sudo -A (SUDO_ASKPASS) used by the graphical installer.

sudo starts this program with its prompt as the argument and reads the
password from its standard output. Nothing is stored or logged; exit code 1
means cancelled.
"""
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk  # noqa: E402

PROMPT = sys.argv[1] if len(sys.argv) > 1 else "Password:"
result = {"code": 1}


def activate(app):
    win = Gtk.ApplicationWindow(application=app, title="Autodesk Inventor installer - password")
    win.set_default_size(420, -1)
    win.set_resizable(False)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    for side in ("top", "bottom", "start", "end"):
        getattr(box, "set_margin_" + side)(18)
    win.set_child(box)

    title = Gtk.Label(xalign=0, wrap=True)
    title.set_markup("<b>Administrator rights are needed</b>")
    box.append(title)
    text = Gtk.Label(xalign=0, wrap=True,
                     label="The installer installs packages of your distribution (sudo). "
                           "The password goes straight to sudo and is not stored.")
    box.append(text)
    box.append(Gtk.Label(xalign=0, label=PROMPT.strip()))

    entry = Gtk.PasswordEntry(show_peek_icon=True)
    box.append(entry)

    buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
    cancel = Gtk.Button(label="Cancel")
    ok = Gtk.Button(label="OK")
    ok.add_css_class("suggested-action")
    buttons.append(cancel)
    buttons.append(ok)
    box.append(buttons)

    def accept(*_):
        sys.stdout.write(entry.get_text() + "\n")
        sys.stdout.flush()
        result["code"] = 0
        app.quit()

    ok.connect("clicked", accept)
    entry.connect("activate", accept)
    cancel.connect("clicked", lambda *_: app.quit())
    win.connect("close-request", lambda *_: (app.quit(), False)[1])
    win.present()
    entry.grab_focus()


app = Gtk.Application(application_id="io.github.harvi654.InventorInstaller.AskPass",
                      flags=Gio.ApplicationFlags.NON_UNIQUE)
app.connect("activate", activate)
app.run([sys.argv[0]])
sys.exit(result["code"])
