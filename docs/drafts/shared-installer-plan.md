# One installer for several Autodesk products (plan, 2026-11-22)

The installer in this repository (`install-from-image.py`, `odis.py`, the
migration runner, the prefix setup) installs Inventor as Autodesk's own
installer does on Windows (`docs/installer-completeness-review.md`).
AutoCAD 2027 already installs with it (Autodesk-AutoCAD-for-Linux,
`docs/autocad-experiment-2026-11.md`, 2026-11-17) and Revit is next. This
plan keeps one installer instead of a copy per product, and adds the checks
that stop a change for one product, or one release, from breaking another.

## Decision

- **One shared core, thin product repositories.** The core (installation
  from the image, the migration runner, the common prefix setup: Wine,
  DXVK and vkd3d-proton, fonts, WebView2, isolation, licensing and the
  sign-in callback) stays in this repository for now. Each product gets a
  **profile**: default prefix, the executable, which setup steps it needs,
  extra skipped packages, default add-ins, its own migrations. What only
  Inventor needs (add-ins, Content Center, COM registration) lives in
  Inventor's profile.
- **The AutoCAD and Revit repositories pin a release of the core**, as the
  products pin a winum release, and hold only their profile, migrations,
  tools and docs. A new core is taken after that product's own test.
- The core moves to its own repository only once two products are stable
  on it.
- Not chosen: a copy of the scripts per product. Every fix of the last
  weeks (INSTALLDIR from `setup.xml`, ODIS MSI properties, bsdtar, the
  Access/ODIS names, migration 0012) would have had to be ported by hand,
  and a bug like 0010's would repeat in each copy.

## Architecture (decided 2026-11-23)

