# Add-ins that are off by default

`finish-install.sh` / `rebuild-prefix.sh` move these add-ins to
`Inventor 2026/Addins.disabled/`, outside `Bin/Addins` (Inventor 2026 also
loads add-ins from subfolders of `Bin/Addins`, so a `disabled` subfolder there
does not work). The list is `INV_DEFAULT_DISABLED_ADDINS` in
`scripts/lib/common.sh`.

```bash
bash scripts/addins.sh list              # what is on / off
bash scripts/addins.sh enable NAME       # e.g. simulationstressanalysis
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
| `autodesk.simulationstressanalysis.inventor.addin`, `autodesk.frameanalysis.inventor.addin`, `autodesk.dynamicsimulation.inventor.addin` | heavy, untested |

Untested means: please try it with `addins.sh enable` and report what happens.

iLogic was off by default until 2026-10-18; it works now (rules, parameters
driving the model) and is on. An existing prefix: `bash scripts/addins.sh enable ilogic`.
