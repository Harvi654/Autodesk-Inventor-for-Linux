# Installer completeness review (plan, 2026-11-15)

## Decision

The offline installer (`scripts/install-from-image.py` reading the
manifests of the user's own install image) stays the way Inventor is
installed. Stability first: the same image gives the same prefix, it works
without network, and it is what the NixOS build (`requireFile`, no network
in the sandbox) is built on.

The other way - running Autodesk's own installer (ODIS, the web installer)
under Wine - was looked at (2026-11-15, a public AutoCAD 2026 project that
does it: private ODIS DLLs put on `WINEPATH`, the install run with the clock
set back because Wine does not honour the signing timestamp of Autodesk's
packages, services moved to session 0 in wineserver, WebView2 109). It needs
more Wine changes, its input changes with what Autodesk serves on the day,
and it does not fit the Nix build. It may come back later as an optional
path, once winum has proper fixes for those three Wine gaps (each with a
test and L1).

## Why a review

The installer replaces ODIS, so whatever ODIS does that the installer does
not imitate is missing, silently. AutoCAD 2027 showed it (see
Autodesk-AutoCAD-for-Linux, `docs/autocad-experiment-2026-11.md`): the
"ACAD Private" MSI landed in `C:\Program Files\` because its target is
`%ACAD_INSTALL_PATH%`, which only ODIS fills in, and AutoCAD then refused to
license. Revit 2027 showed two more (MSI property values with a space fail
in Wine's msiexec; `%LANGUAGE_CODE%` unknown). Inventor works and passes the
smoke tests, but nobody has checked that the prefix holds everything a
Windows installation of the same image holds - files and registry.

Known places where the installer drops something today:

1. `do_msi`: MSI properties whose value still contains `%` after expansion
   are left out without a message ("ones only ODIS can fill in").
2. MSI packages: the manifest's `installLocation` is not passed at all; the
   MSI installs to its own default folder.
3. ADIX packages: their `HKLM\SOFTWARE\Autodesk\UPI2\{upi2}` registration
   (which ODIS writes) is not written.
4. Actions with an unknown variable are skipped (`skip action ... (unknown
   variable)`).
5. On purpose: ODIS, Autodesk Access, CER, Genuine Service and optional
   packages (`skipped:` in the plan).

## Plan

1. **Audit output.** The installer (also with `--dry-run`) lists, per
   package, every property, install location, action or parameter it
   drops or cannot expand, with the variable name - a warning, not
   silence. Unit test with a small synthetic manifest.
2. **Windows reference.** Install Inventor 2027 from the same image in the
   maintainer's offline Windows 10 VM with Autodesk's installer. Keep
   locally (never committed): file lists of `Program Files`,
   `Program Files (x86)`, `ProgramData` and the user's `AppData` (Autodesk
   folders), registry exports of `HKLM\SOFTWARE\Autodesk`, its
   `WOW6432Node`, `HKCU\Software\Autodesk`, the Uninstall keys and the
   services, ODIS's `Install.log`; optionally a Process Monitor capture of
   the first start.
3. **Compare** with a fresh prefix from the installer (same image, same
   options). Tools from Autodesk-AutoCAD-for-Linux (`regdiff.py`: key and
   value names only; `pml-vs-prefix.py`) plus a file-list diff. Sort every
   difference into: needed (fix), intentionally skipped (document why),
   Windows-only (no counterpart under Wine).
4. **Fix** in the installer, and for existing prefixes as migrations (every
   change to what a prefix gets is a new migration). Candidates already
   known: install-path variables of the main product (the
   `%ACAD_INSTALL_PATH%` kind) passed as `INSTALLDIR`; `%LANGUAGE_CODE%`
   from `--lang`; MSI property values with spaces reaching msiexec as
   `PROP="value"`; UPI2 keys for ADIX packages if the comparison shows
   they matter.
5. **Check:** a fresh install and a migrated prefix, both compared again
   (step 3 shows nothing unexplained); the usual Inventor smoke test
   (start, part, assembly, drawing, save/reopen, restart, Import CAD, 3D
   PDF); the NixOS build (with @krokosik).

The same review is then repeated for every product the installer handles
(AutoCAD, Revit), since they share the code.
