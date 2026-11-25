#!/usr/bin/env python3
"""File list of an install image, and a comparison of two such lists.

  image-manifest.py make DIR [-o OUT]     SHA-256, size, relative path of
                                          every file, sorted by path
  image-manifest.py compare A B [--details FILE]

The format is the same as tools/image-manifest.ps1 writes on Windows
("<sha256>\t<size>\t<relative/path>"), so an image made by Autodesk's
Create Installer under Wine can be compared with one made on Windows from
the same download. Paths are compared case-sensitively first; a path that
differs only in case is reported as such (Windows does not care, a Linux
file system does).

The lists hold only paths inside the image, sizes and hashes; they stay
local all the same (never committed).
"""
import argparse
import hashlib
import os
import sys


def make(root, out):
    root = os.path.abspath(root)
    rows, total = [], 0
    for d, dirs, files in os.walk(root):
        dirs.sort()
        for name in files:
            p = os.path.join(d, name)
            if os.path.islink(p) or not os.path.isfile(p):
                continue
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            size = os.path.getsize(p)
            total += size
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            rows.append((rel, "%s\t%d\t%s" % (h.hexdigest(), size, rel)))
            print("\r%d files" % len(rows), end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)
    rows.sort(key=lambda r: r[0])
    text = "".join(line + "\n" for _, line in rows)
    if out:
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("%d files, %.1f GB -> %s" % (len(rows), total / 2**30, out))
    else:
        sys.stdout.write(text)


def load(path):
    entries = {}
    with open(path, encoding="utf-8-sig") as f:      # tolerate a BOM
        for n, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if not line:
                continue
            parts = line.split("\t", 2)
            if len(parts) != 3:
                sys.exit("%s:%d: not '<sha256>\\t<size>\\t<path>'" % (path, n))
            entries[parts[2]] = (parts[0].lower(), int(parts[1]))
    return entries


def top(path):
    return path.split("/", 1)[0] if "/" in path else "(root)"


def compare(a_path, b_path, details):
    a, b = load(a_path), load(b_path)
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    # Same file, path differing only in case.
    lower_b = {}
    for p in only_b:
        lower_b.setdefault(p.lower(), p)
    case_only = []
    for p in list(only_a):
        q = lower_b.get(p.lower())
        if q:
            case_only.append((p, q))
            only_a.remove(p)
            only_b.remove(q)
    common = sorted(set(a) & set(b)) + [p for p, _ in case_only]
    same, differ = 0, []
    for p in common:
        q = dict(case_only).get(p, p)
        if a[p] == b[q]:
            same += 1
        else:
            differ.append((p, a[p], b[q]))

    size_a = sum(s for _, s in a.values())
    size_b = sum(s for _, s in b.values())
    print("A: %s - %d files, %.2f GB" % (a_path, len(a), size_a / 2**30))
    print("B: %s - %d files, %.2f GB" % (b_path, len(b), size_b / 2**30))
    print("identical: %d" % same)
    print("different content: %d" % len(differ))
    print("only in A: %d" % len(only_a))
    print("only in B: %d" % len(only_b))
    print("same file, path differs only in case: %d" % len(case_only))

    def by_top(paths):
        counts = {}
        for p in paths:
            counts[top(p)] = counts.get(top(p), 0) + 1
        return ", ".join("%s %d" % kv for kv in sorted(counts.items()))

    if differ:
        print("\ndifferent content, by top folder: " + by_top(p for p, _, _ in differ))
        for p, x, y in differ[:20]:
            print("  %s  (size %d / %d)" % (p, x[1], y[1]))
    if only_a:
        print("\nonly in A, by top folder: " + by_top(only_a))
        for p in only_a[:20]:
            print("  " + p)
    if only_b:
        print("\nonly in B, by top folder: " + by_top(only_b))
        for p in only_b[:20]:
            print("  " + p)
    if case_only:
        print("\npath differs only in case:")
        for p, q in case_only[:20]:
            print("  %s  /  %s" % (p, q))
    if details:
        with open(details, "w", encoding="utf-8") as f:
            f.write("# Image comparison\n\nA: %s\nB: %s\n" % (a_path, b_path))
            f.write("\n## Different content\n\n")
            for p, x, y in differ:
                f.write("- %s (A %s %d, B %s %d)\n" % (p, x[0][:12], x[1], y[0][:12], y[1]))
            f.write("\n## Only in A\n\n" + "".join("- %s\n" % p for p in only_a))
            f.write("\n## Only in B\n\n" + "".join("- %s\n" % p for p in only_b))
            f.write("\n## Path differs only in case\n\n"
                    + "".join("- %s / %s\n" % pq for pq in case_only))
        print("\nfull lists: %s" % details)
    return 0 if not (differ or only_a or only_b) else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make", help="list the files of an image")
    m.add_argument("dir")
    m.add_argument("-o", "--out")
    c = sub.add_parser("compare", help="compare two lists")
    c.add_argument("a")
    c.add_argument("b")
    c.add_argument("--details", metavar="FILE", help="write the full lists here")
    args = ap.parse_args()
    if args.cmd == "make":
        make(args.dir, args.out)
        return 0
    return compare(args.a, args.b, args.details)


if __name__ == "__main__":
    sys.exit(main())
