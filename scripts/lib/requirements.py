#!/usr/bin/env python3
"""Disk space and memory checks of the interactive front ends (install.sh,
check-system.sh, the graphical installer). The numbers are in
requirements.env next to this file.

Disk: what goes where - the prefix (its parent folder, --prefix or the
GUI's choice), the unpacked downloads (XDG_CACHE_HOME), winum
(XDG_DATA_HOME) and the small downloads (the project's downloads/) - is
added up per filesystem (st_dev) and compared with that filesystem's free
space, plus REQ_MARGIN.

Memory: MemTotal of /proc/meminfo (INV_MEMINFO: another file, for tests).
Only a warning, never a stop. Not used by what the Nix build runs
(install-from-image.py, finish-install.sh).

    requirements.py disk --prefix P [--cache C] [--wine-dir W] [--downloads D]
                         [--no-content] [--no-media] [--no-wine] [--repair]
        one line per filesystem: ok|short<TAB>text; exit code 1 if short
    requirements.py mem
        ok|warn|low<TAB>text
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(HERE, "requirements.env")
GB = 1024 ** 3     # as du -h / df -h count; the measurements were made with du


def load(path=ENV_FILE):
    """NAME=value lines of requirements.env -> {NAME: float}."""
    req = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            req[k.strip()] = float(v.strip())
    return req


def default_paths(prefix):
    """Where an installation puts things, as common.sh and install.sh do."""
    home = os.path.expanduser("~")
    cache = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(home, ".cache"),
                         "inventor-on-linux", "media")
    wine = os.environ.get("INV_WINE_HOME") or os.path.join(
        os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share"), "inventor-on-linux")
    downloads = os.environ.get("DOWNLOAD_DIR") or os.path.join(os.path.dirname(os.path.dirname(HERE)), "downloads")
    return {"prefix": prefix, "cache": cache, "wine": wine, "downloads": downloads}


def winum_present(wine_dir=None):
    """True when the winum release of wine/version.env is unpacked already."""
    vals = {}
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(HERE)), "wine", "version.env")) as f:
            for line in f:
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    vals[k] = v
    except OSError:
        return False
    if "WINUM_VERSION" not in vals or "WINUM_BUILD" not in vals:
        return False
    wine_dir = wine_dir or default_paths("")["wine"]
    return os.path.isdir(os.path.join(wine_dir, "winum-%s-%s-x86_64" % (vals["WINUM_VERSION"], vals["WINUM_BUILD"])))


def existing(path):
    """The path itself or its nearest existing parent (a prefix or cache
    folder that is not made yet lands where its parent is)."""
    p = os.path.abspath(os.path.expanduser(path))
    while not os.path.exists(p):
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return p


def mount_point(path, stat=os.stat):
    """The top folder of the filesystem PATH is on (for the message)."""
    p = existing(path)
    dev = stat(p).st_dev
    while True:
        parent = os.path.dirname(p)
        if parent == p or stat(parent).st_dev != dev:
            return p
        p = parent


LABELS = {"prefix": "prefix", "cache": "unpacked downloads", "wine": "Wine", "downloads": "small downloads"}


def needs(req, content=True, media=True, wine=True, repair=False):
    """GB per kind of place, before the margin."""
    if repair:
        return {"prefix": req["REQ_REPAIR_GB"]}
    n = {"prefix": req["REQ_PREFIX_GB"] if content else req["REQ_PREFIX_NO_CONTENT_GB"],
         "downloads": req["REQ_DOWNLOADS_GB"]}
    if media:
        n["cache"] = req["REQ_MEDIA_GB"]
    if wine:
        n["wine"] = req["REQ_WINE_GB"]
    return n


def disk_plan(paths, req, content=True, media=True, wine=True, repair=False,
              stat=os.stat, statvfs=os.statvfs):
    """[{mount, kinds, needed, free, ok}] - one per filesystem, in GB."""
    fs = {}
    for kind, gb in needs(req, content, media, wine, repair).items():
        p = existing(paths[kind])
        dev = stat(p).st_dev
        e = fs.setdefault(dev, {"path": p, "kinds": [], "raw": 0.0})
        e["kinds"].append(kind)
        e["raw"] += gb
    plan = []
    for dev, e in fs.items():
        st = statvfs(e["path"])
        free = st.f_bavail * st.f_frsize / GB
        needed = e["raw"] * (1 + req["REQ_MARGIN"])
        plan.append({"mount": mount_point(e["path"], stat), "kinds": e["kinds"], "needed": needed,
                     "free": free, "ok": free >= needed})
    order = ["prefix", "cache", "wine", "downloads"]
    for d in plan:
        d["kinds"].sort(key=order.index)
    return sorted(plan, key=lambda d: order.index(d["kinds"][0]))


def describe(d):
    """'prefix disk /mnt/nvme: 22 GB needed, 15 GB free'"""
    what = " + ".join(LABELS[k] for k in d["kinds"])
    return "%s disk %s: %.0f GB needed, %.0f GB free" % (what, d["mount"], d["needed"], d["free"])


def mem_total_gib(path=None):
    """MemTotal in GiB; None when it cannot be read."""
    path = path or os.environ.get("INV_MEMINFO") or "/proc/meminfo"
    try:
        with open(path) as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1024 / 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def mem_check(req=None, path=None):
    """(level, text): level 'ok', 'warn' (below 16 GB) or 'low' (about 8 GB or less)."""
    req = req or load()
    g = mem_total_gib(path)
    if g is None:
        return "ok", "memory: unknown (no MemTotal in /proc/meminfo)"
    shown = "%.1f GiB" % g
    if g < req["REQ_RAM_LOW_GIB"]:
        return "low", ("memory: %s - far below Autodesk's minimum of 16 GB; Inventor may not even start "
                       "properly, and it is not usable for work" % shown)
    if g < req["REQ_RAM_GIB"]:
        return "warn", ("memory: %s - 16 GB or more recommended; with 8 GB Inventor starts but is not "
                        "usable for work" % shown)
    return "ok", "memory: %s" % shown


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("disk")
    d.add_argument("--prefix", required=True)
    d.add_argument("--cache")
    d.add_argument("--wine-dir")
    d.add_argument("--downloads")
    d.add_argument("--no-content", action="store_true")
    d.add_argument("--no-media", action="store_true")
    d.add_argument("--no-wine", action="store_true")
    d.add_argument("--repair", action="store_true")
    sub.add_parser("mem")
    a = ap.parse_args(argv)
    req = load()
    if a.cmd == "mem":
        level, text = mem_check(req)
        print("%s\t%s" % (level, text))
        return 0
    paths = default_paths(a.prefix)
    for k, v in (("cache", a.cache), ("wine", a.wine_dir), ("downloads", a.downloads)):
        if v:
            paths[k] = v
    plan = disk_plan(paths, req, content=not a.no_content, media=not a.no_media, wine=not a.no_wine,
                     repair=a.repair)
    for e in plan:
        print("%s\t%s" % ("ok" if e["ok"] else "short", describe(e)))
    return 0 if all(e["ok"] for e in plan) else 1


if __name__ == "__main__":
    sys.exit(main())
