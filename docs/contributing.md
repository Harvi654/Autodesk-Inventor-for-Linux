# Contributing to Inventor on Linux

This document is for developers who want to improve Wine compatibility for Autodesk Inventor. It assumes familiarity with Wine internals, COM, and x86-64 assembly.

---

## Table of Contents

- [Development Environment](#development-environment)
- [Debugging Techniques](#debugging-techniques)
- [Open Problem: OGS Protein Pipeline](#open-problem-ogs-protein-pipeline)
- [Open Problem: iLogic COM Interop](#open-problem-ilogic-com-interop)
- [Upstreaming to Wine](#upstreaming-to-wine)
- [Project Structure](#project-structure)
- [Before Submitting a PR](#before-submitting-a-pr)

---

## Development Environment

You need:

- Wine 11.4 **source tree** — for patching and `winedbg`
- `x86_64-w64-mingw32-objdump`, `radare2`, or Ghidra — for static analysis of Inventor DLLs
- `winedbg` — Wine's built-in debugger (ships with Wine)
- Standard build tools: `gcc`, `make`, `flex`, `bison`

```bash
# Get the matching Wine source
curl -LO https://dl.winehq.org/wine/source/11.x/wine-11.4.tar.xz
tar xf wine-11.4.tar.xz && cd wine-11.4
./configure --enable-win64 --without-x --without-freetype
```

A minimal configure (no X, no freetype) is sufficient for building individual DLLs like `wbemprox`.

---

## Debugging Techniques

### COM call tracing

The most valuable trace channel for Inventor issues:

```bash
WINEPREFIX=~/.wine-inventor2026 \
WINEDEBUG=+ole,+rpc,err+all \
wine "C:\\Program Files\\Autodesk\\Inventor 2026\\Bin\\Inventor.exe" \
    2>&1 | tee /tmp/com-trace.log
```

Look for `E_FAIL`, `E_NOINTERFACE`, or patterns like `returning NULL` near the crash timestamp.

### winedbg breakpoints

```bash
WINEPREFIX=~/.wine-inventor2026 winedbg --gdb \
    wine "C:\\Program Files\\Autodesk\\Inventor 2026\\Bin\\Inventor.exe"
```

Then from the GDB prompt:

```gdb
# Find OGSFactory base address
info sharedlibrary OGSFactory

# Break at the COM call that returns NULL (substitute actual base)
# RVA 0x57A40 inside OGSFactory.dll
break *(0x<base> + 0x57A40)

run

# After hitting the breakpoint:
info registers     # inspect arguments
x/2gx $rsp+0x68   # inspect [rsp+0x70] (the ppObject pointer)
stepi              # single-step through the COM call
```

To inspect a COM vtable slot:

```gdb
# rcx = the interface pointer; slot 4 = IEnumWbemClassObject::Next
x/8gx $rcx         # print vtable pointer
x/gx (void**)$rcx  # dereference to get vtable address
```

### Module load trace

Identifies crash timing relative to DLL load order:

```bash
WINEPREFIX=~/.wine-inventor2026 \
WINEDEBUG=+loaddll,err+all \
wine Inventor.exe 2>&1 | grep -E "(Loaded|ERR|fixme)"
```

### WMI query trace

```bash
WINEPREFIX=~/.wine-inventor2026 \
WINEDEBUG=+wbemprox,err+all \
wine Inventor.exe 2>&1 | grep -i wbem
```

### Disassembling OGSFactory.dll

The pre-patch original is at `$WINEPREFIX/drive_c/.../Bin/OGSFactory.dll.original`.

```bash
# Disassemble the relevant function (RVA 0x57968 to ~0x57B00)
objdump -d --start-address=0x57968 --stop-address=0x57B00 \
    --adjust-vma=0x10000000 OGSFactory.dll.original

# Or with radare2:
r2 OGSFactory.dll.original
[0x00401000]> s 0x10057968
[0x10057968]> pd 200
```

The base address in the PE header is `0x10000000` for OGSFactory.dll. File offset = RVA (no base added — PE sections are mapped directly).

---

## Open Problem: OGS Protein Pipeline

This is the highest-priority open issue. Fixing it unblocks correct material brightness and Realistic Visual Style.

### What We Know

Function `OGSFactory.dll!fn@RVA:0x57968` does approximately:

```c
IWbemServices *svc = /* ... acquired earlier ... */;
IEnumWbemClassObject *enumerator = NULL;
svc->CreateInstanceEnum(L"Win32_TimeZone", flags, NULL, &enumerator);  // vtable[18]

IWbemClassObject *obj = NULL;
ULONG returned = 0;
enumerator->Next(2000, 1, &obj, &returned);  // vtable[4]
// obj is NULL here under Wine — crash follows
obj->Get(L"Bias", 0, &variant, NULL, NULL);  // ACCESS VIOLATION
```

The `Win32_TimeZone` entry now exists in wbemprox (our patch), and `CreateInstanceEnum` succeeds. But `Next()` returns `S_OK` with `obj = NULL` and `returned = 0`.

### Investigation Steps

**Step 1: Confirm the failure point**

Set a breakpoint at RVA `0x57A40` (the `Next()` call site). After the call, inspect:
- `rax` — return value (should be `S_OK = 0`, but may be `S_FALSE = 1`)
- `[rsp+0x70]` — the `ppObject` output (should be non-NULL)
- `[rsp+0x68]` — the `puReturned` output (should be `1`)

If `rax = 1` (`S_FALSE`), Wine is returning "no more items" even though one exists. That's a bug in our `fill_timezone()` or in `wbemprox`'s enumeration logic.

**Step 2: Trace through wbemprox**

Add `WINEDEBUG=+wbemprox` and look for the `Win32_TimeZone` query. The fill function `fill_timezone()` calls `match_row()` and increments `table->num_rows` — verify this path executes.

Alternatively, build wbemprox with `TRACE` statements and check the Wine debug log.

**Step 3: Check the IEnumWbemClassObject implementation**

In Wine source: `dlls/wbemprox/query.c` — the `IEnumWbemClassObject` implementation. The `enum_wbem_object_next()` function returns rows from the table. If `table->num_rows == 0` at query time (fill ran but match failed), `Next()` correctly returns `S_FALSE`.

Check: is `fill_timezone()` being called? Is `match_row()` returning true? Is `table->num_rows` being incremented?

**Step 4: If wbemprox is correct, look for a second COM call**

There may be a second `IEnumWbemClassObject::Next()` call *on the object returned by the first call* (i.e., querying a property that is itself a WMI object). In that case, a different WMI class needs implementing.

---

## Open Problem: iLogic COM Interop

**Enable the addin:**

```bash
mv "$WINEPREFIX/drive_c/Program Files/Autodesk/Inventor 2026/Bin/Addins/disabled/autodesk.ilogic.inventor.addin" \
   "$WINEPREFIX/drive_c/Program Files/Autodesk/Inventor 2026/Bin/Addins/"
```

**Capture the failure:**

```bash
WINEPREFIX=~/.wine-inventor2026 \
WINEDEBUG=+ole,+typelib,err+all \
wine Inventor.exe 2>&1 | grep -A5 "E_FAIL\|ilogic\|iLogic" > /tmp/ilogic.log
```

The failure is `E_FAIL` on `DesignProjectManager.get_ActiveDesignProject`. This is a dual-interface COM call from .NET via `ClrAddinLoader`. The most likely causes:

1. `IDispatch::Invoke` failure — Wine's typelib marshalling doesn't handle the dispatch ID correctly
2. The `DesignProjectManager` object isn't registered in Wine's COM catalog — add it to `autodesk-full.reg`
3. A .NET 8 / wine-mono interop issue at the RCW (Runtime Callable Wrapper) boundary

---

## Upstreaming to Wine

### Win32_TimeZone (wbemprox)

This patch is ready for upstream submission. Steps:

1. Fork Wine at https://gitlab.winehq.org/wine/wine
2. The patch is at `patches/wbemprox-timezone.patch` — apply it to a clean Wine tree
3. Add a conformance test in `dlls/wbemprox/tests/` querying `Win32_TimeZone`
4. Format with `git format-patch --subject-prefix="PATCH"` following Wine's commit style
5. Send to wine-devel@winehq.org

Wine commit message format:
```
wbemprox: Add Win32_TimeZone class implementation.

The Win32_TimeZone WMI class returns timezone information via
GetTimeZoneInformation(). This is queried by Autodesk Inventor
and other applications during graphics subsystem initialization.
```

### OGSFactory.dll Patch

The binary patch cannot be upstreamed — it modifies a proprietary DLL. The correct upstream contribution is identifying and fixing the Wine bug that causes `IEnumWbemClassObject::Next()` to return NULL (see above).

---

## Project Structure

```
scripts/
  launch-inventor.sh       # Start services in order, then launch Inventor
  rebuild-prefix.sh        # Full prefix rebuild from Windows source (28 steps)
  adskidmgr-callback.sh    # xdg-mime handler: deliver OAuth2 code to running IdMgr
  phase0-setup.sh          # Install system prerequisites (pacman packages)
patches/
  wbemprox-timezone.patch  # Adds Win32_TimeZone to Wine's wbemprox
registry/
  autodesk-full.reg        # Full Autodesk registry export from Windows
notes/
  disabled-addins.md       # Which addins are disabled and why
docs/
  contributing.md          # This file
logs/                      # Wine debug logs, gitignored
```

---

## Before Submitting a PR

- **Test with a clean prefix.** Run `rebuild-prefix.sh` from scratch. Don't test on a prefix that has manual modifications.
- **Wine patches:** verify they build cleanly against Wine 11.4 source with `make -C dlls/<affected>`.
- **rebuild-prefix.sh changes:** test the full 28-step run. The script starts with `rm -rf "$WINEPREFIX"`.
- **Addin status changes:** update `notes/disabled-addins.md`.
- **Significant compatibility improvement:** add a session history entry to the README with the date and a one-paragraph summary of what changed.
