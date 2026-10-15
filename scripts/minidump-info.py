#!/usr/bin/env python3
"""Print the crash reason of Windows minidumps (.dmp), e.g. WebView2/Crashpad reports.

Only reads the dump header, the exception record, the module list and the
Crashpad "ptype"/"reason" annotations. No memory contents are printed, so the
output is safe to share (dumps themselves may contain tokens - do not share them).

Usage: python3 -I scripts/minidump-info.py FILE.dmp [...]
"""
import re
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

    # Crashpad annotations are stored as plain strings; ptype = process type.
    text = re.findall(rb"[\x20-\x7e]{3,200}", b)
    for i, s in enumerate(text[:-1]):
        if s in (b"ptype", b"reason", b"crash_reason", b"exit_reason"):
            print(f"   {s.decode()}: {text[i + 1].decode('ascii', 'replace')[:120]}")

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
