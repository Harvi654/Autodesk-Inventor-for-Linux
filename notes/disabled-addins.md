# Disabled Inventor Addins

These addins are moved to `Inventor 2026/Addins.disabled/` (outside `Bin/Addins`) to reduce failure surface area.
To re-enable: `bash scripts/addins.sh enable NAME` (or move them back to `Bin/Addins/`).

**Note:** the original location `Bin/Addins/disabled/` does not work on Inventor 2026 builds
that scan subfolders of `Bin/Addins` - the add-ins were still loaded from there.

## Non-essential (disabled in Phase 7 to reduce crash surface)
- `Anark.Core.addin` - 3D PDF/Anark (requires CEF, which we excluded)
- `Autodesk.Feedback.Inventor.addin` - Telemetry/feedback
- `Autodesk.PerfFeedbackAddin.Inventor.addin` - Performance telemetry
- `Autodesk.SharedViews.Inventor.addin` - Cloud shared views
- `Autodesk.InteractiveTutorial.Inventor.addin` - Tutorial overlay
- `Autodesk.Publisher.Inventor.addin` - Publishing features
- `autodesk.translatorfusion.inventor.addin` - Fusion 360 translator

## Simulation (disabled - heavy, not needed for basic modeling)
- `autodesk.dynamicsimulation.inventor.addin` - Dynamic simulation
- `autodesk.frameanalysis.inventor.addin` - Frame analysis (FEA)
- `autodesk.simulationstressanalysis.inventor.addin` - Stress analysis (FEA)

## Broken in Wine (disabled due to crashes)
- `autodesk.ilogic.inventor.addin` - iLogic automation (.NET COM interop failure: E_FAIL 0x80004005 on DesignProjectManager.get_ActiveDesignProject)

## TODO: Re-enable once Inventor is stable
Priority order for re-enabling:
1. iLogic (needs .NET COM interop fix)
2. Simulation addins (may work once core is stable)
3. Translator/Publisher addins
4. Anark (needs CEF/libcef.dll - 205MB, excluded from initial copy)

## Confirmed on Inventor 2026 build 30.40 (.NET 10), Wine 11.19
- Inventor itself runs on CoreCLR (.NET 10), but some add-ins are still loaded
  through wine-mono. `Autodesk.SharedViews.Inventor.addin` re-enabled ->
  wine-mono assertion in `mono_runtime_object_init` (SharedViews.dll needs
  `System.Runtime 10.0`) -> `Environment.Exit` -> Inventor closes. Keep disabled.
- iLogic and SharedViews were still loaded with their .addin in `Bin/Addins/disabled/`:
  Inventor scans subfolders. Fixed by moving disabled add-ins outside `Bin/Addins`.
- `scripts/addins.sh reset` restores this default set.
