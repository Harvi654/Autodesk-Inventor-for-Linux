# Add-ins that are off by default

`finish-install.sh` / `rebuild-prefix.sh` move these add-ins to
`Inventor 2026/Addins.disabled/`, outside `Bin/Addins` (Inventor 2026 also
loads add-ins from subfolders of `Bin/Addins`, so a `disabled` subfolder there
does not work). The list is `INV_DEFAULT_DISABLED_ADDINS` in
`scripts/lib/common.sh`.

```bash
bash scripts/addins.sh list              # what is on / off
bash scripts/addins.sh enable NAME       # e.g. frameanalysis
bash scripts/addins.sh disable NAME
bash scripts/addins.sh reset             # back to the default set
```

| Add-in | Why it is off |
|---|---|
| `Autodesk.SharedViews.Inventor.addin` | **crashes Inventor**: loaded through wine-mono, which cannot load its .NET 10 references and ends the process |
| `Autodesk.Feedback.Inventor.addin`, `Autodesk.PerfFeedbackAddin.Inventor.addin` | usage reporting |
| `Autodesk.InteractiveTutorial.Inventor.addin` | tutorial overlay, not needed |
| `Autodesk.Publisher.Inventor.addin`, `Anark.Core.addin` | 3D PDF: the dialog opens, but Publish crashes Anark's `corewrapper.exe` (a .NET Framework program, so it runs on wine-mono): it calls into oleaut32's proxy tables as if they were code - most likely a COM interop gap in wine-mono. Inventor itself keeps running. Not fixed yet |
| `autodesk.translatorfusion.inventor.addin` | Fusion interop, untested |

Untested means: please try it with `addins.sh enable` and report what happens.

iLogic was off by default until 2026-10-18; it works now (rules, parameters
driving the model) and is on. An existing prefix: `bash scripts/addins.sh enable ilogic`.

Frame Analysis was off until 2026-10-22; with Wine build `wine-11.20-6` it
works (study, constraints, loads, Simulate, results). The Robot solver
`rkernel.exe` writes its results into one compound file from four threads at
once; Wine's ole32 storage code had no locking and corrupted its block chains
(assertions `blockIndex != nextBlock` / `depotBlockCount < bigBlockDepotCount`
in storage32.c). Fixed by `patches/ole32-storage-thread-lock.patch` and
`patches/ole32-transacted-truncate-dirty.patch` (a stream truncated to zero in
a transacted storage was left out of the commit). An existing prefix:
`bash scripts/addins.sh enable frameanalysis`.

Stress Analysis was off until 2026-10-18; with the ntdll, rpcrt4 and combase
Wine fixes it works (mesh, simulate, results) and is on. An existing prefix:
`bash scripts/addins.sh enable simulationstressanalysis`.

Dynamic Simulation was off until 2026-10-20; it works (joints from
constraints, gravity, Run, Replay, Construction Mode) and is on. An existing
prefix: `bash scripts/addins.sh enable dynamicsimulation`. The Simulation
Player panel can end up behind Inventor's main window - Alt+Tab brings it back.
