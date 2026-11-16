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
  manifest marks it optional). It is Autodesk's check for non-genuine
  software, not the licensing itself (Inventor licenses without it).
  Decision (maintainer, 2026-11-16): install it as Windows does, so that
  nothing of Autodesk's own protection is left out - first as a test on a
  prefix copy (does its service run under Wine, start-up time, crashes,
  CPU); kept unless it causes problems, and then the reason is written
  here.
  Installable since 2026-11-16 (branch `installer-review`):
  `install-from-image.py IMAGE --with ags` installs it (a name given with
  `--with` overrides the skip list); the default stays without it until
  the test below is done. **Test on a prefix copy** (the maintainer; the
  working prefix is not touched):
  1. With winum's `bin` first in `PATH`
     (`~/.local/share/inventor-on-linux/winum-*-x86_64/bin`), stop the
     prefix and copy it with reflinks:
     `WINEPREFIX=$PREFIX wineserver -k; cp -a --reflink=auto $PREFIX $PREFIX-ags`.
  2. `--dry-run` first: `python3 scripts/install-from-image.py $IMAGE
     --prefix $PREFIX-ags --with ags --dry-run | grep -v 'already done'` -
     only the AGS package(s) may be left to run.
  3. The same without `--dry-run`; the package's `exit code` line and, if
     it hangs, how long (its service may not report "running" to Wine,
     like the licensing service).
  4. What it left: `WINEPREFIX=$PREFIX-ags wine reg query
     'HKLM\System\CurrentControlSet\Services' | grep -i genuine` (the
     service; its `Start` value with `wine reg query '<that key>' /v
     Start`).
  5. `INV_YEAR=2027 INV_PREFIX=$PREFIX-ags bash scripts/launch-inventor.sh`: time to the
     home page compared with the working prefix, `top -b -n1 | grep -i
     genuine` after a minute (CPU), Inventor's smoke test, and a crash or
     message box from AGS.
  Result: pending.
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
  Windows reference. First run on the reference prefix: all 11 782
  installed ADIX files identical; nine files turned off on purpose by the
  prefix setup (six add-ins, `InteractiveTutorial.dll` and its resources,
  `CER\senddmp.exe`); the rest missing belongs to the two applications not
  installed (TrueView, Electrical Catalog Browser). Seven TrueView files in
  `Common Files\Autodesk Shared` (`AcInetEngine26.dll`,
  `AcInetEngineps26.dll`, `AcSignCore16.dll`, `AcShellEx\*`,
  `en-US\AcAxDb26res.dll`) are already in the prefix from another package
  in a different build; which one wins once TrueView is installed has to
  match Windows (package order, file versions).
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

## Fixes (branch `installer-review`, 2026-11-16)

Points 1-8 of "Needed" and Genuine Service, one commit each with a unit
test under `tests/` (synthetic manifests, `setup.xml`, setup UI settings
and ADIX zips; no Autodesk files). Not merged, no tag. `--dry-run` prints
every application, package, property, location, action and file that is
left out, with the reason. Status of each: **fixed in the installer, not
yet checked on a real install** - the results of the maintainer's run
(below) go into the table.

