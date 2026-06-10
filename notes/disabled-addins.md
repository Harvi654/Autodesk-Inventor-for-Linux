# Disabled Inventor Addins

These addins were moved to `Bin/Addins/disabled/` to reduce failure surface area.
To re-enable, move them back to `Bin/Addins/`.

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
