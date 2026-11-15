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

## First comparison: Inventor 2027 (2026-11-15)

Windows 10 VM (offline) against a fresh prefix made by `install.sh` with
winum-11.20-2, both from the same image (SHA-256 of both download parts
compared), no update. How it was done: [tools/README.md](../tools/README.md).
Windows added 17 260 files and about 49 000 registry keys; the prefix lacked
3 251 of the files. After sorting, the differences come down to the points
below. Status: found, not fixed yet; each fix goes into the installer and,
for existing prefixes, into a migration.

### Needed

1. **Inventor's own registration is never run.** On Windows, during the
   install, `msiexec` starts `Inventor.exe /install 0` (Process Monitor:
   `Inventor.exe` with that command line, parent `msiexec.exe`, writes
   `HKCU\Software\Classes\Inventor.Application` and
   `InventorRegistrationLog_<pid>.log` in `%TEMP%`). It registers the COM
   server `Inventor.Application` (used by add-ins, iLogic, Vault, external
   programs), the document types `Inventor.PartDocument`,
   `.AssemblyDocument`, `.DrawingDocument`, `.PresentationDocument`,
   `.iFeatureDocument`, `.DesignViewDocument`, `.ProjectDocument` (icons,
   open/print verbs, shell extensions) and type libraries (`RxAppCtrl.Ocx`,
   `RxInventor.tlb`, `UCxTextBtn.Ocx`, `InfoTip.Dll`, `ThView.Dll`). In the
   prefix none of these keys existed. Running the same command once in the
   reference prefix created them (`Inventor.Application`: 0 -> 10 entries in
   `user.reg`, 12 in `system.reg`; `Inventor.PartDocument` 0 -> 11 in
   `user.reg`) and the registration log. It showed no window and ended on
   its own with exit code 0 (Wine's console showed Inventor's start-up
   messages: DXVK, ADP SDK, Identity Manager). Helper processes it started
   kept the wineserver alive (`wineserver -w` did not return), so the
   installer stops the prefix after it. It must run with winemenubuilder
   off (`WINEDLLOVERRIDES=winemenubuilder.exe=d`): the manual run created
   13 `wine-extension-*.desktop` / `wine-protocol-*.desktop` files in
   `~/.local/share/applications` pointing at the test prefix (removed by
   hand; the `adskidmgr://` default stayed `adskidmgr-handler.desktop`).
   Which package's action starts it is not certain. Process Monitor: the
   parent `msiexec.exe` (the Windows Installer service running the
   multi-package transaction) had last opened the cached package of
   "Autodesk Interoperability Engine Manager" (`adsk-hive-host.msi`)
   before it started `Inventor.exe /install 0`; the action lists of
   `InvPrivate.msi` are the same on Windows and Wine, and Wine's logs of
   `adsk-hive-host.msi` and `InvPrivateLoc.msi` show no such action. Order
   on Windows: InvCore 22:45:47, adsk-hive-host 22:47:04, InvPrivate
   22:47:34, registration 22:47:41 - Inventor's files were in place. Our
   installer runs adsk-hive-host as package 2 of 28, before any Inventor
   file exists, so an action that needs `Inventor.exe` could not have run.
   Either way the fix is the same: run the registration once after the
   Inventor packages. Whether an update runs it again: see the 2027.2
   comparison.
