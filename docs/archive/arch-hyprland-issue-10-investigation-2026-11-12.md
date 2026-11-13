# Issue #10 investigation notes (2026-11-10 to 2026-11-12)

Moved here unchanged from `docs/arch-hyprland.md` when its issue #10
section was rewritten around the cause and the fix (section "Import CAD
(STEP) and Property Mapping in 2027 (issue #10)"). These are the findings
on the way there: the symptoms as first reported, the trace of the insert
step, the VBA class, templates and output locations ruled out, the import
tests and the log noise.

## Import CAD (STEP) and Property Mapping crash in 2027 (issue #10, open)

Reported by @krokosik on 2026-11-10 (NixOS, Hyprland, RTX 3060, Wine 11.20,
Inventor 2027). Not yet reproduced here; to be fixed for the next release,
after the winum release tests.

- **Symptom 1:** Assembly -> Place -> Import CAD with a STEP file (a
  Thorlabs part, PC4QR) and default options ends with "Could not import
  object". The same file imports on Windows.
- **Symptom 2:** the Property Mapping button of the import dialog opens
  Wine's crash window: page fault on write in
  `AnyCADPropertyMappingTool.exe`, in Autodesk's
  `rxapprenticeservercore` (+0x15ff9). The written address lies in the
  range where `libmono-2.0-x86_64` is loaded, and the tool's process has
  Wine Mono (`mscoree`, `libmono`, `presentationnative_cor3`) loaded: it
  runs on Wine Mono, not on the .NET Framework.
- **First hypothesis (unproven):** the import and property-mapping tools
  need the .NET Framework that the planned .NET 4.8 step of the installer
  provides (3D PDF already needed it). Check that first, before any Wine
  change.
- **Also seen in the report:** `report.sh` on NixOS found no prefix and no
  Wine ("system ()", prefix 2026 for a 2027 install, "NOT patched" for
  every DLL), so the report helper needs a look on NixOS too.

**2026-11-11, Arch, Inventor 2027, winum-11.20-1 build (Build Wine run
43022221734), a prefix with .NET Framework 4.8:** the Property Mapping
dialog opens and works (no crash), so .NET 4.8 fixes symptom 2. The import
itself still fails: Load Model reads the STEP file and shows its preview
and tree (tested with two files, one of them a simple bolt), but OK ends
with "Data Exchange Import: problems encountered ... Could not Insert
Object". Next: the same files in Inventor 2027 on Windows, to see whether
Windows inserts them; then a filtered trace of the insert step.

**2026-11-11, trace of the insert step:** Windows (Inventor 2027 in the
maintainer's VM) inserts the same files. On Linux, with a line-count marker
taken just before OK and `WINEDEBUG=err+all,fixme-all,+debugstr,warn+ole`,
the insert step on the main thread shows:

- `err:ole:com_get_class_object class {cfe9f29b-e1b6-4240-aed7-360846769314}
  not registered`, right after `RxPart.dll` is loaded. On Windows this
  class is "Microsoft APC 7.1 Object Library" (`apc71.dll`, VBA 7.1), but
  there VBA was installed by SOLIDWORKS 2026 (`InstallSource` in its
  `PreReqs\VBA`), not by Inventor: the Inventor 2027 image has no VBA
  package (not in the plan, the manifests or the files), and our installer
  skipped nothing but AGS, CER, ODIS and Access. A Windows machine with only
  Inventor would miss the class too, so this is most likely Inventor
  probing for VBA - **not the cause** (not proven: the VM has VBA).
- `RunningObjectTableImpl_GetObject Moniker unavailable (0x800401e3)` once.
- About 60 `ITypeInfo_fnInvoke invoked function failed` (0x80004005 and
  0x80070057) and some `ITypeInfo_fnGetIDsOfNames no names found`: IDispatch
  calls whose callee returned an error; which interfaces is not known yet.
- About 40 `err:dialog:EndDialog got invalid window handle`.
- No `OutputDebugString` text (`+debugstr` printed nothing).

Clean prefix with .NET Framework 4.0 + 4.8 from the installer (2026-11-11,
L4 of the .NET step): Property Mapping opens; importing the STEP file into
a part works, into an assembly it still ends with "Could not Insert
Object". So the assembly insert is what remains of this issue.

Tests in Inventor (2026-11-11): File -> Open of the STEP file works (the
part opens, but the same "Could not Insert Object" message shows). In an
assembly, Place -> Import CAD fails with both Reference Model and Convert
Model, with every Output Location (User Path, Source Path, Workspace) and
also with the assembly saved first: Load Model shows the model and its
bodies, and after OK nothing is inserted. So it is not an empty or
unwritable output path. What works and what does not: placing an existing
`.ipt` into an assembly works; Manage -> Import of the STEP file into an
open part works (the body is inserted). What fails is every import that has
to create a **new document** (File -> Open of the STEP file, Import CAD into
an assembly): the preview shows, after OK no document appears. The
templates are all in the prefix (`Templates\en-US\`, Metric and English)
and File -> New creates a part, so a missing template is ruled out too.
Next: repeat on a clean install with .NET 4.8 from the installer, to rule
out state left over from earlier tests in this prefix. Parked for now; the next step is a trace that
names the failing IDispatch calls (`trace+ole` around `ITypeInfo_fnInvoke`,
from the marker on).

Noise seen with `+seh` in the same step: access violations on the main
thread inside Autodesk's `rse.dll`, `SMData.dll`, `Cm.dll`, handled by a
handler in `rse.dll` (continue execution); C++ exceptions on another thread
from `AdpSDKCore.dll` (analytics). Neither is related to the import.

To do: reproduce on Arch with the same STEP file (2026 and 2027); repeat
with .NET 4.8 in the prefix (done 2026-11-11, see above); if it still fails, `+seh` and a filtered
`+relay` around the crash, and the import log from Inventor. Clean room:
only the crash address and module list of Autodesk's binaries, nothing
from inside them.
