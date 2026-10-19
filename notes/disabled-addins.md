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
| `autodesk.frameanalysis.inventor.addin` | the study, constraints and loads work; Simulate crashes the Robot solver `rkernel.exe` inside Wine's ole32 structured storage: StgStreamImpl_Write -> TransactedSnapshotImpl_StreamWriteAt -> stream resize (small -> big blocks) -> SmallBlockChainStream_ReadAt -> BlockChainStream_ReadAt -> BlockChainStream_GetSectorOfOffset reads past its index cache (stale block-chain cache in a transacted storage, most likely). Not fixed yet |

Untested means: please try it with `addins.sh enable` and report what happens.

iLogic was off by default until 2026-10-18; it works now (rules, parameters
driving the model) and is on. An existing prefix: `bash scripts/addins.sh enable ilogic`.

Stress Analysis was off until 2026-10-18; with the ntdll, rpcrt4 and combase
Wine fixes it works (mesh, simulate, results) and is on. An existing prefix:
`bash scripts/addins.sh enable simulationstressanalysis`.

Dynamic Simulation was off until 2026-10-20; it works (joints from
constraints, gravity, Run, Replay, Construction Mode) and is on. An existing
prefix: `bash scripts/addins.sh enable dynamicsimulation`. The Simulation
Player panel can end up behind Inventor's main window - Alt+Tab brings it back.