| Point | What the installer does now | Existing prefixes | Check | Result |
|---|---|---|---|---|
| 1 Registration | `Inventor.exe /install 0` once after the product's packages and the .NET 4.8 step, winemenubuilder off for everything it runs, then `wineserver -k`/`-w`; checks `Inventor.Application` and `Inventor.PartDocument` in `user.reg`; not finished = warning, tried again on the next run | migration `0005-inventor-registration` (a registration that does not finish warns, does not stop the launcher; again with `migrate-prefix.sh --run 0005`) | `user.reg` has both keys; no new `~/.local/share/applications/wine-*.desktop`; install.log `registered:` | pending |
| 2 `setup.xml` properties | `<Properties>` become variables (`INV_INSTALL_PATH`); a `RegistrySearch` whose key and value exist in the prefix wins; logged as `var    %X% = ... (setup.xml; ...)` | none needed for `INSTALLDIR` (files in place); the InvAcNGEN action (.NET native images) did not run in them - open, below | install.log `var    %INV_INSTALL_PATH% = C:\Program Files\Autodesk\Inventor 2027\`; InvAcNGEN runs with `...\Inventor 2027\Bin`; compare: `NGenService` keys | pending |
| 3 `CONTENT_PATH` | from `SetupRes/locale/<lang>/<app>.xml` (`defaultVal`), else ODIS's default `%PROGRAMDATA%\Autodesk` | none (files in place) | install.log `var    %CONTENT_PATH% = C:\ProgramData\Autodesk (setup UI default, ...)` | pending |
| 4 `INSTALLDIR` | for every MSI with an `installLocation` that can be filled in; unknown variable: warning, not passed | none (files in place) | compare-reference section 2: no `INSTALLDIR` "Windows passes ..., we don't" | pending |
| 6 Action parameters | unknown `%VARIABLE%` in path or parameters: action skipped with `WARN skip action ...`; MSI properties left out, install parameters with unknown variables and action types never run are listed | - | install.log: no `WARN skip action` for Inventor's packages | pending |
| 5 Applications | every `manifest/app.*.xml` except `*.ui` (inventor, dclibrary, aceinvaddin, dwgtrueview); `--no-app`, `install.sh --no-trueview/--no-electrical`, GUI switches; .NET 4.8 (TrueView's dependency) stays with its own step. A file another package already put into the prefix keeps the higher file version (Windows Installer's rule), each logged as `shared file ...` | no migration (the files come from the image): a repair run of `install.sh` with the same download installs the new applications (finished packages are skipped). A prefix that already has an update keeps those applications at the base build - a new installation is the clean way | compare-reference section 3: TrueView and Electrical files no longer missing; section 3a: the seven `Common Files\Autodesk Shared` files have Windows' size; admeta-check: TrueView/Electrical packages complete | pending |
| 7 ADIX root files | listed as `not installed (outside VFS, not package metadata): ...` | - | install.log line for InvCore (`SharedComponents.json`) - decide per file | pending |
| 8 Standard MSI properties | `MSIFASTINSTALL=7`, `REBOOT=ReallySuppress`, `ARPSYSTEMCOMPONENT=1` on every MSI (not on MSP patches) unless the manifest gives one | none: only `SystemComponent=1` in the parts' uninstall entries, nothing reads it | compare-reference section 2: these three no longer "Windows passes ..." | pending |
| Genuine Service | `--with ags` installs it; default without it until the test above | - | the test on a prefix copy ("On purpose") | pending |

Open, to be decided with the results:

- **`RegistrySearch` and setup UI attribute names are guessed** (`root`/
  `key`/`name` and their usual spellings; the variable name of a setup UI
  setting from `name`, `id`, `property`, ... or the element name).
  `tools/odis-audit.py IMAGE` prints what it understood (sections
  "Variables from setup.xml" and "Setup UI settings"); a search it cannot
  read is logged with its attribute names and the default is used.
- **`inventor.ui` is assumed to be a UI description**, not an application
  (left out). odis-audit's "Applications in the image" shows whether it
  has packages; compare-reference shows whether Windows installed any.
- **The NGEN action in existing prefixes:** InvCore's postInstall
  `InvAcNGEN.exe` makes .NET native images (84 `NGenService` keys on
  Windows); existing prefixes ran it with the unexpanded variable. Native
  images only make .NET code start faster; a migration needs the action's
  exact command line from a new install.log and a check that it works
  under Wine first.
- **Package order** still differs from ODIS (point 1 does not depend on
  it any more).
- **Nix (@krokosik):** the Nix build runs `install-from-image.py` and
  `finish-install.sh`, so it now installs DWG TrueView and the Electrical
  Catalog Browser too (larger store path; `--no-app` exists if the package
  should leave them out), and runs the registration (in the build sandbox,
  without a display - a registration that does not finish is only a
  warning, bounded by the 600 s timeout).
- **Point 9** (UPI2 keys, the product's uninstall entry, `dotnet` in
  `PATH`): decided by the maintainer on 2026-11-16 - not now; after the
  comparison with the 2027.2 update, since UPI2 is mainly what updates
  rely on.
- **`INSTALLDIR` for MSIs without an `installLocation`**: measured with
  `tools/installdir-check.py` on the Windows capture (2026-11-16): the
  image has seven MSI packages; the four with an `installLocation` got it
  (InvPrivate, InvPrivateLoc, DCLibrary64, Autodesk Genuine Service), the
  three without one (`adsk-hive-host.msi`, `cer.msi`,
  `AceInvAddIn-ca.msi`) all got `C:\Program Files\Autodesk` =
  `%INSTALL_DEST%`. The installer now passes `%INSTALL_DEST%` to every MSI
  without an `installLocation`.
- **`Registry.reg` next to `Registry.dat`** (the three Material Library
  packages), compared with `tools/adix-registry-names.py` (names only,
  2026-11-16): the same key and the same five value names in both
  (`HKLM\SOFTWARE\Autodesk\ADSKAssetLibrary\5` resp.
  `...\ADSKTextureLibraryNew\1\Textures` and `\2\Textures`: `Build`,
  `LibraryPaths`, `Master`, `ProductLine`, `Release`). The `.reg` writes
  its keys as `REGISTRY\MACHINE\...`, like the hive. It holds nothing the
  imported `.dat` does not: nothing to add.
- **`CONTENT_PATH`**: the image has `<Setting name="CONTENT_PATH"
  defaultVal="%PROGRAMDATA%\Autodesk" deployment="true" standalone="true">`,
  but run 2 used ODIS's default (same value) because the first reader did
  not find it. The reader now looks at every setup UI file and falls back
  to a plain pattern for a file the XML parser rejects. Where the file is:
  to be confirmed in the next run's log (`var    %CONTENT_PATH% = ...
  (setup UI default, <file>)`).

### Wine bug: msiexec and a property value with a space

Worth a report on bugs.winehq.org. A program that passes an MSI property
whose value has a space as one argument -
`wine msiexec /i X.msi /qn "INSTALLDIR=C:\Program Files\X"` - gets
1639 (`ERROR_INVALID_COMMAND_LINE`): Wine builds the command line
`msiexec /i X.msi /qn "INSTALLDIR=C:\Program Files\X"` (the whole
argument quoted, the usual Windows convention), Wine's msiexec keeps those
quotes when it splits the line and quotes the value again, and the
Windows Installer reads a property named `"INSTALLDIR` with unbalanced
quotes. ODIS's own form, `INSTALLDIR="C:\Program Files\X\"`, works, but
cannot be produced through Wine's command line building. What Windows'
msiexec does with the same command lines is **not measured yet**; the
synthetic reproducer (a tiny MSI built with `wixl`, a script for Wine and
one for the Windows VM) and the step-by-step reading of Wine's code are in
[docs/wine-repro/msiexec-property-spaces/](wine-repro/msiexec-property-spaces/README.md).
The report is written once Windows is measured; not filed yet.

