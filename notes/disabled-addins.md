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
| `Autodesk.Publisher.Inventor.addin`, `Anark.Core.addin` | **only without .NET Framework 4.8** (`INV_DOTNET48_ADDINS`): 3D PDF's Publish crashes Anark's `corewrapper.exe` on wine-mono. With the .NET Framework 4.8 that `install-from-image.py` installs from the image, they are on |
| `autodesk.translatorfusion.inventor.addin` | Fusion interop, untested |
| `Autodesk.AssistantAddin.Inventor.addin` | Inventor 2027: the "Ask Autodesk Assistant" panel (an online AI assistant). The add-in was already in `Bin\Addins` before the 2027.2 Update, its panel shows up since 2027.2 - drawn wrongly under Wine, and it is not needed. The 2027.2 Update also puts a copy into `ProgramData\Autodesk\Inventor 2027\Addins\Assistant\<version>\` (the "Inventor MCP Server" package); turning off the one in `Bin\Addins` was enough, the panel did not come back |

Untested means: please try it with `addins.sh enable` and report what happens.

3D PDF (2026-11-08): with Microsoft's .NET Framework 4.8 in the prefix
instead of wine-mono for the .NET Framework parts, `corewrapper.exe` runs,
and with winum's `oleaut32-typelib-keep-released` the export takes about
15 s for a part and 20 s for an assembly (in testing). The two add-ins stay
off without it; since 2026-11-11 `install-from-image.py` installs the
image's .NET Framework 4.8 and `finish-install.sh` / `addins.sh reset` then
leave them on. See "3D PDF (Anark)" and ".NET Framework 4.8 in the prefix"
in `docs/arch-hyprland.md`.

iLogic was off by default until 2026-10-18; it works now (rules, parameters
driving the model) and is on. An existing prefix: `bash scripts/addins.sh enable ilogic`.

Frame Analysis was off until 2026-10-22; with Wine build `wine-11.20-6` it
works (study, constraints, loads, Simulate, results). The Robot solver
`rkernel.exe` writes its results into one compound file from four threads at
once; Wine's ole32 storage code had no locking and corrupted its block chains
(assertions `blockIndex != nextBlock` / `depotBlockCount < bigBlockDepotCount`
in storage32.c). Fixed by `ole32-storage-thread-lock.patch` and
`ole32-transacted-truncate-dirty.patch` (in winum since winum-11.20-1; the
former copies are in `docs/archive/own-wine-build/patches/`) (a stream truncated to zero in
a transacted storage was left out of the commit). An existing prefix:
`bash scripts/addins.sh enable frameanalysis`.

Stress Analysis was off until 2026-10-18; with the ntdll, rpcrt4 and combase
Wine fixes it works (mesh, simulate, results) and is on. An existing prefix:
`bash scripts/addins.sh enable simulationstressanalysis`.

Dynamic Simulation was off until 2026-10-20; it works (joints from
constraints, gravity, Run, Replay, Construction Mode) and is on. An existing
prefix: `bash scripts/addins.sh enable dynamicsimulation`. The Simulation
Player panel can end up behind Inventor's main window - Alt+Tab brings it back.
