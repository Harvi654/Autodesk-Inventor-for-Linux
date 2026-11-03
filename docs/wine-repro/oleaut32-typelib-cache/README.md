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

## Results

(to be filled in: Windows 10 x64 / i686, Wine 11.20 with and without the
diagnostic patch)