The installer's workaround (since 2026-11-16): an msiexec command line
with a space goes into `C:\odis-logs\NN-<package>.msi.cmd` and runs
through `wine cmd /c`. **Autodesk-Revit-for-Linux** has its own `.bat`
workaround for its step 25 (the same failure); it should be replaced by
this helper (`run_msiexec` in `install-from-image.py`) once the two
installers share the code again.

### Clean room exception: file versions of shared files

Decided by the maintainer on 2026-11-16: `install-from-image.py` reads the
file version (the `VS_FIXEDFILEINFO` version stamp) of a file that two
packages install (point 5: the seven TrueView files in `Common
Files\Autodesk Shared`), to keep the newer one as Windows Installer does.
Only the version stamp is read - nothing else from Autodesk files (no
code, no other resources, no disassembly). It is an explicit exception to
"not looking inside vendor binaries beyond crash addresses" (AGENTS.md,
"Clean room"); the version stamp is also what Windows' own file
properties dialog shows.

### Check (the maintainer's run)

A fresh prefix on `/mnt/nvme` from the two download parts with this
branch, then `tools/admeta-check.py`, `tools/compare-reference.py` against
the Windows capture (`~/vm-inventor/cap`) and the Inventor smoke test
(start, part, assembly, drawing, save/reopen, restart, Import CAD, 3D
PDF). Filtered output only. Results go into the table above and here.

Results:

