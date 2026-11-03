# oleaut32: type library cache and typelib-marshaled proxies

**Problem:** Inventor's 3D PDF export (Anark `corewrapper.exe`, on native .NET
Framework 4.8 as a black box) took ~7 minutes under Wine. `corewrapper.exe`
reads the part from Inventor through Inventor's COM API; every new
typelib-marshaled proxy for an Inventor interface took ~1 s of CPU (421
proxies in one export). In Wine 11.20 `get_typeinfo_for_iid()`
(`dlls/oleaut32/oleaut.c`) loads the interface's type library, takes the
ITypeInfo and releases the library; the proxy built by `CreateProxyFromTypeInfo`
(`dlls/rpcrt4/ndr_typelib.c`) keeps no reference either, so the last reference
goes, `ITypeLib2_fnRelease` drops the library from `tlb_cache`, and the next
proxy parses `RxInventor.tlb` again. A diagnostic build that keeps the reference
(`patches/debug/oleaut32-typelib-ps-keep-diag.patch`) made the export take
15 s instead of ~7 min.

**What `measure.c` finds out on Windows** (own program, its own type library):

- A: after `Release` to 0, is the next `LoadTypeLib` as fast as with a
  reference held (a cache that outlives the last reference)?
- B: do a typelib-marshaled proxy and stub keep references to the ITypeLib /
  ITypeInfo while they exist?
- C: time per round "new object, marshal MTA -> STA, one call, release",
  without and with a reference to the library held by the program.

The answers decide where a fix belongs (oleaut32's cache, or rpcrt4 proxies/
stubs holding their ITypeInfo) and what the Wine test checks.

## Build and run

```bash
x86_64-w64-mingw32-gcc -O2 -o measure64.exe measure.c -lole32 -loleaut32 -luuid
i686-w64-mingw32-gcc   -O2 -o measure32.exe measure.c -lole32 -loleaut32 -luuid
```

Under Wine first (quick check that it works), then in the Windows 10 VM:
`run-measure.bat` writes `measure-result.txt` (text only comes back). The
program registers its type library for the current user and unregisters and
deletes it at the end.

## Results (2026-11-03)

Default arguments (3000 interfaces x 10 functions, 2.2 MB file, 20 rounds):

| | Windows 10 x64 | Windows 10 i686 | Wine 11.20 x64 | Wine 11.20 + diag patch |
|---|---|---|---|---|
| A first load | 5.21 ms | 2.75 ms | 20.68 ms | 20.34 ms |
| A load after Release to 0 | 2.51 ms (same pointer: yes) | 0.35 ms (no) | 20.16 ms (no) | 19.13 ms (no) |
| A load, reference held | 0.00 ms | 0.00 ms | 0.10 ms | 0.10 ms |
| B ITypeLib / ITypeInfo refs: before, proxy+stub alive, released | 2/1, 2/1, 2/1 | 2/1, 2/1, 2/1 | 2/1, 2/1, 2/1 | 2/1, 4/1, 4/1 (the leak) |
| C per round, no reference held | 8.82 ms | 1.51 ms | 48.14 ms | 2.19 ms |
| C per round, reference held | 0.55 ms | 0.71 ms | 2.33 ms | 2.23 ms |

Windows 10 x64 with 300 interfaces: A 6.80 / 0.38 (no) / 0.00 ms, B unchanged,
C 1.23 / 0.47 ms.

What it says:
- B: on Windows, too, typelib-marshaled proxies and stubs hold no reference to
  the ITypeLib or ITypeInfo - so making Wine's proxies hold one would differ
  from Windows.
- A/C: on Windows, too, a type library is dropped after its last Release
  (another pointer after reloading in two of three runs) and a round without a
  reference costs more. The difference is the load itself: Windows loads this
  library in 0.35-2.5 ms, Wine in ~20 ms, because Wine's LoadTypeLib parses
  every type info, function and parameter up front. For Inventor's
  RxInventor.tlb that is ~0.5 s per load, two loads (proxy and stub) per new
  object.
