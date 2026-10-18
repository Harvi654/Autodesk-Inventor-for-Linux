# Add-ins that are off by default

`finish-install.sh` / `rebuild-prefix.sh` move these add-ins to
`Inventor 2026/Addins.disabled/`, outside `Bin/Addins` (Inventor 2026 also
loads add-ins from subfolders of `Bin/Addins`, so a `disabled` subfolder there
does not work). The list is `INV_DEFAULT_DISABLED_ADDINS` in
`scripts/lib/common.sh`.

```bash
bash scripts/addins.sh list              # what is on / off
bash scripts/addins.sh enable NAME       # e.g. ilogic, simulationstressanalysis
bash scripts/addins.sh disable NAME
bash scripts/addins.sh reset             # back to the default set
```

| Add-in | Why it is off |
|---|---|
| `Autodesk.SharedViews.Inventor.addin` | **crashes Inventor**: loaded through wine-mono, which cannot load its .NET 10 references and ends the process |
| `Autodesk.Feedback.Inventor.addin`, `Autodesk.PerfFeedbackAddin.Inventor.addin` | usage reporting |
| `Autodesk.InteractiveTutorial.Inventor.addin` | tutorial overlay, not needed |
| `Autodesk.Publisher.Inventor.addin`, `Anark.Core.addin` | publishing / 3D PDF, untested |
| `autodesk.translatorfusion.inventor.addin` | Fusion interop, untested |
| `autodesk.ilogic.inventor.addin` | works with the current fixes (2026-10-18: iLogic tab, rule editor with snippets and model tree, a `MessageBox` rule runs in an assembly); still off by default until rules that change parameters are tested. It failed on older setups only because `Default.ipj` was missing |
| `autodesk.simulationstressanalysis.inventor.addin`, `autodesk.frameanalysis.inventor.addin`, `autodesk.dynamicsimulation.inventor.addin` | heavy, untested |

Untested means: please try it with `addins.sh enable` and report what happens.