**Run 1 (2026-11-16, `/mnt/nvme/.wine-inventor2027-review`, winum-11.20-2):**
stopped at step 22/32, `InvPrivate.msi`: exit code 103 after 0.2 s, i.e.
1639 (`ERROR_INVALID_COMMAND_LINE`) - the new
`INSTALLDIR=C:\Program Files\Autodesk\Inventor 2027\`. Cause, read in
Wine 11.20's source: Wine builds the Windows command line from the
arguments and puts an argument with a space in quotes as a whole
(`"INSTALLDIR=C:\Program Files\..."`, ntdll `build_command_line`);
msiexec splits it keeping the quotes (`chomp`) and quotes the value once
more (`build_properties`), so the Windows Installer reads a property
named `"INSTALLDIR` with unbalanced quotes (`msi_parse_command_line`).
Every property value with a space fails this way - also Revit's earlier
"values with a space" failure. ODIS passes `INSTALLDIR="C:\Program
Files\...\"`, which these functions parse correctly (checked with a
local port of the three functions, not committed). Fix: an msiexec command
line with a space goes into `C:\odis-logs\NN-<package>.msi.cmd` and runs
through `cmd /c` (cmd hands the line to msiexec unchanged, waits for it in
a batch file and returns its exit code); commands without a space run as
before. A Wine bug report is possible (msiexec should not keep the quotes
around a whole argument); not filed yet.