Not a rewrite: the installation core is proven (the Create Installer image
is identical to Windows' and installs to Inventor 2027.2, below). What
changes is the shape around it - five layers, each with a defined input and
output, so each can be tested and replaced on its own, and the same layers
serve every product through its profile:

1. **Get the image.** Input: `Create_Installer_<product>_<ver>_<lang>_WIN64.exe`
   (recommended: it brings the latest update and is verified against
   Windows), the parts of a Browser download, or an unpacked image. The
   Create Installer runs under winum in a small throwaway download prefix,
   never in the product's prefix, and writes the image to a folder the user
   chooses (any disk). Output: the image folder and its file list
   (`tools/image-manifest.py`), so it can be checked again later.
2. **Plan.** From the image's manifests (`odis.py`): applications,
   packages, options, what is skipped and why. Shown before installing;
   kept as golden plans.
3. **Install.** `install-from-image.py` as it is: runs the plan into the
   prefix, state per step.
4. **Set up the prefix.** The migrations, as now.
5. **Update.** The same path with a newer image: a reflink copy of the
   prefix, the update part (`WF5\`), the check, back to the copy if it
   fails. Create Installer fits this: for a new update it downloads the
   image with the update in it.

**Components.** The Electrical Catalog Browser (`aceinvaddin`) and Nastran
(`InvNastran`, part of `app.inventor`) are in Inventor's image and install
with it; the browser stays optional and on by default as on Windows,
Nastran needs a feature test (study, solve, results), not an installer
step. **Vault** is the one separate product: its own download and image,
installed as a companion product into the Inventor prefix of the same year
(AGENTS.md exception, 2026-11-23) through the same layers; whether its
Create Installer works like Inventor's is to be checked. PR #8 moves to
this path.

**GUI.** GTK 4 and Python stay. The installer emits machine-readable
events (JSON lines: step, state, progress, error) instead of the GUI
parsing `@@phase` lines, and the GUI only shows them: the source (Create
Installer, image, Browser download) and the disks for image and prefix,
the plan with components to tick (Content Center, TrueView, Electrical
Catalog Browser, Vault), install / repair / update / roll back, and a
Start button per release. The same GUI serves AutoCAD and Revit through
their profiles.

**README:** Create Installer ("Download" method in Autodesk Account)
becomes the recommended way to get the files; Browser download stays as
the fallback (maintainer, 2026-11-23).

**Order (decided 2026-11-24, replaces the six-step list of 2026-11-23 in
c9d6712).** Bottom up: harden the core, then add components, then the
GUI. The GUI only shows what the command line can already do; built
first, it would sit on parts that are still changing.

- **Phase 0 - close what is running.** L4 of the combined winum test-run
  (`test-run/next-release-1`: token integrity, combase, kernelbase,
  wbemdisp, msado15, win32u), release winum-11.22-3, then one commit here
  switching `wine/version.env` and `wine/SHA256SUMS`; README: Nastran
  works. No new Wine investigations until phase 1 is done.
- **Phase 1 - harden the installer core, no new features.** The items of
  "Work items, in order", step 1, below: ODIS under other manifest names
  (#32); atomic state, stamped unpack cache, the licensing service's
  address (#34); the full exit code of Autodesk's installers (`.cmd`
  wrapper and `%ERRORLEVEL%`), so .NET's "newer version already
  installed" is not logged as FAILED; the sign-in callback with the
  running session's Wine; DXVK and vkd3d-proton as a common step;
  Autodesk's terms before installing; the image's language detected
  when `--lang` is not given (one language besides English: use it and
  say so; several: stop and list them; a `--lang` the image lacks: an
  error) - a Czech Revit 2027.4 image installed with the default
  `en-US` would get the English transform and miss its Czech packages
  without a warning. With them the safety net (section
  below): golden plans for Inventor, an upgrade of a copy of the previous
  release's prefix, the release checklist. Every later phase relies on it.
- **Phase 2 - Create Installer as the input.** `install.sh` takes
  `Create_Installer_*.exe` directly: gets the image into a folder the user
  chooses, checks it against its manifest (`tools/image-manifest.py`),
  installs; the update is unpacked next to the image, not into
  `~/.cache`.
- **Phase 3 - components, also added to an existing prefix.** First on
  the command line:
  - The prefix records what it holds (product, year, components,
    versions) in `<prefix>/.inventor-on-linux/`.
  - A component is either part of the product's image (Nastran,
    Electrical Catalog Browser, Content Center) or a companion product
    with its own image (Vault; later others, under the AGENTS.md
    exception). Both go through the same layers: image, plan, install,
    migrations.
  - Adding one later, e.g.
    `install.sh --prefix ~/.wine-inventor2027 --add vault --source Create_Installer_<Vault>.exe`,
    takes a reflink snapshot of the prefix first and returns to it if the
    step fails.
  - **Vault PR #8 moves onto this path** as the first companion
    component (its install and its Inventor add-in); its migrations are
    renumbered (0014 Vault, 0015 TrueView #28). It is not merged before,
    so the work is not done twice.
- **Phase 4 - JSON events and the GUI.** The installer emits events
  (step, state, progress, error); the GUI only shows them. Screens: the
  product (Inventor, AutoCAD, Revit, ... through their profiles) and the
  source (Create Installer, image, Browser download); the plan with
  components to tick and the terms checkbox; after installing, **Manage
  prefix**: what is installed, *Add component*, Repair, Update, Roll
  back, Start.
- **Phase 5 - more products.** AutoCAD as a profile (comparison with
  Windows, gaps closed, an AutoCAD release); Revit after that (Wine work
  on DataIntegrity first); the core in its own repository once AutoCAD
  uses it. The update service with the snapshot (step 2 of "Downloads and
  updates" below) builds on phases 2 and 3.

Split of the work: Codex takes isolated, well-testable items of phase 1
(#32, #34, exit codes, golden plans); a Claude session takes the parts
that need the whole picture (phase 3: prefix state, the component model,
Vault on the new path; then the JSON events). Each reviews the other's
changes, as with the winum candidates.

**Fonts and text rendering** are a separate workstream (section "Fonts"
below), as they concern every product.

## Safety net

1. **Release checklist per product:** a fresh install from the image; an
   **upgrade of a copy of the previous release's prefix** (this would have
   caught 0010 before v0.4.0); an old prefix without .NET Framework 4.8
   kept as a test fixture.
2. **Golden plans:** the `odis-plan.py` output for each product image
   (package names, versions, INSTALLDIR values, what is skipped and why)
   kept as text in the repository and compared before a release; every
   difference is explained. Names only, no Autodesk files.
3. **Comparison with Windows** (`tools/compare-reference.py`) for the
   newest release of each product: done for Inventor 2027 and 2027.2,
   AutoCAD 2027 next.
4. **Every migration is tested with and without .NET Framework 4.8** and on
   an old prefix.

## Work items, in order

1. Shared fixes in the core:
   - Access/ODIS under other manifest names (#32);
   - robustness: atomic state, stamped unpack cache, the licensing
     service's address from its `.data` file (#34);
   - the sign-in callback uses the running session's Wine, not
     `select_wine`'s (AutoCAD notes 2026-11-17, finding 2);
   - DXVK and vkd3d-proton as a common setup step, not only in Inventor's
     `finish-install.sh` (finding 3) - but switched on per product
     profile: AutoCAD keeps Wine's own Direct3D (DXVK hides its
     overlays, vkd3d-proton crashes orbit), Revit cannot use DXVK
     (no D3D11 class linkage, no WARP). And `install_dxvk` sets
     `d3dcompiler_47` to `native`, which only Inventor can have: Revit
     and AutoCAD bring no `d3dcompiler_47.dll` and need
     `native,builtin`, otherwise Revit does not start at all (`c0000135`,
     Revit notes 2026-11-26);
   - **Autodesk's terms before installing** (below);
   - release checklist and golden plans for Inventor.
2. Product profiles, without changing what Inventor gets (proved by its
   golden plan and the tests).
3. AutoCAD: profile, comparison with Windows in the offline VM, the gaps
   closed, then an AutoCAD release.
4. Revit after that: it stops in DataIntegrity, which is Wine work first.

## Autodesk's terms before installing

On Windows, Autodesk's installer (ODIS) shows the terms and goes on only
after the user agrees. Our installer runs the packages directly; the
manifests themselves pass `ADSK_EULA_STATUS=#1` to the MSI packages (the
project's code does not set it), so the terms are never shown. Autodesk's
general terms are also accepted at account registration and by using the
products, but the website's terms say software that comes with a licence
agreement may not be installed before agreeing to it. The project does
what ODIS does:

- `install.sh` says, before anything is installed, that Autodesk software
  is installed under Autodesk's terms, links them
  (`https://www.autodesk.com/company/terms-of-use/en/general-terms`) and
  asks for `yes`; `--accept-autodesk-terms` for unattended runs.
- The GUI installer: a checkbox with the link; Install stays off until it
  is ticked.
- README: one sentence in the installation section.
- The terms' text is not copied into the repository, only linked.
- Nix: the flag in its configuration, at @krokosik's next batch update.

## Downloads and updates without manual steps (decided 2026-11-22)

Two questions are kept apart: **who installs** (the project's installer,
which follows the ODIS manifests and is checked against Windows) and
**where the files and updates come from** (today: the user downloads the
image and each update by hand). The installer stays the base; ODIS is
not made the base, because it updates itself and changes under the
project, it can only be observed from outside (clean room), it needs
Wine gaps closed first (the signing timestamp of Autodesk's packages,
services in session 0, WebView2), some of its custom actions need
Windows PowerShell 5.1 (part of Windows, not redistributable; PowerShell 7
is no drop-in for InstallShield's actions), and it does not fit the Nix
build. In steps, each time-boxed (three rounds):

1. **Research: ODIS only for downloading.** Can Autodesk's web installer
   (or Autodesk Access) under Wine fetch the image and its updates without
   installing, so the project's installer installs from what it fetched?
   First test 2026-11-22: what the web installer downloads, where, and
   whether the latest update comes with it.

   Result of the first test (2026-11-23, Inventor Professional 2027.2
   web installer, "Install" method, throwaway prefix, winum-11.22-1):
   - The web installer is a 7-Zip self-extractor. It unpacks `Setup.exe`
     (the ODIS bootstrap) to `%TEMP%\7zD...\` and runs it.
   - Under Wine `Setup.exe` does not start: its private side-by-side
     assemblies `odis.bs.win` and `odis.bs.wx` (wxWidgets, `AdHttpLib.dll`)
     sit in `ODIS\odis.bs.win\` and `ODIS\odis.bs.wx\`, found on Windows
     through `<probing privatePath="ODIS"/>` in `Setup.exe.config`. Wine's
     `lookup_assembly` (ntdll `actctx.c`) never reads the application
     configuration file, so `+actctx` shows "Could not find dependent
     assembly odis.bs.win" and the loader fails with c0000135. This is a
     fourth Wine gap. Known upstream: bug 56648 (DWG TrueView), bug 58527
     (AutoCAD Electrical 2026), merge request 10753 under review. If it
     is merged by Wine 11.23 we get it with the rebase; otherwise it is a
     winum fix of our own (MEASURE first, then a test in `ntdll/tests`).
   - For the test only (not for the installer), the layout was arranged so
     Wine's existing lookup finds the assemblies (`Setup.exe` moved into
     `ODIS\`, a copy of `ODIS\` under it). Then the bootstrap window
     ("Preparing for installation...") works: it downloads one package,
     `%TEMP%\odis_download_dest\<GUID>\pkg.odis.tar` (430 MB, containing only
     `ODIS/AdODIS-installer.exe`), i.e. ODIS itself, and then opens the
     ODIS window. It was cancelled there; nothing was installed.
   - ODIS's own log names "Inventor Professional 2027.2": the web
     installer targets the latest update directly, it is not 2027.0 plus
     a separate update.
   - Autodesk Account offers a separate "Download" method that downloads
     the installer without running it and, according to Autodesk's
     download-method pages, includes the latest updates like "Install"
     does ("Direct download" mostly does not). That is the method to test
     next for download-only: what it produces (an image like the one the
     project installs from today?) and whether it needs ODIS installed.

   Result of the second test (2026-11-23, same prefix): **download-only
   works.** The "Download" method gives `Create_Installer_<product>_<ver>_
   <lang>_WIN64.exe` (32 MB, a 7-Zip self-extractor holding
   `AdOdisDeployTool.exe`, a Qt tool with its own downloader, plus the
   image's `setup.xml` and manifests). Under winum-11.22-1 it runs with no
   Wine errors, asks for no sign-in, downloads the packages into
   `C:\Autodesk\WI\<id>\pkg.*.tar(.xz)` (9.7 GB, a work cache) and writes
   an ordinary unpacked image to `Downloads\Autodesk\Inventor Professional
   2027 - (EN)\` (9.8 GB: `Setup.exe`, `setup.xml`, `manifest\`, `x64\`,
   `x86\`, `3rdParty\`, `Content\`). The latest update comes with it:
   `WF5\Inventor_2027.2_Update.exe` (3.5 GB) with its own `WF5\setup.xml`,
   linked by a `setup_ext.xml` in the image root ("Inventor Professional
   2027.2 Update", depending on the product). Nothing was installed.
   Checked the same night: a dry run of `install-from-image.py` on that
   image passes all 34 steps. The download was repeated from scratch in
   a new prefix on another disk and, from the same `Create_Installer`
   file (SHA-256 compared), in an online Windows 10 VM snapshot;
   `tools/image-manifest.py compare` against `tools/image-manifest.ps1`'s
   list: 261 files, 9.78 GB on both sides, all 261 identical (SHA-256,
   size, path), nothing missing or extra. Wine downloads exactly what
   Windows does.
   Installed the same night (2026-11-23) from that image into a fresh
   prefix on another disk: `scripts/install.sh IMAGE UPDATE --prefix ...
   --skip-packages --no-desktop`, with `WF5\Inventor_2027.2_Update.exe`
   unpacked by hand first (the installer would unpack it into `~/.cache`).
   Product 34 steps, update 19 steps, migrations to 0012; Inventor starts,
   signs in, and About shows Release 2027.2, Build 334. Two update steps
   fail and are allowed by the manifest: the WebView2 runtime installer
   (known; `finish-install` installs WebView2) and ".NET Windows Desktop
   Runtime 10.0.0". The latter is explained: the product image already
   installed 10.0.9, and the update's 10.0.0 bundle detects the newer
   related bundle, skips its plan as a downgrade and exits with 0x666
   (1638, ERROR_PRODUCT_VERSION; its own log in `%TEMP%`, "Plan skipped
   due to related bundle of plan type Downgrade"). Windows does the same,
   which is why the manifest allows the failure. The installer sees 102
   because a process's exit status on Linux keeps only the low byte
   (0x666 & 0xff = 0x66); reading the full code (through a `.cmd`
   wrapper and `%ERRORLEVEL%`) would let the log say "already newer"
   instead of FAILED. An older prefix has 10.0.0 because the earlier
   Browser-download image carried 10.0.0. The uninstall entries say
   31.0.19200 in both this and an updated prefix: Autodesk does not change
   them with an update, so the release is read from About.
   Open: whether the
   work cache can be removed once the image is written; and whether the
   download link inside `Create_Installer_*.exe` expires (re-running it
   later would then need a new download from Autodesk Account).
2. **The project's own update service**, shared by all products: a timer
   (monthly by default) that says updates are available and, on the
   user's yes, takes a reflink copy of the prefix, gets the update (step 1
   or files the user downloaded), installs it with the project's
   installer, checks it (golden plan, a start of the program), goes back
   to the copy if anything fails, and then rests until the next window.
   Updates come in batches, never in the middle of work. Part of the
   check can be a small .NET smoke test built on Linux (a WinForms and a
   WPF window, a COM call, an exception crossing native and .NET code),
   run before the program itself: it does not find more than the program
   would, but it fails earlier and names the area (2026-11-23).
3. **The three Wine gaps as proper winum fixes** (tests, L1); they also
   help licensing and WebView2 (sign-in, Assistant).
4. **Only then: ODIS as an optional full path**, run on a copy of the
   prefix with the project's GUI watching it and comparing the result with
   what the project's installer does; actions that cannot run under Wine
   (PowerShell) are skipped and listed. It becomes the default only if
   that comparison holds over several releases.

If step 1 does not work, step 2 still works with files the user
downloads, so no step is wasted.

Maintainer, 2026-11-26: **stability first, updates are not a priority.**
A user who downloads a `Create_Installer_*.exe` gets the latest release
with its update already in it, so most users never need an update path.
Autodesk's release notes decide when a new release is worth installing.
Autodesk Access (Autodesk's own updater) inside the prefix is an
experiment for later, not part of the plan. Updates within a release year
stay what step 2 describes: the project's installer on a reflink copy of
the prefix, never a downgrade, a new release year always a new prefix.

What is known about `Create_Installer_*.exe` (tests of 2026-11-23): it
carries the image's `setup.xml` and manifests and its own downloader, and
the product version is in its name and its manifests (Inventor 2027.2,
Revit 2027.4). That points to a fixed version, but it is not tested.
Test to run once Autodesk publishes the next update of a product we have
an older `Create_Installer` for (the Inventor 2027.2 file of 2026-11-23,
SHA-256 recorded):

1. Run the old file again in a throwaway prefix (download only, as in the
   second test) and record whether it still downloads at all (the open
   question of an expiring link above).
2. Compare the new image with the one of 2026-11-23 with
   `tools/image-manifest.py compare`: identical (the file is pinned to
   its version), or the newer update (it asks the server for the latest).
3. Download a fresh `Create_Installer` from Autodesk Account for the same
   product and compare file names and sizes with the old one: does
   Autodesk publish a new file per update?

The answer decides what the README tells users: "keep your installer
file, it reinstalls the same version" or "download a fresh one when you
reinstall". One installer change follows either way: the launchers must
find the licensing service's version folder from what is installed
(`AdskLicensing\<version>\`), not from a fixed version, so that an update
of the service does not break the start (phase 1).

## Fonts (2026-11-23)

What is known: Wine ships its own Tahoma (LGPL) and maps the classic
Win32 UI font (`MS Shell Dlg`) to it; WPF and newer UI ask for Segoe UI,
which may not be distributed. The installer's default
(`scripts/linux-fonts.sh`) copies Liberation, Noto and DejaVu into the
prefix and maps Windows family names (Arial -> Liberation Sans, Segoe UI
-> Noto Sans, ...); `INV_FONTS=windows` copies fonts from the user's own
Windows installation. Without any Windows fonts WPF's fallback fails fast
(`docs/arch-hyprland.md`, "Windows fonts are required"). Autodesk brings
its own engineering fonts (AIGDT/AMGDT in Inventor; AutoCAD its SHX fonts
and a few TrueType fonts) - to be listed per product from the prefix and
the Windows reference, not assumed. @krokosik found (#13, #18, Nix only)
that small Tahoma text is jagged because Wine takes anti-aliasing from
fontconfig first: with `rgba` none it never reaches ClearType, while
Windows uses ClearType by default (`FontSmoothingType=2`).

Order:
1. **Inventory, measured:** which families Inventor and AutoCAD ask for
   and what Wine gives them (a `+font` trace summary), and which fonts the
   Windows reference install puts into `C:\Windows\Fonts`
   (`compare-reference.py` already lists the files).
2. **Wine first:** whether Wine should follow the registry's ClearType
   setting over fontconfig is a winum candidate (test measured in the
   offline VM; krokosik's probe ran on a networked machine, so it is
   re-run there).
3. **Project settings like Windows:** `FontSmoothingType=2` and the
   family mappings as a migration, after step 2 decides what the Wine
   side covers; krokosik's Nix logic ported to `scripts/` where still
   needed, so both paths render the same.
4. Segoe UI stays the user's own (their Windows fonts); the free mapping
   remains the default.

## Not part of the installer

- **Autodesk Genuine Service** stays optional (`--with ags`): AutoCAD 2027
  started on Windows with its folder moved away and reported nothing
  (maintainer, 2026-11-22), and its installer fails under Wine (its custom
  action needs Windows PowerShell).
- **Licensing service and Identity Manager updates** come on Windows
  through Autodesk Access, not with the product updates (Inventor 2027.2
  had neither; the AutoCAD VM had Identity Manager 1.19.2.0 where the
  prefix has 1.16.5.1). Open: an optional step that installs Autodesk's
  standalone installers the user downloads (the project never downloads
  Autodesk files itself).