2. **`%INV_INSTALL_PATH%` is never filled in.** It is defined in the
   image's `setup.xml` (`<Properties><Property property="INV_INSTALL_PATH"
   defaultValue="%INSTALL_DEST%\Inventor 2027\">` with a `RegistrySearch`
   for an existing install), which the installer does not read. Effects:
   no `INSTALLDIR` for `InvPrivate.msi` and `InvPrivateLoc.msi` (Windows:
   `C:\Program Files\Autodesk\Inventor 2027\`; the files still landed in
   the right folder - unlike AutoCAD's ACAD Private - but by the MSI's
   default, not by design), and the InvCore postInstall action ran as
   `InvAcNGEN.exe install ... %INV_INSTALL_PATH%Bin` with the variable
   unexpanded (the .NET native images, 84 `NGenService` keys on Windows, are
   not made). Fix: read the `setup.xml` properties as variables.
3. **`%CONTENT_PATH%`** (Content Center, `DCLibrary64.msi`,
   `installLocation="%CONTENT_PATH%\Inventor 2027"`) is a setting of the
   setup UI (`SetupRes/locale/<lang>/dclibrary.xml`, default
   `%PROGRAMDATA%\Autodesk`); Windows passed
   `INSTALLDIR=C:\ProgramData\Autodesk\Inventor 2027`. Same fix, plus that
   default.
4. **`INSTALLDIR` is also passed by Windows for `adsk-hive-host.msi`**
   (`C:\Program Files\Autodesk`). Generally: ODIS passes the package's
   install location to every MSI that has one.
5. **Two applications of the image are not installed.** The image has
   `manifest/app.{inventor,dclibrary,dwgtrueview,aceinvaddin,inventor.ui}.xml`;
   ODIS installs `dwgtrueview` (DWG TrueView 2027, 1 573 files, its
   `acax26*.tlb`, `dwgviewrAcctrl.dll`, `MsiKeyFile_*` in Common Files) and
   `aceinvaddin` (Electrical Catalog Browser 2027 and its language pack:
   `Bin\InventorElectrical\*`, `Autodesk.Electrical.Inventor.addin`, the
   Electrical Library in Public Documents) by default; the installer plans
   `inventor` (+ `dclibrary`) only. Fix: the same default as Windows, with
   an option to leave each out (installer and GUI).
6. **Unknown variables in action parameters are passed on silently.** Only
   the action's program path is checked. Fix: check the parameters too and
   skip the action with a warning (point 2 is the case that showed it).
7. **ADIX packages: files at the package root other than the known
   metadata are dropped silently** (`SharedComponents.json` in InvCore).
   Fix: list them in the log; decide per file.
8. **ODIS's standard MSI properties** are not passed: `MSIFASTINSTALL=7`,
   `REBOOT=ReallySuppress`, `ARPSYSTEMCOMPONENT` (keeps the parts out of
   Programs and Features). For `InvPrivateLoc.msi` ODIS also passes a
   transform it generates in `%TEMP%`; the resulting files and keys match,
   it is not looked into further.
9. **Registration ODIS writes itself:** `HKLM\SOFTWARE\Autodesk\UPI2\{...}`
   for 24 products, four values in `...\Autodesk\UPI`, the Programs and
   Features entry of the product ("Autodesk Inventor Professional 2027 -
   English"). Smaller: `C:\Program Files\dotnet\` in the machine `PATH`
   and `SOFTWARE\dotnet\Setup\InstalledVersions\x64` (the .NET 10 runtimes),
   `.NETFramework\AssemblyFolders\Autodesk Inventor 31.0` (references for
   add-in developers). Whether Inventor or updates need them: next step.

### Not a gap

- The large MSI property list of `InvPrivate.msi` (`ACADSERIALNUMBER`,
  `UNITS`, `DC_*`, `READONLYMODE`, ...) whose values are `%...%`: ODIS does
  not pass them either (Windows' command line for the package holds only
  ODIS's standard properties and `INSTALLDIR`), so leaving them out matches.
- Add-ins the prefix setup turns off on purpose (`.addin` files moved).
- Windows' own background changes (logs, caches, Defender), counted and
  left out by the tool.

### On purpose (decide or document)

- Autodesk Access (`AdODIS`, Access service), CER (crash reporting and its
  service), ODIS itself with its metadata and `Uninstallers`.
- **Autodesk Genuine Service** is installed by Windows by default (the
  manifest marks it optional). It is part of Autodesk's licensing checks;
  the goal is that licensing works as on Windows, so whether to install it
  needs a decision.
- `AdskLicensingService` start type Manual instead of Auto (the launcher
  starts it).

### Also found

- `.admeta` next to every ADIX package in the image is JSON: the
  package's files, fonts and registry keys. Its `hash` field is not a hash
  of the file content (44 base64 characters; md5, sha1, sha256, sha512,
  sha3-256, blake2s in hex and base64, whole file and MSIX 64 KiB block
  hashes, and the stored bytes in the package all tried - none match, also
  for one-block files). `tools/admeta-check.py` therefore uses the list and
  compares every listed file in a prefix with the same file inside the
  package (present, size, SHA-256): a file integrity check without a
  Windows reference.
- The order of the packages differs from ODIS (e.g. adsk-hive-host before
  InvCore, see point 1). Worth comparing as a whole once the fixes are in.
- `wineserver -k` cannot reach a wineserver whose prefix folder was moved
  (here: to the trash) while it ran; the "prefix busy" check then refuses
  the new prefix of the same path. Nothing to do with the installer, but the
  message could say how to find and stop those processes.

### Next

Fix points 1-8 in `install-from-image.py` with tests (synthetic manifests,
`setup.xml` properties, action parameter check), migrations for existing
prefixes (registration, `INSTALLDIR`-less MSIs need no change if their files
are in place), install again and compare until only the "on purpose" list
remains; then the 2027.2 update the same way (VM snapshot
`inventor2027-base` + update, prefix copy + update).