**Run 2 (2026-11-16, same prefix, resumed at step 22):** `InvPrivate.msi`,
`InvPrivateLoc.msi` and `DCLibrary64.msi` installed through the batch
file with `INSTALLDIR` (exit code 0). Stopped at step 31,
`AceInvAddIn-ca.msi` (Electrical Catalog Browser, the content package):
1603. Its MSI log: the custom action `AceUnzipZipFiles` reports "Error
when unzipping" for `M:\x64\AceAddIn-ca\Documents\ADSK\Content\AceInvLib.zip`
(its CustomActionData: that zip and the target `C:\users\Public\Documents\
Autodesk\Inventor Electrical Library 2027\`). On Windows the result is 20
files in `Public Documents\Autodesk\Inventor Electrical Library 2027`.
Two possible causes, to be told apart from outside (clean room: Wine
debug channels only, nothing looked at inside the action's DLL):
(a) the action unzips through the Windows shell (Explorer's zip folder,
`zipfldr`), which Wine does not implement - then a winum candidate with a
test; (b) it fails because the source is on `M:` (the image mapped as a
drive; Bitrock InstallBuilder installers also fail from `M:`). Check:
the same MSI once with `WINEDEBUG=+loaddll` (does `zipfldr.dll` load?)
and once from a copy of its folder on `C:`. Decision (maintainer, 2026-11-16): if (b), the
package is installed from a copy of its folder on `C:` (the action stays
as it is); if (a), the Electrical Catalog Browser is left out by default
with a note in the README, and zipfldr becomes a winum candidate with a
test. The installer never places the zip's contents itself.
Diagnosis (2026-11-16): (b) ruled out - from a copy on `C:` the action
fails the same way (Wine: `custom_get_thread_return invalid Return Code
1359`, i.e. the action returned ERROR_INTERNAL_ERROR; 0 files in the
library folder); the copy mechanism prepared for (b) was reverted. (a) not
shown either: with `+loaddll`, `zipfldr.dll` was not loaded (`shell32` and
`cabinet` were). Next hypothesis (c): the action needs the .NET Framework
(a managed custom action), which our installer adds only after all
packages while Windows has it from the start. Check: the DLLs the run
loaded (`mscoree`, `clr`), the COM classes it asked for (`+ole`), and the
same MSI again once .NET 4.8 is in the prefix. If (c), the cause is our
order, not Wine: the decision for (a)/(b) does not apply and is asked
again. Result (maintainer's trace): after the action's DLL
(`msiXXXX.tmp`) only the usual MFC/GUI dependencies load (winex11,
msimg32, compstui, winspool, gdiplus, oleacc, msacm32, winmm) - no
mscoree/clr, and no cabinet, shell32 or zipfldr (those were loaded earlier
by msiexec itself): a native action that unzips with its own code, so (c)
is ruled out and (a) unlikely. Hypothesis (d), the maintainer's: the
CustomActionData also carries the user's SID (`S-1-5-21-0-0-0-1000`) and
the product code, so the action probably sets permissions on the library
folder for that user, before or after unzipping, and a Wine security call
fails (the action returns 1359, ERROR_INTERNAL_ERROR). Next: one msiexec
run with `+loaddll,+advapi,+security,+file,+seh`, filtered to the thread
that loaded the action's DLL (its last calls before it returns, security
calls, errors), and whether the target folder is created at all.

  **Cause found (trace with `+loaddll,+advapi,+security,+file,+seh`,
  filtered to the thread that loaded the action's DLL, 2026-11-16):**
  none of (a)-(d). The action creates the target folder
  (`CreateDirectoryW ...\Inventor Electrical Library 2027\`), copies
  the zip to a temporary folder (`C:\ACED5EA\ZIPD5EB\AceInvLib.zip`)
  and then starts the command line
  `tar -xf "C:\ACED5EA\ZIPD5EB\AceInvLib.zip" -C "C:\ACED5EA\OUTD5EC" --keep-newer-files`.
  Windows 10 (since 1803) has `C:\Windows\System32\tar.exe` (bsdtar,
  from libarchive); Wine has no `tar.exe`. The trace shows the program
  search for the unquoted command line (`tar`, `tar.exe`, `tar -xf`,
  `tar -xf "C:\...zip"`, ... in system32, windows, system, wbem,
  WindowsPowershell\v1.0 and the current folder) finding nothing; the
  action then returns 1359 and the MSI rolls back (the folder is gone
  afterwards). No security call failed. A Wine gap, but a missing
  program rather than a broken function: the decision for (a)/(b) does
  not cover it and is asked again. Possible ways: leave the Electrical
  Catalog Browser out by default until there is a `tar.exe`; a winum
  candidate that adds a `tar.exe` to Wine (at least `-x -f <zip> -C <dir>
  --keep-newer-files`, with a test whose expected results come from
  Windows' own `tar.exe` in the VM - L1 is possible, Windows 10 has it);
  or libarchive's own Windows build of bsdtar - the program Windows ships
  as `tar.exe` - as a pinned, SHA-256-checked download put into the
  prefix before the packages (also in `nix/inventor.nix`). Whether
  libarchive publishes such a build: not checked yet.
  Decision (maintainer, 2026-11-16): now the Electrical Catalog Browser is
  off by default (`DEFAULT_OFF` in `install-from-image.py`;
  `--include-app aceinvaddin`, `install.sh --with-electrical`, the GUI
  switch off; note in the README). The fix: libarchive's own Windows build
  of bsdtar as `C:\windows\system32\tar.exe` - pinned and SHA-256
  checked, a prefix setup step before the packages, a migration for
  existing prefixes, `fetchurl` in `nix/inventor.nix` (@krokosik to be
  told) - and then the Catalog Browser back on by default. A `tar.exe` in
  winum (option 2) only if libarchive has no usable Windows build.
  Measured (maintainer, 2026-11-16): Windows 10 19045.6456 has
  `C:\Windows\System32\tar.exe`, `tar --version`: `bsdtar 3.5.2 -
  libarchive 3.5.2 zlib/1.2.5.f-ipp` - the program option 3 would put in
  the prefix. libarchive's latest release (v3.8.11, GitHub API) has only
  source archives (`libarchive-3.8.11.tar.gz`/`.tar.xz`/`.zip`, each with
  an `.asc` signature), no Windows build. Older releases: to be checked.
  If none has a usable one, the choice is between building bsdtar.exe
  ourselves from the pinned, signature-checked source (MinGW, in public
  CI, the source next to the binary - as winum does with Wine) and
  option 2; the maintainer decides.
  Older releases (GitHub API, maintainer): official Windows builds
  `libarchive-vX-win64.zip` with `.asc` exist up to v3.5.3. **Chosen
  (maintainer, 2026-11-16): `libarchive-v3.5.3-win64.zip`** - official,
  signed, the same 3.5 line as Windows' bsdtar 3.5.2; no own build.
  - Pinned in `scripts/lib/bsdtar.env`: SHA-256 of the zip
    `81c45c31a31a7b49809b3625594c28a1afbcc18faa6ee1d2ab4e4328ba8ef736`,
    of its `libarchive/bin/bsdtar.exe`
    `b072373bb24396c83e56093a8842497069b9014e7dc6caec2b595ad1057ff5c2`.
    The `.asc` is signed by the key with fingerprint
    `A5A45B12AD92D964B89EEE2DEC560C81CEC2276E` (the same key signs
    `libarchive-3.5.3.tar.gz`); the maintainer verifies it with
    libarchive's release key. Verified (maintainer, 2026-11-16, key from
    keyserver.ubuntu.com): both `.asc` "Good signature from Martin Matuska
    <mm@FreeBSD.org>", made 2022-02-08, primary key fingerprint
    `A5A4 5B12 AD92 D964 B89E EE2D EC56 0C81 CEC2 276E`; the key has expired
    since (gpg: "[expired]"), which does not affect signatures it made
    while valid. SHA-256 of both files as pinned.
  - Contents of the zip: `bin/bsdtar.exe`, `bsdcpio.exe`, `bsdcat.exe`,
    `archive.dll`, headers, import/static libraries, man pages - no
    license file. `bsdtar.exe` is statically linked with libarchive
    (it does not import `archive.dll`; imports: kernel32, user32,
    advapi32, bcrypt, `VCRUNTIME140.dll` and the UCRT `api-ms-win-crt-*`,
    which the image's VC++ 2015-2022 redistributable and Wine provide).
    So only `bsdtar.exe` goes into the prefix, as `tar.exe` (the name
    Windows uses) in `system32` and, in a WoW64 prefix, `syswow64` too
    (Windows 10 has a `tar.exe` in both). libarchive's `COPYING` comes from
    the signed 3.5.3 source release (`libarchive-3.5.3.tar.gz`, SHA-256
    `72788e5f58d16febddfa262a5215e05fc9c79f2670f641ac039e6df44330ef51`),
    kept in `scripts/lib/licenses/libarchive-3.5.3-COPYING` and copied to
    `<prefix>/.inventor-on-linux/doc/libarchive-3.5.3/COPYING`.
  - Where: `install-from-image.py` puts it in place before the packages
    (the Catalog Browser needs it during its install); migration
    `0006-bsdtar-tar-exe` for existing prefixes; `nix/inventor.nix`
    fetches the same zip (`bsdtarArchive`) and links it into
    `DOWNLOAD_DIR`. The Catalog Browser is on by default again.
  - **Security:** 3.5.x lacks the security fixes of later libarchive
    releases (3.6 onwards). Accepted (maintainer, 2026-11-16): in the
    prefix only installers run it, on Autodesk's own archives from the
    user's image; nothing feeds it untrusted archives. If that ever
    changes, an own build of a current release (from the signed source)
    replaces it.
  - **Nix (@krokosik):** a new fixed-output download in
    `nix/inventor.nix`, `bsdtarArchive` =
    `libarchive-v3.5.3-win64.zip` (2.3 MB, sha256 above), linked into
    `DOWNLOAD_DIR`; `install-from-image.py` writes `tar.exe` into the
    prefix before the packages. The package also gets DWG TrueView and the
    Electrical Catalog Browser by default now (`--no-app` leaves one out).
  - Result: pending (the next install: `AceInvAddIn-ca.msi` exit code 0,
    20 files in `Public Documents\Autodesk\Inventor Electrical Library
    2027`, as on Windows).

**Run 3 (2026-11-16, same prefix, resumed at step 31, Catalog Browser on
again):** `tar.exe` (bsdtar 3.5.3) went into `system32` and `syswow64`
before the packages; `AceInvAddIn-ca.msi` with
`INSTALLDIR="C:\Program Files\Autodesk"` through the batch file: exit
code 0 after 0.6 s; the library folder holds 9 entries at its top level
(Windows: 20 files - whether counted the same way, recursively, is to be
checked). DWG TrueView: 1 885 files placed, 4 480 registry keys. Files
another package had put there already: the seven in `Common
Files\Autodesk Shared` have the same version (26.0.59.0) and size as
TrueView's but other bytes - replaced (equal versions: the package's
copy, as Windows Installer does); two fonts without a version,
`AIGDT___.TTF` (36 520 -> 42 132 bytes) and `AMGDT___.ttf` (25 964 ->
12 461 bytes), replaced by TrueView's - which size Windows has:
compare-reference section 3a, which now also checks `windows\Fonts` and
`Public Documents\Autodesk`. .NET 4.8 installed; the registration
finished in 11.3 s with both keys; migrations 0005 and 0006 found it
already so. `CONTENT_PATH` was still not found in a setup UI file (the
`<Setting name="CONTENT_PATH">` is elsewhere in the image - its file to
be named; the value equals ODIS's default).

**Comparison after run 3 (2026-11-16; the prefix of runs 1-3, so with
the installer of three different commits - a fresh install with the final
branch is still to come):**
- Electrical Catalog Browser library: the same 20 files as on Windows.
- `tools/admeta-check.py`: 13 527 ADIX files, 13 511 identical, 9 turned
  off on purpose, 0 missing, 7 different (InvCore 4, RealDWG Shared 2,
  InvCore language pack 1) - which ones: to be listed.
- MSI properties: `adsk-hive-host.msi` still without `INSTALLDIR` (installed
  in run 1, before INSTALL_DEST for MSIs without a location); `DC_GOST`
  and `STANDALONE_LP` passed by us, not by Windows - fixed (setup options
  are not passed); `CURRENTDIRECTORY`, `CLIENTUILEVEL`,
  `MSICLIENTUSESEXTERNALUI`, `CLIENTPROCESSID` are the Windows Installer
  client's own (now ignored by the tool); `TRANSFORMS` for
  `InvPrivateLoc.msi` as known.
- Files: Windows added 17 260, 1 400 not in the prefix - AdODIS, CER,
  Genuine Service, ODIS, Uninstallers (on purpose); Inventor 2027 (34),
  Common Files\Autodesk Shared (1), ADPSDK, IDSDK, AdskLicensingService
  and the user's AppData (first start?), the shortcuts
  `Public\Desktop\Autodesk Inventor Professional 2027.lnk` and
  `Documents\Inventor\Inventor Eletrical Project 2027.lnk`: to be listed.
- Different size: `AIGDT___.TTF` and `AMGDT___.ttf` - **Windows has the
  copies that were in the prefix before DWG TrueView** (36 520 and 25 964
  bytes); our rule (unversioned: the later package's copy) gave
  TrueView's. Whether Windows installs TrueView earlier or keeps an
  existing unversioned file: to be found (package order on Windows).
  `Inventor.ini` and `InvRO.ini` 3 bytes shorter than on Windows: open.
  The rest (licensing log, `uninstall.dat`, `UserConsent\en.json`) is
  written at run time.
- Only in the prefix: `Program Files\Autodesk\AutoCAD 2027` (25 files),
  `ProgramData\Autodesk\ODIS` (94, our extract of Shared Components),
  `Inventor 2027` (9, `Addins.disabled`), licensing and IDSDK files: the
  AutoCAD folder to be explained.
- Registry: 21 400 keys missing in 10 900 groups (AdODIS/DDA, COM
  interfaces, ...): to be grouped.

**Details of the comparison after run 3 (maintainer's filtered lists):**
- **Electrical Catalog Browser in the wrong folder:** its 25 files were in
  `Program Files\Autodesk\AutoCAD 2027\Bin\InventorElectrical\` and
  `...\AutoCAD 2027\Bin\Addins\Autodesk.Electrical.Inventor.addin`
  instead of `Inventor 2027\Bin\...` (the 25 "missing in Inventor 2027"
  and "only in the prefix" files are the same). Its ADIX package keeps
  them under that folder in its VFS; ODIS moves them by the manifest's
  `InstallPathMappings`, which the installer used only for the registry.
  Fixed: the mappings apply to files too (installer and admeta-check),
  every mapping is logged with the number of files it moved. The mapping
  format (folder token, VFS or C: source) is read generically - the next
  install's log shows what the image has.
- **The 7 files admeta-check called different** are the shared files of
  DWG TrueView in `Common Files\Autodesk Shared` (AcShellExtension.dll,
  AcLauncher.exe, AcInetEngineps26.dll, AcInetEngine26.dll from InvCore;
  AcSignCore16.dll, en-US\AcAxDb26res.dll from RealDWG Shared;
  AcShellExtensionRes.dll from InvCoreLP): TrueView, installed last by us,
  replaced their copies. On Windows TrueView's package finished first
  (log times 07:49:59, RealDWG 07:50:00, InvCoreLP 07:50:01, InvCore
  07:50:03) and Windows has the later packages' copies - also of the two
  fonts. Fixed: TrueView now comes first in the plan; with equal versions
  or no version the later package's copy stays, as on Windows.
- **Other files missing in the prefix:** the six add-ins, `senddmp.exe` and
  `InteractiveTutorial` turned off on purpose;
  `Autodesk Robot Structural Analysis Engine 2027\Cfg\USER_cfg.lnk` and the
  shortcuts `Public\Desktop\Autodesk Inventor Professional 2027.lnk`,
  `Documents\Inventor\Inventor Eletrical Project 2027.lnk` (shortcuts:
  open - who creates them on Windows, and whether Wine's MSI makes .lnk
  files with winemenubuilder off); the "other" groups are Windows'
  (Temp 330, `AppData\Roaming\UI Launcher` 89 - ODIS's UI,
  `AppData\Local\Packages` 45, `Windows\Installer` 35 - its MSI cache,
  `ProgramData\Microsoft` 24, `System32` 14, D3DSCache).
- **Registry, 21 400 missing keys by path:** 8 436
  `hklm:software\wow6432node\classes` - the tool's mistake (Windows
  exports 32-bit classes there, Wine keeps the same key as
  `software\classes\wow6432node`), fixed in compare-reference; 6 009
  `hkcu:software\classes\interface` and 6 009
  `hkcu:software\classes\wow6432node` - COM interfaces Windows registers
  per user (Inventor's registration), to be checked whether the prefix has
  them machine-wide (the tool now counts those apart); 1 088
  `hklm:software\microsoft\windows`, 212 `wow6432node\microsoft`, 86
  `.netframework`, 27 `classes\installer`, 21 UPI2, 18 DDA (Autodesk
  Access), 16 services: to be read after the next comparison.

**Dry run with the finished branch (2026-11-16, fresh prefix
`.wine-inventor2027-review2`):** order `dwgtrueview, inventor, dclibrary,
aceinvaddin`; `CONTENT_PATH` and further settings now from `setup.xml`
(`INVENTORLANGUAGESTRING`, `LANG2LONG`, `UPIMASTERID`, `UNITS`,
`DRAWINGSTANDARD` - setup options, so not passed to MSIs, as on
Windows); the Catalog Browser's two mappings `[{ProgramFilesX64}]\Autodesk\AutoCAD 2027\
-> C:\Program Files\Autodesk\Inventor 2027` move 19 + 6 files; the other
mappings name the folder the VFS already uses (TrueView 1 573 files,
Inventor 2027, Common Files, ProgramData). Four packages map
`[{Common Documents}]\ -> %PUBLIC%\Documents\`, which was not understood:
`%PUBLIC%` is now `C:\users\Public`. The same mappings replace folder
tokens in the packages' registry values, so until now such values got the
text `%PUBLIC%\Documents\...` - in existing prefixes too. Checked in the
run-3 prefix (2026-11-16): three plain string (REG_SZ) values, which are
never expanded - Inventor's Task Scheduler (`TaskScheduler\Installation
Path`: `DBQ`, the path of its database, and `LogFile`) and
`HTML Help -> admapi_31_0.chm` (the API help); the other `%PUBLIC%` values
in `system.reg` are Wine's own shell folders (REG_EXPAND_SZ, fine).
Migration `0007-public-documents-paths` rewrites such Autodesk values to
`C:\users\Public\...` in existing prefixes.

What run 1 showed before that:
- Applications: `inventor, dclibrary, aceinvaddin, dwgtrueview`;
  `inventor.ui` left out.
- `%INV_INSTALL_PATH%` = `C:\Program Files\Autodesk\Inventor 2027\`;
  its RegistrySearch was understood
  (`HKLM\SOFTWARE\Autodesk\Inventor\RegistryVersion31.0 ->
  InstallLocation`, not in a fresh prefix). Also from `setup.xml`:
  `INSTALLED_PRD_VER` (empty), `DC_GOST=0` (now passed to
  `InvPrivate.msi`, as a manifest property that can be filled in),
  `STANDALONE_LP=0`.
- InvCore's NGEN action now runs with real paths:
  `M:\x64\InvCore\InvAcNGEN.exe install 31.0.19200.0
  M:\x64\InvCore\inventor.acngen "C:\...\Inventor 2027\Bin"`, exit
  code 0 after 0.7 s (whether it made native images: compare, NGenService).
- `%CONTENT_PATH%`: no setup UI settings file named it - ODIS's default
  was used. To check: where the setting is in the image.
- `adsk-hive-host.msi` got no `INSTALLDIR`: its manifest has no
  `installLocation`, yet Windows passed `C:\Program Files\Autodesk`. Where
  ODIS takes it from is open.
- ADIX files outside VFS: `AppxMetadata/CodeIntegrity.cat` and
  `Assets/*.png` (MSIX package metadata and logos), `SharedComponents.json`
  (REX Inventor, Geospatial Coordinate Systems, RealDWG, InvCore), and in
  the three Material Library packages `Icon.png` and `Registry.reg` next to
  the `Registry.dat` that is imported. Whether `Registry.reg` holds more
  than `Registry.dat`: open.
