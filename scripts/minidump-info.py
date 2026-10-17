#!/usr/bin/env python3
"""Print the crash reason of Windows minidumps (.dmp), e.g. WebView2/Crashpad reports.

Only reads the dump header, the exception record, the module list and the
Crashpad "ptype"/"reason" annotations. No memory contents are printed, so the
output is safe to share (dumps themselves may contain tokens - do not share them).

Usage: python3 -I scripts/minidump-info.py FILE.dmp [...]
"""

import struct
import sys

EXC_NAMES = {
    0xC0000005: "ACCESS_VIOLATION",
    0xC0000409: "STACK_BUFFER_OVERRUN / fast fail",
    0xC000001D: "ILLEGAL_INSTRUCTION",
    0xC0000374: "HEAP_CORRUPTION",
    0xC00000FD: "STACK_OVERFLOW",
    0x80000003: "BREAKPOINT (CHECK/NOTREACHED in Chromium)",
    0xE0000008: "OUT_OF_MEMORY (Chromium)",
    0x4000001F: "WX86_BREAKPOINT",
    0xC0000420: "ASSERTION_FAILURE",
}
FAST_FAIL = {2: "STACK_COOKIE_CHECK", 3: "CORRUPT_LIST_ENTRY", 4: "INCORRECT_STACK",
             5: "INVALID_ARG", 7: "FATAL_APP_EXIT", 10: "INVALID_SET_OF_CONTEXT", 13: "GUARD_ICALL_CHECK_FAILURE"}


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def u64(b, o):
    return struct.unpack_from("<Q", b, o)[0]


def mdstring(b, rva):
    n = u32(b, rva)
    return b[rva + 4: rva + 4 + n].decode("utf-16-le", "replace")


# Chromium crash keys worth showing. "switch-N" = command-line switches,
# "LOG_FATAL" = the message of a failed CHECK/NOTREACHED/LOG(FATAL).
# Keys that could identify the user (URLs, user names) are not printed.
SHOW_KEYS = {"ptype", "num-switches", "gpu-gl-renderer", "gpu-gl-vendor", "gpu-vsver", "gpu-psver",
             "gpu_gl_context_is_virtual", "gpu-generation-intel", "egl-display-type", "osarch", "ver", "prod"}


def utf8(b, rva):
    n = u32(b, rva)
    return b[rva + 4: rva + 4 + n].decode("utf-8", "replace").rstrip("\0")


def crashpad_annotations(b, streams):
    """Yield (key, value) from Crashpad's info stream: simple annotations of the
    process and of every module, and the module annotation objects (crash keys)."""
    if 0x43500001 not in streams:
        return
    _, rva = streams[0x43500001]

    def simple(loc_rva):
        if not loc_rva:
            return
        for i in range(u32(b, loc_rva)):
            k, v = struct.unpack_from("<II", b, loc_rva + 4 + 8 * i)
            yield utf8(b, k), utf8(b, v)

    yield from simple(u32(b, rva + 40))
    mods = u32(b, rva + 48)
    if not mods:
        return
    for i in range(u32(b, mods)):
        _, _, mrva = struct.unpack_from("<III", b, mods + 4 + 12 * i)
        yield from simple(u32(b, mrva + 16))
        objs = u32(b, mrva + 24)
        if not objs:
            continue
        for j in range(u32(b, objs)):
            name, typ, _, val = struct.unpack_from("<IHHI", b, objs + 4 + 12 * j)
            if typ == 1:  # string
                n = u32(b, val)
                yield utf8(b, name), b[val + 4: val + 4 + n].decode("utf-8", "replace").rstrip("\0")


def info(path):
    b = open(path, "rb").read()
    print(f"== {path.split('/')[-1]}")
    if b[:4] != b"MDMP":
        print("   not a minidump")
        return
    nstreams, dirrva = u32(b, 8), u32(b, 12)
    streams = {}
    for i in range(nstreams):
        t, size, rva = struct.unpack_from("<III", b, dirrva + 12 * i)
        streams.setdefault(t, (size, rva))

    modules = []
    if 4 in streams:
        _, rva = streams[4]
        for i in range(u32(b, rva)):
            m = rva + 4 + 108 * i
            base, size = u64(b, m), u32(b, m + 8)
            modules.append((base, size, mdstring(b, u32(b, m + 20)).split("\\")[-1]))

    def where(addr):
        for base, size, name in modules:
            if base <= addr < base + size:
                return f"{name}+0x{addr - base:x}"
        return "?"

    for k, v in crashpad_annotations(b, streams):
        if k in SHOW_KEYS or k.startswith("switch-") or "LOG" in k or "fatal" in k.lower():
            print(f"   {k}: {v[:300]}")

    if 6 not in streams:
        print("   no exception stream (dump taken without a crash, e.g. a hang report)")
        return
    _, rva = streams[6]
    code, addr, nparam = u32(b, rva + 8), u64(b, rva + 24), u32(b, rva + 32)
    params = [u64(b, rva + 40 + 8 * k) for k in range(min(nparam, 15))]
    name = EXC_NAMES.get(code, "")
    if code == 0xC0000409 and params:
        name += f" ({FAST_FAIL.get(params[0], params[0])})"
    print(f"   exception 0x{code:08X} {name}")
    print(f"   at 0x{addr:x} = {where(addr)}")
    if code == 0xC0000005 and len(params) >= 2:
        print(f"   {'write' if params[0] == 1 else 'exec' if params[0] == 8 else 'read'} of 0x{params[1]:x}")


for p in sys.argv[1:]:
    try:
        info(p)
    except Exception as e:  # keep going on a truncated/odd dump
        print(f"   could not parse: {e}")
