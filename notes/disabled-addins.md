# Add-ins that are off by default

`finish-install.sh` / `rebuild-prefix.sh` move these add-ins to
`Inventor <year>/Addins.disabled/`, outside `Bin/Addins` (Inventor also
loads add-ins from subfolders of `Bin/Addins`, so a `disabled` subfolder there
does not work). The lists are `INV_DEFAULT_DISABLED_ADDINS` (always off) and
`INV_DOTNET48_ADDINS` (off without .NET Framework 4.8) in
`scripts/lib/common.sh`.

Since 2026-11-16 only the Assistant is off by default (and, without .NET
Framework 4.8, 3D PDF and SharedViews). Migration
`0010-default-addins-on` turns the others on in existing prefixes; whoever
wants one off again: `bash scripts/addins.sh disable NAME`.

```bash
bash scripts/addins.sh list              # what is on / off
bash scripts/addins.sh enable NAME       # e.g. frameanalysis
bash scripts/addins.sh disable NAME
bash scripts/addins.sh reset             # back to the default set
```

| Add-in | Why it was off | Test 2026-11-16 | Now |
|---|---|---|---|
| `Autodesk.SharedViews.Inventor.addin` | **crashed Inventor** on wine-mono: loaded through it, which cannot load its .NET 10 references and ends the process | works with .NET Framework 4.8 (share, Autodesk Viewer) | **on with .NET Framework 4.8**, off without it (`INV_DOTNET48_ADDINS`) |
| `Autodesk.Feedback.Inventor.addin`, `Autodesk.PerfFeedbackAddin.Inventor.addin` | usage reporting | load, nothing broke | **on**, as on Windows; Inventor's own settings turn usage reporting off |
| `Autodesk.InteractiveTutorial.Inventor.addin` | tutorial overlay, not needed; `InteractiveTutorial.dll` and `en-US\InteractiveTutorial.resources.dll` were moved to `Addins.disabled\libs` as a crash source | works: the tutorial downloads and runs. Its window opens at the far right and has to be moved by hand (a WebView placement issue, open) | **on with .NET Framework 4.8**, off without it (`INV_DOTNET48_ADDINS`): on Wine Mono it crashed Inventor right after the splash at every start (2026-11-18, migration 0012, found by @Lukas10999); the two libraries stay in `Bin` |
| `autodesk.translatorfusion.inventor.addin` | Fusion interop, untested | loads (Add-In Manager) | **on**. Real use needs Autodesk Desktop Connector and Fusion Team data, which this project does not install |
| `Autodesk.Publisher.Inventor.addin`, `Anark.Core.addin` | **only without .NET Framework 4.8**: 3D PDF's Publish crashes Anark's `corewrapper.exe` on wine-mono | (on since 2026-11-11 with .NET 4.8) | on with .NET Framework 4.8, off without it (`INV_DOTNET48_ADDINS`) |
| `Autodesk.AssistantAddin.Inventor.addin` | Inventor 2027: the "Ask Autodesk Assistant" panel (an online AI assistant). The add-in was already in `Bin\Addins` before the 2027.2 Update, its panel shows up since 2027.2. The 2027.2 Update also puts a copy into `ProgramData\Autodesk\Inventor 2027\Addins\Assistant\<version>\` (the "Inventor MCP Server" package); turning off the one in `Bin\Addins` was enough, the panel did not come back | loads, but its panel is drawn wrongly (WebView2) | **off** - the only add-in off by default (maintainer's decision); `bash scripts/addins.sh enable assistant` turns it on. Revisit with the WebView work |

The test (maintainer, 2026-11-16): a copy of a 2027 prefix with .NET
Framework 4.8, winum-11.20-2 and vkd3d-proton 3.0.1-winum-1, all add-ins
on at once with `bash scripts/addins.sh enable-safe`. Details in
`docs/arch-hyprland.md`, Result log 2026-11-16.

If an add-in misbehaves for you: `addins.sh disable` it and report what happens.

3D PDF (2026-11-08): with Microsoft's .NET Framework 4.8 in the prefix
instead of wine-mono for the .NET Framework parts, `corewrapper.exe` runs,
and with winum's `oleaut32-typelib-keep-released` the export takes about
15 s for a part and 20 s for an assembly (in testing). The two add-ins stay
off without it; since 2026-11-11 `install-from-image.py` installs .NET
Framework 4.0 and the image's 4.8 and `finish-install.sh` / `addins.sh
reset` then leave them on. Confirmed on a clean Inventor 2027.2
installation (2026-11-11): both on, 3D PDF Publish works. See "3D PDF (Anark)" and ".NET Framework 4.8 in the prefix"
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
