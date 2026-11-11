# Arch Linux + Hyprland: setup notes and findings

The engineering log of this project: how the installation works, every
problem found on the way (symptom, cause down to the Wine function, fix,
how it was found) and the dated **Result log** at the end. Written on Arch
Linux with Hyprland and KDE Plasma; most of it applies to every
distribution. For installing and using Inventor, read the
[README](../README.md) first.

Wine fixes are being moved to [winum](https://github.com/Harvi654/winum),
a Wine shared with other engineering programs; its per-patch pages
(`docs/patches/`) carry the validation tables. Sections here describe what
Inventor needed and point there for details.

Some older sections mention `rebuild-prefix.sh` or `/mnt/windows`: that was
the first setup, which copied a Windows installation. Its sections are in
[archive/arch-hyprland-retired-2026-11-08.md](archive/arch-hyprland-retired-2026-11-08.md).

## Contents

- **Installation:** [One command: scripts/install.sh](#one-command-scriptsinstallsh); [Installing from Autodesk's install image (no Windows needed)](#installing-from-autodesks-install-image-no-windows-needed); [Inventor 2027: unpacked image without a year, the 2027.2 Update (issue #6)](#inventor-2027-unpacked-image-without-a-year-the-20272-update-issue-6)
- **Desktop:** [Hyprland](#hyprland)
- **Prefix setup:** [OGSFactory.dll is not modified](#ogsfactorydll-is-not-modified); [DXVK and isolation](#dxvk-and-isolation); [Windows fonts are required](#windows-fonts-are-required); [Default.ipj is required (materials, appearances, shading)](#defaultipj-is-required-materials-appearances-shading); [WebView2: white licensing window, empty Home tab](#webview2-white-licensing-window-empty-home-tab); [File icons and thumbnails](#file-icons-and-thumbnails)
- **Fixes by area:** [Design Accelerator (Shaft, gears, ...): "Failed to create shaft"](#design-accelerator-shaft-gears--failed-to-create-shaft); [Content Center](#content-center); [Frame Generator: Insert Frame creates nothing](#frame-generator-insert-frame-creates-nothing); [Drawings: editing dimension text](#drawings-editing-dimension-text); [Sketch: an edited dimension shows only after the mouse moves](#sketch-an-edited-dimension-shows-only-after-the-mouse-moves); [Sketch: black rectangles around the sketch input boxes (fixed)](#sketch-black-rectangles-around-the-sketch-input-boxes-fixed); [Crash "XI_BadDevice ... X_GetDeviceButtonMapping" (Hole command)](#crash-xi_baddevice--x_getdevicebuttonmapping-hole-command); [Status bar: white instead of dark](#status-bar-white-instead-of-dark); [Open: crash while browsing (fixed in wine-11.20-4)](#open-crash-while-browsing-fixed-in-wine-1120-4); [Frame Analysis: Simulate crashes the solver (fixed in wine-11.20-6)](#frame-analysis-simulate-crashes-the-solver-fixed-in-wine-1120-6); [Import CAD (STEP) and Property Mapping crash in 2027 (issue #10, open)](#import-cad-step-and-property-mapping-crash-in-2027-issue-10-open)
- **Graphics and repainting:** [GPU ray tracing (Inventor 2027, works in testing)](#gpu-ray-tracing-inventor-2027-works-in-testing); [Status bar: old text stays after GPU ray tracing (workaround)](#status-bar-old-text-stays-after-gpu-ray-tracing-workaround); [Window drawn shifted after ray tracing (open)](#window-drawn-shifted-after-ray-tracing-open); [Home page stays stale after a dialog (open)](#home-page-stays-stale-after-a-dialog-open)
- **3D PDF:** [3D PDF (Anark) - works in testing](#3d-pdf-anark---works-in-testing); [.NET Framework 4.8 in the prefix](#net-framework-48-in-the-prefix-installer-step)
- **Wine:** [Prefix migrations](#prefix-migrations-updating-an-installed-prefix-2026-11-11); [This project's own Wine (v0.2)](#this-projects-own-wine-v02); [winum as the Wine for Inventor](#winum-as-the-wine-for-inventor-winum-11201)
- **Logs:** [Known harmless log messages](#known-harmless-log-messages); [Result log](#result-log)

## One command: scripts/install.sh

```bash
bash scripts/install.sh DOWNLOAD [UPDATE ...] [--prefix DIR] [--no-content] [--no-desktop]
```

DOWNLOAD is what Autodesk's **Browser download** gives (all `.exe` parts,
their folder, or an unpacked image) - not the small `..._webinstall.exe`
that "Install" gives. It runs: packages (official repos), every Wine fix
(`build-wine-dll.sh`, skipped when already installed), unpacking, Inventor +
Content Center, updates, `finish-install.sh`, desktop entry. Rerun the same
command after a failure; finished steps are skipped.

Verified on a fresh prefix (Inventor image + 2026.4 update, ~6 minutes with
the Wine fixes already built): sign-in, 2026.4, Home page New/Open, sketch
(no black boxes, dimensions redraw at once), extrude, materials, Content
Center, Design Accelerator shaft in an assembly. Browser download (a 15 MB
`..._db_001_002.exe` + the `..._db_002_002.7z` with the data) given as their
folder: the `.7z` unpacks to the install image directly, found and used.
The 2026.x update is a separate download (account -> Updates); the
`Create_Installer_...exe` files are Windows-only tools, not needed.

## Installing from Autodesk's install image (no Windows needed)

This is how `install.sh` installs Inventor: instead of copying a Windows
installation (the first setup of this project, archived), Autodesk's own
packages are installed under Wine. The steps by hand:

```bash
# IMAGE = the unpacked "Browser download" (folder with Setup.exe, manifest/, x64/ ...)
python3 scripts/odis-plan.py "$IMAGE"                        # what will be installed, in which order
python3 scripts/install-from-image.py "$IMAGE"               # into ~/.wine-invtest (test prefix)
INV_PREFIX=~/.wine-invtest bash scripts/finish-install.sh   # DXVK, WebView2, isolation, ...
INV_PREFIX=~/.wine-invtest bash scripts/launch-inventor.sh  # first start: Autodesk login in the browser
```

How it works: the image's manifests (`manifest/app.inventor.xml`, `pkg.*.xml`)
list every package with its file, silent-install parameters and dependencies.
`scripts/lib/odis.py` walks them in Autodesk's order; `install-from-image.py`
runs MSIs with `msiexec /qn`, EXEs with their silent switches, and unpacks
ZIP/7Z/ADIX archives (ADIX = MSIX-style, `VFS\<folder>\...` plus a
`Registry.dat` hive that `scripts/lib/regf.py` converts to .reg). Telemetry,
Genuine Service, Autodesk Access and the ODIS installer are skipped.

What had to be worked around (all handled by the scripts):

| Problem | Cause | Fix |
|---|---|---|
| AdskLicensing installer exits 84 | the service starts but never reports "running" to Wine's service manager (1053) | accept it, write the skipped `version.ini` and `Current`/`CurrentSDK` links |
| `Inventor.msi`: LaunchConditions 1603 | "needs to be run from Setup.exe" | `ADSK_ODIS_SETUP=1` |
| `Inventor.msi`: licIsSvcUpgraded 1603 | its licensing actions need the running service | run `AdskLicensingService.exe` as a plain process during MSI steps |
| Shared Components not installed | nested bundle; `%ASC_BASE_PATH%` defined by the outer package | nested plan inherits the outer properties |
| `Current?` folders | Wine stores Autodesk's junctions in a form Linux can't follow | replaced by relative symlinks (`cfg_current_link`) |
| Login never returns to Inventor | `adskidmgr://` callback went to the default prefix | `launch-inventor.sh` records the running prefix for the callback |
| "Failed to initialize a component for accessing AutoCAD files. Error 82" | no `RealDWGSettings.xml` in the profile | `finish-install.sh` writes it |

### Updates (e.g. 2026.4)

```bash
python3 scripts/install-from-image.py Inventor_2026.4_Update.exe   # the .exe from Autodesk, unpacked with 7z
INV_PREFIX=~/.wine-invtest bash scripts/finish-install.sh
```

| Problem | Cause | Fix |
|---|---|---|
| update's `setup.xml` not recognised | a downloaded update's Bundle manifest is `setup.xml` | `odis.bundle_manifest()` |
| PatchFiles 1603 on `senddmp.exe` | finish-install.sh had renamed it | moved-aside files are put back before an update |
| PatchFiles 1603 on the first delta | Wine's `mspatcha`: "interleaved LZXD decompression is not supported" for old files larger than the 8 MB window (22 files in 2026.4) | `patches/mspatcha-pa19-32bit-and-large-files.patch` (`build-wine-dll.sh mspatcha --install`): only the first window-size bytes of the old file are the reference - found black-box against Windows' results, output byte-identical |
| PatchFiles 1603 on .NET assemblies | "special processing of 32-bit executables not implemented" (44 files in 2026.4) | same patch: Wine MR 3870 (Aidan Khoury, 2023, never merged) ported to 11.19 |
| 2026.4 `Inventor.exe` dies at start (0xc06d007f) | Wine `msi` dropped the 570 Patch rows whose header is in `MsiPatchHeaders` (NULL `Header` stream) - their files stayed at 2026.0 | `patches/msi-transform-null-stream.patch` (`build-wine-dll.sh msi --install`) |
| files skipped even so | Wine's MsiApplyPatch doesn't reinstall the patched features | `REINSTALL=ALL REINSTALLMODE=omus` |
| a failed patch leaves the product unregistered (1605) | Wine's rollback | keep a copy of the prefix before updating |

Result: 2026.4 installed from Autodesk's packages differs from the Windows
install only in Inventor.ini/InvRO.ini and the optional Electrical add-in
(31 lines of `rsync` diff), with no Windows DLLs in the prefix. Verified:
the updated prefix starts, signs in and models (extrude, hole, circular
pattern) as 2026.4.

Content Center libraries: the install image has them as a second
application (`manifest/app.dclibrary.xml`, `Content/DCLibrary/DCLibrary64.msi`,
~12.7 GB installed). `install-from-image.py` installs them with Inventor
(`--no-content` leaves them out; `--app dclibrary` adds them to an existing
prefix). They land in `C:\ProgramData\Autodesk\Inventor 2026\Content Center\Libraries`
and Inventor's Default project picks them up - no configuration needed.

Still open: fonts without a Windows partition,
one-command/GUI installer, a bundled patched Wine.

## Inventor 2027: unpacked image without a year, the 2027.2 Update (issue #6)

**Symptom (issue #6):** the reporter gave the installer an already unpacked
Inventor 2027 image in a folder called `Inventor` (no year in any file name).
The installer took it for 2026, Autodesk's packages put Inventor 2027 into
`~/.wine-inventor2026`, and the prefix setup stopped at 84 % with
`ERROR no Inventor in .../Inventor 2026 - run install-from-image.py first`.

**Cause:** `install.sh` and the GTK installer read the release only from the
download names (`Inventor_Professional_2027_..._db_002_002.7z`,
`Inventor_2027.2_Update.exe`). An unpacked image has no such name, so the
default 2026 was used. Nothing checked afterwards that the image and the
prefix belong to the same release.

**Fix (e171b0f):** `odis.release_of()` also reads the release from the image's
own ODIS manifests (the Inventor package's display name, else its build
number: 31.x = 2027). `install.sh` restarts itself for that release while
nothing is installed yet, or - if `INV_YEAR` was given and does not match -
stops before anything goes into the prefix and names the `INV_YEAR` to use.
`finish-install.sh` names the release a prefix really holds instead of just
"no Inventor". A copied `install-from-image.py` outside the project says so
instead of `No module named 'regf'`. Tests: `tests/test_image_release.py`
(synthetic manifests only).

**How it was tested (2026-11-03):** a clean Ubuntu 26.04 VM (GNOME, Wayland,
llvmpipe - no GPU), the README layout `~/Downloads/Inventor/` with the two
`..._db_...` files and `Inventor_2027.2_Update.exe`:

```bash
# release of a download folder and of an unpacked image (no install)
7z x -o"$HOME/Downloads/InvImage" ~/Downloads/Inventor/*_db_002_002.7z
python3 -I -c 'import sys; sys.path.insert(0, "scripts/lib"); import odis; [print(a, "->", odis.release_of(a)) for a in sys.argv[1:]]' ~/Downloads/Inventor ~/Downloads/InvImage
#   both -> 2027
# a wrong release is refused before anything is installed
export INV_YEAR=2026
bash scripts/install.sh --prefix "$HOME/.wine-inv6-stoptest" --no-desktop ~/Downloads/InvImage
unset INV_YEAR
#   [4/8] ERROR the download is Inventor 2027, but this run installs Inventor 2026 into ... - start again with INV_YEAR=2027
#   the test prefix has no Program Files/Autodesk
# then the GUI with ~/Downloads/Inventor: Inventor 2027 into ~/.wine-inventor2027,
# 28/28 packages, Update 19/19, prefix setup 13/13, launcher entry
```

Inventor 2027.2 then started, signed in, made a part (Extrude, Hole, Circular
Pattern) and an assembly with Content Center parts. On the maintainer's Arch
machine an existing 2027 prefix was updated to 2027.2 the same way (GUI, only
the Update selected → "Repair"); About shows build 334, release 2027.2.

**Found on the way and fixed:**

| Problem | Cause | Fix |
|---|---|---|
| 2027.2 Update stops at step 5: `no usable installLocation ('%ALLUSERSPROFILE%\Autodesk\Inventor 2027\Addins\Assistant\31.20.33400') for InvMCP` | the new ZIP package "Inventor MCP Server 2027" installs below `%ALLUSERSPROFILE%`, a variable `install-from-image.py` did not know | `%ALLUSERSPROFILE%` = `C:\ProgramData` (Windows 10 and Wine) - fc71893, with a test |
| `uninstall.sh --yes --desktop --prefix` kept `~/.wine-inventor2027` and its menu entry, without a word | with no `INV_YEAR` / `config.env` prefix, `common.sh` assumes 2026; with both releases installed it removed 2026 without asking | for `--prefix` and `--desktop` it takes the only installed release, asks when there are several, says when nothing is found - ba99c6a, checked with fake prefixes in a temporary `HOME` |
| "Ask Autodesk Assistant" panel drawn wrongly | `Autodesk.AssistantAddin.Inventor.addin` (already in `Bin\Addins` before 2027.2) shows its panel since 2027.2 | off by default (`INV_DEFAULT_DISABLED_ADDINS`, `notes/disabled-addins.md`) - 2915840 |
| GUI: the whole message on the Done page shown selected; no way back to the first page | the selectable text got the keyboard focus first | the main button gets the focus; "Back to the start" builds the pages anew (abdb64c and the two before it) |

All other `%VARIABLES%` in the 2027.2 Update's `installLocation`s were already
known or defined by their own manifest (checked with
`grep -rohE 'installLocation="[^"]*%[^"]*"' <unpacked update> --include='*.xml'`).

**Disk space, measured:** Inventor 2027.2 with Content Center: prefix
18.2-20 GB (Content Center 7.4 GB of it), unpacked downloads in
`~/.cache/inventor-on-linux` 10.4 GB (kept after the installation; the GUI's
Uninstall page removes them). The installation needs about 30 GB; the checks
in `install.sh` (warns below 40 GB) and the GUI (refuses below 40 GB) are
stricter than needed and say different things - still to be aligned.

**Still open:**
- the 2027.2 Update also installs DWG TrueView 2027 (`Program Files\Autodesk\AutoCAD 2027`)
  into the prefix; Inventor runs with it, not tested yet, kept for now;
- `--skip-packages` on a fresh system stops only in step 3 at a missing `curl` -
  step 1 should say so;
- in the VM the New dialog showed generic icons without previews, on the
  Arch machine it shows Inventor's icons and previews - not looked into yet;
- Vault 2026 client/add-in: not tried by anyone yet.

**Wine bug report:** none - these are installer bugs of this project, not Wine.

**Level:** installer changes, not Wine patches: unit tests
(`python3 -m unittest discover -s tests`, 21 OK), fake-prefix tests for
`uninstall.sh`, a full installation in a clean Ubuntu VM and an update on Arch.

## Hyprland

Wine runs through **XWayland** (the prefix pins Wine's X11 driver). Make sure
XWayland is enabled (it is by default) and `DISPLAY` is set in your session.

### HiDPI / fractional scaling

On 2026-11-10, NixOS + Hyprland already had `force_zero_scaling=true`, but
Inventor 2027's ribbon and status text looked jagged while the Home WebView
text looked smooth. The prefix had `FontSmoothing="2"`,
`FontSmoothingType=1` (grayscale), RGB orientation (`1`), and 120 DPI.
A local experiment changed only the smoothing type to `2` (ClearType), using
the packaged Wine inside the launcher's composed prefix before starting
Inventor:

```bash
wine reg query 'HKCU\Control Panel\Desktop' /v FontSmoothingType
wine reg add 'HKCU\Control Panel\Desktop' /v FontSmoothingType /t REG_DWORD /d 2 /f
```

These commands require the package's Wine and active composed `WINEPREFIX`;
do not use a system Wine or assume the source installer's prefix location.
Restore `/d 1` to undo this experiment. The live registry query confirmed the
change from `1` to `2`; the user reported no visible improvement. No default
package setting or Wine patch was changed.

Follow-up: a synthetic GDI probe run inside Inventor's actual user and mount
namespaces confirmed smoothing type `2`, but zero intermediate pixels in small
Tahoma text. Wine's `+font` trace reported `aa disabled by GASP` from
`freetype_get_aa_flags()` in `dlls/win32u/freetype.c`. Segoe UI and Noto Sans
rendered with intermediate pixels in the same DIB test. This user had Windows
fonts available from a mounted Windows installation; the package's free-family
replacements do not override an already available real family. A local
`HKLM\Software\Microsoft\Windows NT\CurrentVersion\FontSubstitutes` string
`Tahoma=Segoe UI`, followed by restart, changed system menu/status fonts to
Segoe UI. Their probe output then had intermediate pixels; explicit Tahoma
requests remained unsmoothed. The user confirmed that the change looked good.
The Nix launcher now checks real host/prefix font families and applies this
mapping only when Segoe UI is available. It removes that mapping if the family
disappears and preserves substitutions to other families. No fonts are added
to the package. Local rollback is to delete that value and restart; the launcher
will restore it if Segoe UI is still available. Other launchers are unchanged.
See [the probe and commands](wine-repro/win32u-font-smoothing/README.md).

With monitor scale > 1, XWayland apps are upscaled and look blurry. Two options:

1. Let Hyprland not scale XWayland and make Wine scale itself:

   ```ini
   # hyprland.conf
   xwayland {
       force_zero_scaling = true
   }
   ```

   ```bash
   # DPI inside Wine: 96 = 100 %, 144 = 150 %, 192 = 200 %
   WINEPREFIX=~/.wine-inventor2026 wine reg add 'HKCU\Control Panel\Desktop' \
       /v LogPixels /t REG_DWORD /d 144 /f
   ```

2. Keep the default (blurry but correctly sized). Fine on scale 1.

Inventor's own UI scaling under Wine DPI changes is untested - please report
what works.

### Native Wayland summary: not ready for Inventor (2026-10-26)

Native Wayland does not work yet for Inventor, especially its embedded
WebView2 screens. The draft bridge helped render Home, but was terribly slow
and glitchy; fractional-scale text remained blurry. Use X11/XWayland while
waiting for upstream support. See the [reproducer and investigation](wine-repro/winewayland-cross-process-gdi/README.md)
for screenshots, diagnosis, patch limitations, validation and tracked issues,
including [Wine #58921](https://bugs.winehq.org/show_bug.cgi?id=58921).

Retested 2026-11-07 on a copy of the 2027 prefix with Wine's Wayland driver:
GPU ray tracing worked, but the WebView2 pages stayed broken, dialogs were
abnormal, dimension values could not be typed and Restore Down/maximise was
not right. The X11 driver through XWayland stays the supported path.

### Window rules

Ready-made rules: `config/hyprland-inventor.lua` (Hyprland 0.55+, Lua config)
and `config/hyprland-inventor.conf` (0.53/0.54, hyprlang). They:

- keep the Autodesk windows fully opaque (a desktop with `inactive_opacity`
  below 1 otherwise shows the blurred wallpaper through Inventor whenever a
  tool dialog takes the focus);
- turn off Hyprland's border, shadow, rounding, blur and **animations** for the
  Autodesk windows. Inventor's WPF panels draw their own frame and shadow
  (separate shadow windows); Hyprland decorating those gives doubled grey
  outlines around the property panels, and the move animation makes windows
  that follow the cursor (coordinate input next to the sketch cursor) lag;
- float dialogs and panels, tile the main window (`Autodesk Inventor...` title).

Classes seen with `hyprctl clients`: `inventor.exe`, `adsklicensingagent.exe`,
`adskidentitymanager.exe`. Wine's menus and tooltips are override-redirect
X11 windows that Hyprland does not manage, so no rule touches them.

### Browser login (adskidmgr://)

The SSO login opens your default browser. After login, the browser hands the
`adskidmgr://...` link to `scripts/adskidmgr-callback.sh` (registered by
`install-desktop-integration.sh`). Check:

```bash
xdg-mime query default x-scheme-handler/adskidmgr   # -> adskidmgr-handler.desktop
xdg-settings get default-web-browser
```

Firefox asks once which application should open the link - choose
"Autodesk Identity Manager" and tick "always".

## OGSFactory.dll is not modified

An earlier version of this project patched bytes in Autodesk's OGSFactory.dll
to stop a crash of the 3D viewport. The crash came from Wine: Inventor asks WMI
for `Win32_TimeZone`, Wine had no such class and returned an empty result,
which Inventor then used as an object. `patches/wbemprox-timezone.patch` adds
the class to Wine, and Inventor runs with its files exactly as Autodesk ships
them (verified 2026-10-15; the darker materials of the patched DLL are gone too).
No Autodesk file is modified by these scripts.

## DXVK and isolation

### DXVK without the AUR

`rebuild-prefix.sh` downloads `dxvk-2.7.1.tar.gz` from the official DXVK GitHub
releases (cached in `downloads/`) and refuses it unless its SHA-256 is
`d85ce7c7...13ce87` - the hash winetricks pins for its `dxvk2071` verb, and the
version the original project was tested with. The DLLs are copied into the
prefix only; nothing is installed system-wide and nothing runs as root.

To use a system package instead: `INV_DXVK=system` (needs `setup_dxvk`, e.g.
AUR `dxvk-bin`). Another version: set both `DXVK_VER` and `DXVK_SHA256`.

### What the isolation does

By default Wine gives Windows programs drive `Z:` = `/` and links the Windows
Desktop/Documents/Downloads/... folders straight into your `$HOME`. With
isolation on (default, `INV_SANDBOX=1`):

| Drive / folder | Points to |
|---|---|
| `C:` | `~/.wine-inventor2026/drive_c` (the prefix) |
| `D:` | `~/Inventor` - your projects and exports (`INV_DATA_DIR`) |
| `T:` `U:` ... | font folders only (`/usr/share/fonts`, `~/.local/share/fonts`) and Wine's read-only data folder `/usr/share/wine` (its own fonts are found through it) |
| `Z:`, other letters, raw devices | removed |
| Desktop, Documents, Downloads, ... | real folders inside the prefix |
| "/" entry in file dialogs | removed (registry) |

It is applied at the end of `rebuild-prefix.sh` and again on every launch
(after any `wineboot`), so a Wine update can't silently bring `Z:` back. Wine's
automatic prefix update is turned off; `launch-inventor.sh` runs it itself when
`wine --version` changes and re-applies the isolation.

**Why the font drives:** Wine gives every Linux font a Windows path through
some drive letter. With no drive covering `/usr/share/fonts`, the path becomes
`\\?\unix\usr\share\fonts\...`; WPF passes it to `new Uri(...)` and Inventor dies
while drawing the ribbon (`System.UriFormatException` in
`MS.Internal.FontCache.Util.CombineUriWithFaceIndex`). Found on the first run
with isolation; the original setup never hit it because it had `Z:` = `/`.

Nothing else in the setup depends on `Z:`: the registry import and the WebView2
installer are copied to `C:\windows\temp` first.

**Limits - read this.** This controls what Windows programs *see*, not what
they *can* do. Wine is not a sandbox: processes run as your Linux user and a
program that wants to can still open Unix paths directly (Wine supports
`\\?\unix\...` paths). It protects against accidents - file dialogs, add-ins
scanning drives, default save locations in `$HOME` - not against malicious
code. A real boundary needs a namespace sandbox such as `bubblewrap`, which is
harder here because the browser login (`adskidmgr://` handler) and the
wineserver socket must cross it. Not done yet.

## Windows fonts are required

With no Windows fonts in the prefix, WPF's font fallback finds no font for some
characters and terminates Inventor on purpose (`Environment.FailFast
"Unrecoverable system error"` in `TypefaceMap.MapUnresolvedCharacters`, first seen
when the App Home page is drawn). `scripts/windows-fonts.sh` copies the
TrueType/OpenType fonts from your own Windows installation into
`C:\windows\Fonts` and registers them under
`HKLM\...\Windows NT\CurrentVersion\Fonts` - DirectWrite (and so WPF) only sees
registered fonts. `rebuild-prefix.sh` runs it automatically.

Without Windows: `scripts/linux-fonts.sh` (default in `finish-install.sh`;
`INV_FONTS=windows` for the copy above) copies Liberation, Noto and DejaVu
(`sudo pacman -S --needed ttf-liberation noto-fonts ttf-dejavu`) into
`C:\windows\Fonts`, registers them, and maps the Windows family names
through `HKCU\Software\Wine\Fonts\Replacements` (read by both dwrite and
gdi32): Arial -> Liberation Sans, Times New Roman -> Liberation Serif,
Courier New -> Liberation Mono (metric-compatible), Segoe UI & co. -> Noto
Sans / DejaVu Sans. Tested with the 313 Windows fonts moved out of the
prefix (`--remove-windows-fonts`): Inventor starts, no FailFast.

## Default.ipj is required (materials, appearances, shading)

The active project file decides which material and appearance libraries
Inventor loads. `Default.ipj` sits at the top level of
`C:\Users\Public\Documents\Autodesk\Inventor 2026\`, not in one of its
subfolders, so copying only `Design Data`/`Templates`/... leaves the prefix
without a project. Symptoms:

- material and appearance lists are empty,
- parts are drawn as one flat unlit grey; Shaded and Realistic look the same,
- iLogic fails with `E_FAIL` on `get_ActiveDesignProject`.

It looks like a graphics bug and is not one: Quality/Performance, tone mapping,
feature level 10_1 and DXVK's "Class linkage not supported" warning were all
ruled out first (that warning appears whenever a program passes a class-linkage
object, which the D3D Effects framework always does). `rebuild-prefix.sh` now
copies the whole folder (~380 MB) and Inventor picks `Default.ipj` up by itself.
For an existing prefix:

```bash
rsync -rlt "/mnt/windows/Users/Public/Documents/Autodesk/Inventor 2026/" \
  "$HOME/.wine-inventor2026/drive_c/users/Public/Documents/Autodesk/Inventor 2026/"
```

## WebView2: white licensing window, empty Home tab

The licensing dialog (`AdskLicensingAgent.exe`, e.g. "Access expiring soon")
and Inventor's Home tab are WebView2 pages. With runtime 155 they stayed white:
the WebView2 GPU process hit a `CHECK` three times and the browser quit with
`GPU process isn't usable. Goodbye.` (read from the Crashpad dumps with
`scripts/minidump-info.py`). Inventor waits for the licensing dialog, so the
UI was blocked until the white window was closed by hand.

What fixed it (`webview2_reg` in `lib/common.sh`, run by `rebuild-prefix.sh`;
`scripts/webview2-fix.sh` for an existing prefix, `--revert` to undo):

- `msedgewebview2.exe` reported as **Windows 7** (Wine AppDefaults) - the key
  change, same trick the Lutris BYOND installer uses;
- wined3d instead of DXVK for `msedgewebview2.exe` only (wined3d turns a WARP
  device request into a hardware device, DXVK refuses WARP);
- `--no-sandbox --enable-unsafe-swiftshader --use-angle=swiftshader` through the
  **HKLM** policy `Software\Policies\Microsoft\Edge\WebView2\AdditionalBrowserArguments`.
  The `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` environment variable does not reach
  these browsers; HKCU did not work either.

Background: [WebView2Feedback #5720](https://github.com/MicrosoftEdge/WebView2Feedback/issues/5720).
Not yet tested which of the three are strictly needed.

The Home tab then showed `ERR_FILE_NOT_FOUND`: it is
`file:///C:/ProgramData/Autodesk/Inventor 2026/WebBrowser/index.html`, so
`rebuild-prefix.sh` now copies `ProgramData\Autodesk\Inventor <year>` (without
Content Center unless `--content-center`).

To see what a WebView2 page loads: add `--remote-debugging-port=9222` to the
policy value and `curl -s http://127.0.0.1:9222/json` (localhost only).

## File icons and thumbnails

Inventor registers its file types per user (`UsrClass.dat`), so the
NTUSER.DAT export misses them. `scripts/import-file-types.sh` (also run by
`rebuild-prefix.sh`) imports the icons (`DefaultIcon` -> `SrvRes.dll`) and the
shell-extension classes for thumbnails; shell verbs with Windows 8.3 paths are
skipped. Inventor keeps the imported icon on its next start.

The big icons in New/Open and the preview pane still stayed empty: Inventor asks
for them through `IShellItemImageFactory::GetImage`, which in Wine is a stub that
returns an empty 1x1 bitmap. `patches/shell32-getimage.patch` implements it -
the registered thumbnail handler (`IThumbnailProvider`, initialised with a
stream or the file path) and the file's icon at the requested size as fallback -
with a Wine test. Build and install like the wbemprox patch:

```bash
bash scripts/build-wine-dll.sh shell32 --install --hook
bash scripts/build-wine-dll.sh shell32 --test      # Wine's shell32 shlfolder tests
bash scripts/build-wine-dll.sh shell32 --restore   # back to the original
```

### Open/Place: click and double-click

Clicking a file did not put its name into "File name", double-click did
nothing; only typing the name worked. The dialog asks the shell view for the
selection, and Wine's `IFolderView2::GetSelection`/`GetSelectedItem`/
`GetSelectionState` were stubs while `IFolderView::Items`/`ItemCount` ignored
`SVGIO_SELECTION`. `patches/shell32-folderview-selection.patch` implements them;
`build-wine-dll.sh shell32 --install` applies it together with the GetImage
patch. Confirmed: click fills the name, double-click opens files and folders.
(Still needs a Wine test checked on Windows - level L1 in `AGENTS.md`.)

### Open: big icons in the New dialog

The New dialog showed Inventor's old "I" icons. A `+shell` trace: the dialog
asks `SHGetFileInfoW(template, SHGFI_SYSICONINDEX | SHGFI_ICON)`; Wine's
shell32 reads `HKCR\Inventor.PartDocument\DefaultIcon` = `Inventor.exe,4`
- the value the installer wrote to HKLM. Inventor registers the real icons
per user on start (`HKCU\Software\Classes\...\DefaultIcon` =
`SrvRes.dll,N`), which on Windows win over HKLM in HKEY_CLASSES_ROOT; Wine's
shell does not see them. `launch-inventor.sh` now copies these per-user
DefaultIcon values (only those mentioning Autodesk/Inventor) and the class of
Inventor's extensions (`.idw` had none in HKLM) to HKLM before each start
(`scripts/lib/sync-class-icons.py`), so they show from the second start on.
First test: only the `.dwg` icons changed - Inventor writes the old
`Inventor.exe,N` icons to HKCR (HKLM in Wine) again while it starts. So the
launcher keeps checking while Inventor starts (live `reg query`/`reg add`,
`INV_ICON_SYNC_SECONDS`, checks every few seconds for 3 minutes). Confirmed: part, assembly, drawing (.idw/.dwg) and
presentation templates show Inventor's own icons in New. A cleaner fix would
be per-user classes winning in Wine's HKEY_CLASSES_ROOT, as on Windows.

## Design Accelerator (Shaft, gears, ...): "Failed to create shaft"

Two separate causes, both needed:

1. **Wine bug, oleaut32** (`patches/oleaut32-typedesc-*.patch`): in an MSFT
   typelib the pointee of a `VT_PTR` typedesc is an offset into the typedesc
   table stored in two 16-bit words. Wine used only the low word as a signed
   value; Inventor's API typelib is larger than 32 KB, so the offset turned
   negative and Wine read memory before the table. Visible as
   `ITypeInfo_fnInvoke failed to convert param 5 to vt(invalid ...)` for
   `ApplicationAddInSite::CreateDocumentSubTypeHandler`; Design Accelerator's
   add-in could not register itself. Fix: use the full 32-bit offset, with a
   range check.
2. **Missing files**: the generators open templates from
   `Inventor 2026\Design Accelerator\models\` (`Documents.Add(...FD-Shaftmm.ipt)`
   returned `E_INVALIDARG`). `rebuild-prefix.sh` now copies the whole install
   folder instead of only `Bin`, `Configuration`, `Preferences`.

```bash
bash scripts/build-wine-dll.sh oleaut32 --install --hook
```

How it was found - tools that are useful for any "Unexpected failure" message:

- `scripts/dotnet-exceptions.sh`: .NET exceptions Inventor catches itself, with
  the catching method (runtime EventPipe tracing, nothing to install);
- `scripts/build-wine-dll.sh oleaut32 --diag --install`: logs every failing
  late-bound (IDispatch) call into Inventor's API with method name and
  arguments. Build without `--diag` afterwards; that removes it again.

## Content Center

Libraries (`*.idcl`, SQLite) come from `ProgramData\Autodesk\Inventor 2026\Content
Center\Libraries` (`rebuild-prefix.sh --content-center`, ~7 GB). They stayed
empty and a refresh crashed Inventor: before opening a library,
`Connectivity.Core.Util.IOUtil.HasWritePermission` walks the file's ACL and calls
`SecurityIdentifier.IsAccountSid()`, which relies on `GetWindowsAccountDomainSid`
failing with `ERROR_NON_ACCOUNT_SID` for well-known SIDs. Wine returned
`ERROR_INVALID_SID`, .NET threw `Win32Exception: Invalid SID`.
`patches/kernelbase-account-domain-sid.patch` (with a Wine test) fixes it:

```bash
bash scripts/build-wine-dll.sh kernelbase --install --hook
```

Confirmed: Place from Content Center lists and places parts (ISO screws).

## Frame Generator: Insert Frame creates nothing

Insert Frame showed the preview and the naming dialogs, then created only an
empty `Frame` folder - no members, no frame sub-assembly, no message. With
`WINEDEBUG=+seh` the step ends in
`fixme:msxml:domdoc_importNode ... stub` followed at once by a C++ `_com_error`:
Frame Generator copies XML between documents with
`IXMLDOMDocument3::importNode`, which Wine's msxml3 did not implement
(`E_NOTIMPL`). `patches/msxml3-domdoc-importnode.patch` implements it (a clone
of the node that belongs to the importing document and has no parent), with a
Wine test. In this project's Wine since `wine-11.20-3`.

## Drawings: editing dimension text

Editing a dimension's text aborted Inventor with
`Assertion failed ... riched20/caret.c line 232: ~para->nFlags & MEPF_REWRAP`:
the RichEdit caret was placed before the text had been rewrapped.
`patches/riched20-caret-rewrap.patch` rewraps at that point instead
(`build-wine-dll.sh riched20 --install --hook`). Confirmed working.

Inserting a symbol (diameter, GD&T, ...) made the whole text black until it
was selected. The log shows `TextFont_Reset reset mode 4 not supported`.
Mode 4 is `tomApplyTmp`, temporary formatting: a `+richedit` trace shows that
Inventor's spell checker (AdSpellEng.dll) uses it for the red wavy underline
under "misspelled" words (`SetUnderline(0xff0000ff)`, `SetUnderline(tomWave)`).
Wine ignored the mode, and the `Reset(tomApplyNow)` that followed wrote the
font object's stale cached properties - colours included - back into the
text. `patches/riched20-textfont-applytmp.patch` drops temporary formatting
(no spell-check underline) and skips that write-back. Confirmed: no more black
text.

GD&T symbols other than Ø ° ± turned into letters (`gajic...`) when the
dimension text was edited a second time, and were saved as letters. They are
letters in the AIGDT font. The CHARFORMAT trace
(`patches/debug/riched20-charformat-trace.patch`) showed the load: Inventor
inserts the symbol letters with AIGDT, then sets its normal font with
`EM_SETCHARFORMAT(SCF_SELECTION | SCF_WORD)` at the empty insertion point right
after them. Windows formats the word only when the insertion point is *inside*
a word; Wine took the word before the cursor and turned the symbols into
Tahoma. `patches/riched20-scf-word-insertion-point.patch` applies SCF_WORD to
an empty selection only inside a word. Confirmed: symbols survive repeated
edits.

The symbol palette next to the text is a toolbar (`CCS_VERT | TBSTYLE_WRAPABLE`,
58 buttons in 4 separator groups) that Inventor sizes with `TB_SETROWS(12)`.
Wine's TB_SETROWS set the wrap points and then wrapped again by the current
(still tiny) window width, returning a one-column rectangle; Inventor sized
the palette to it. `patches/comctl32-toolbar-setrows-wrapable.patch` (built
into `comctl32` and `comctl32_v6` - Inventor loads the version-6 controls)
keeps the TB_SETROWS wrap points: the palette is a grid now. Current version:
TB_SETROWS picks the fewest buttons per row with which the groups (between
separators, each starting on a new row; separators not counted) fit into the
requested rows - 47 buttons in 5 groups into 12 rows gives 5 columns, as on
Windows - and later resizes and button changes (Inventor replaces buttons one
by one after TB_SETROWS) keep that number of columns. Confirmed: 5 columns
and the groups as on Windows. Also: separator lines span the toolbar width,
and `patches/comctl32-toolbar-padding-height.patch` takes the button height
padding from TB_SETPADDING like the width (Inventor sets 0: rows as tall as
the 16-pixel symbols instead of 22, so the palette fits without a scroll
bar). Confirmed: the palette looks like on Windows.

A freeze of the same dialog with `virtual_setup_exception stack overflow` was
seen once and is not understood yet.

## Sketch: an edited dimension shows only after the mouse moves

After typing a new dimension value and pressing Enter the sketch kept the old
value until the mouse moved or a key was pressed (on Windows: immediately).
Traces (`+msg,+win`) showed Inventor waiting in `WaitMessage` with nothing
pending, and that its view redraws on a mouse move over it - but the redraw
it does at once still has the old value (Ctrl+Z showed the same: every input
displays the state from before that input). Windows sends the window under
the cursor a mouse move when a window is shown or hidden; Wine only did when
a visible window moved. `patches/server-mousemove-on-show-hide.patch`
(wineserver, `build-wine-dll.sh server --install`, close all Wine programs
first) sends one 100 ms after a window is shown/hidden, one per burst
(`WINE_SHOWHIDE_MOUSEMOVE_MS`, 0 = off). Sent at once it came too early.
Confirmed working. The delay is empirical - for level L1 (and a Wine bug
report), measure when Windows delivers that mouse move.

## Sketch: black rectangles around the sketch input boxes (fixed)

While drawing, the length/angle input boxes sit on a shared window that should
be transparent; under the X11 driver it is drawn black. Wine's Wayland driver
(`HKCU\Software\Wine\Drivers` `Graphics=wayland`) was tried: the Home page
(WebView2, a window embedded from another process) stays empty there, so it is
not usable yet. Back to `x11`; the transparency has to be fixed in winex11.

Cause (trace `+win`): the boxes are child Edits of one `HUDFieldDialog`
popup, resized to span both boxes and clipped with `SetWindowRgn`. winex11
turns the region into an X bounding shape, which Xwayland/Wayland
compositors ignore when drawing - hence black.
`patches/winex11-shape-alpha-xwayland.patch` (`build-wine-dll.sh winex11
--install`, close all Wine programs first): under Xwayland such a window
gets an ARGB visual, the pixels outside the shape are written transparent,
and the shape is set as the *input* shape only - as a bounding shape it
clips those transparent pixels out of the window contents (that is why the
first working attempt still showed black). Limited to owned dialog popups
(`#32770`, `WS_POPUP`, no caption, not layered): doing it for every window
with a region (main frame, WebView2) mixed 32- and 24-bit drawables
(`BadMatch` in `X_CopyArea`/`RenderCreatePicture`, Inventor exited) and
broke New/Open on the Home page. The visual is switched while the dialog is
still hidden (the HUD sets its region before showing it).
`WINE_X11_SHAPE_ALPHA=0` turns it off, `=2` also switches visible windows;
`+x11drv` logs every window that gets a region. `--restore` puts the
original driver back. Confirmed: no black boxes, New/Open work.

## Crash "XI_BadDevice ... X_GetDeviceButtonMapping" (Hole command)

Seen on a laptop (Hyprland, Xwayland): Inventor closes when a command that
uses raw mouse input starts (Hole), and the log ends with

```
X Error of failed request:  XI_BadDevice (invalid Device parameter)
  Minor opcode of failed request:  28 (X_GetDeviceButtonMapping)
```

Wine's X11 driver looks up the button mapping of the device a raw mouse event
came from with XInput 1 calls and no X error handler; Xwayland reports
devices that XInput 1 cannot query, and an unhandled X error ends the
process. `patches/winex11-xinput-bad-device.patch` catches the error and uses
the identity button mapping for such a device (part of the `winex11` build:
`bash scripts/build-wine-dll.sh winex11 --install --hook`).

## Status bar: white instead of dark

Inventor's status bar (bottom strip with "Ready", coordinates, "Fully
Constrained") is dark on Windows and white in Wine, with Inventor's light text
invisible on it. A `+statusbar,+uxtheme` trace: it is a normal
`msctls_statusbar32`, themed, with owner-drawn parts (`SB_SETTEXT` with
`SBT_OWNERDRAW`); no `SB_SETBKCOLOR`, no dark theme. The status bar never sees
`WM_ERASEBKGND` - Inventor handles it and paints the strip dark - but Wine's
status bar paints its whole background again in `WM_PAINT` (and its own
invalidations do not ask for an erase), and the light theme's opaque pane
bitmap under every part. `patches/comctl32-statusbar-erase-background.patch`:
the background is painted in `WM_ERASEBKGND`, `WM_PAINT` paints it only if
nobody erased (`ps.fErase`), invalidations ask for an erase, and owner-drawn
parts get no theme pane. Built into `comctl32` and `comctl32_v6`. Confirmed:
the status bar is dark with "Ready", coordinates and "Fully Constrained"
as on Windows. Later findings (2026-11-07/08): the patch matches Windows for
Inventor's themed status bar, and the old text that stays after GPU ray
tracing has another cause - see "Status bar: old text stays after GPU ray
tracing". A v2 in winum corrects the patch for unthemed status bars.

## Open: crash while browsing (fixed in wine-11.20-4)

Switching folders quickly in Open (2026 and 2027's new dialog) ended Inventor
with `Fatal error. 0xC0000005` from .NET. Found with `WINEDEBUG=+seh,+loaddll`:
the preview code raises NullReferenceExceptions (normal, .NET handles them);
one of them happens in a virtual stub dispatch stub, and .NET's
`AdjustContextForVirtualStub` asks for the CET shadow-stack pointer
(`LocateXStateFeature(context, XSTATE_CET_U)`) on a CONTEXT copy that keeps
`CONTEXT_XSTATE` but has no `CONTEXT_EX` behind it. On CPUs with compacted
XSAVE (Zen 3, newer Intel) Wine's `RtlLocateExtendedFeature2` read the XSAVE
header through `XState.Offset` - here stack data, a pointer to the exception
record - before checking that the feature is enabled, and faulted inside the
exception handler. Fix: return NULL for a feature that is not enabled before
the XSAVE area is touched (`patches/ntdll-locate-xstate-feature-enabled.patch`,
with a test).

## Frame Analysis: Simulate crashes the solver (fixed in wine-11.20-6)

Frame Analysis (Environments → Frame Analysis on a frame from Frame
Generator) worked up to Simulate: study, constraints, loads were fine, then
the progress window stopped at "Getting Results..." and Wine showed

```
Assertion failed!
Program: ...\Autodesk Robot Structural Analysis Engine 2026\Exe\rkernel.EXE
File: ../dlls/ole32/storage32.c   Line: 4157
Expression: "blockIndex != nextBlock"
```

`rkernel.exe` is the Robot Structural Analysis solver that Inventor starts as a
separate process. It keeps its model and results in OLE compound files
(`IStorage`/`IStream`, transacted mode, a root storage `RV6STR` with
substorages and streams such as `SCRDT`/`SCRIP`). Inventor itself keeps running;
only the solver dies. The add-in was off by default until this was fixed.

Two Wine bugs, both in `dlls/ole32/storage32.c`:

1. **No locking** (`patches/ole32-storage-thread-lock.patch`) - the cause of the
   crash. `rkernel.exe` writes into **one** compound file from **four threads at
   the same time** (seen in the `+storage` trace: four thread ids interleaved,
   all reading the same small-block depot chain). Wine's storage objects share
   per-file state - the big-block depot cache (`blockDepotCached`,
   `indexBlockDepotCached`), the next-free-block hint (`prevFreeBlock`), the
   block chain cache (`blockChainCache`) with each chain's index cache and
   tail, the small-block root chain - and nothing in ole32 serialised access to
   it. Two threads extending chains at once got the same "free" block, or read
   a depot cache half overwritten by the other thread. The symptom changes from
   run to run: `blockIndex != nextBlock` (a block chained to itself),
   `depotBlockCount < This->bigBlockDepotCount` (a block number far past the end
   of the file), `SmallBlocksToBigBlocks conversion failed: resRead =
   0x8003001e` (STG_E_READFAULT) in several threads, or a page fault in
   `BlockChainStream_GetSectorOfOffset`. On Windows the same `rkernel.exe` runs
   fine, so native ole32 copes with it. Fix: one process-wide recursive lock
   (`storage_cs`, a `CRITICAL_SECTION`) taken in a small wrapper around every
   method of the four `IStorage` vtables (`StorageImpl`, `StorageInternalImpl`,
   `TransactedSnapshotImpl`, `TransactedSharedImpl`), of `IStream`
   (`StgStreamImpl`) and of `IEnumSTATSTG`. Recursive, because storage methods
   call each other (Commit → CopyTree → stream copies, Release → Revert, ...).
   One lock for all files is simple and certainly correct; a per-file lock
   would let two files be used in parallel, but every object would need to
   find its root `StorageImpl`. The internal functions are unchanged.
2. **Truncated stream lost on commit**
   (`patches/ole32-transacted-truncate-dirty.patch`), found on the way.
   `TransactedSnapshotImpl_StreamSetSize` with size 0 drops the entry's link to
   its data in the parent (`transactedParentEntry = DIRENTRY_NULL`) but did not
   set `dirty`. `TransactedSnapshotImpl_CopyTree` decides from `dirty` /
   `stream_dirty` / "a child was copied" whether an entry needs a new copy in
   the parent; the truncated stream needed none by those rules, so it and its
   siblings kept their old parent entries - one of which the commit then
   destroyed as orphaned. The committed tree pointed at a deleted (later
   reused) directory entry: the file name appeared as an element of a
   substorage, later commits crashed in `TransactedSnapshotImpl_StreamLink`
   (`EnsureReadEntry` on garbage) or looped forever over a cycle in the tree.
   Fix: set `dirty = TRUE` in that branch. Upstream Wine (master of
   2026-09-01) has the same code.

### How it was found

Useful for any crash inside ole32's storage code:

1. **A trace of the solver only.** `WINEDEBUG="+pid,err+all,fixme-all,+storage"
   bash scripts/launch-inventor.sh`, run Simulate, then count lines per
   process to find `rkernel.exe` (Inventor itself also uses storage):
   ```bash
   LOG=$(ls -t logs/inventor-*.log | head -1)
   grep -a -o '^[0-9a-f]*:[0-9a-f]*:trace:storage' "$LOG" | cut -d: -f1 | uniq -c | tail -5
   grep -a "^<pid>:" "$LOG" | tail -1500 > ~/fa-diag.txt
   ```
   The first trace (2026-10-21) led to the stale-cache theory; the one with
   all four thread ids showed what really happens. Count threads early: `cut
   -d: -f2 file | sort | uniq -c`.
2. **An ole32.dll with debug info.** Built from the vanilla 11.20 source with
   [llvm-mingw](https://github.com/mstorsjo/llvm-mingw) (about 1 minute for
   `make dlls/ole32/all` after the tools), copied over
   `lib/wine/x86_64-windows/ole32.dll` of the bundled Wine (keep the original
   as `ole32.dll.orig`). The assertion dialog then names the source path of the
   build, which proves the DLL is loaded, and a backtrace has function names
   and lines.
3. **A backtrace while the assertion dialog is open** (do not press OK or
   Cancel - Cancel's built-in debugger output did not contain the trace):
   ```bash
   export WINEPREFIX=~/.wine-invclean
   W=~/.local/share/inventor-on-linux/wine-inventor-11.20-5-x86_64/bin
   pid=$("$W/wine" winedbg --command "info proc" 2>/dev/null | grep -i rkernel | awk '{print $1}')
   "$W/wine" winedbg --command "bt all" "0x$pid" > ~/rkernel-bt.txt 2>&1
   grep -n "ole32" ~/rkernel-bt.txt
   ```
   Result: `StorageImpl_SetNextBlockInChain` ← `BlockChainStream_Enlarge` ←
   `BlockChainStream_SetSize` - a free block equal to the chain's own tail.
4. **Reproducing without Inventor.** The programs in
   [`docs/wine-repro/ole32-storage/`](wine-repro/ole32-storage/) (see its
   README for building and running):
   - `fuzz.c` does random single-threaded operations on nested transacted
     storages and can record and replay a run; `ddmin.py` shrinks a recorded
     run. This found bug 2 (seed 26, shrunk from 1306 to 8 steps: create
     substorage, two streams over 4 KB, commit, truncate one to 0, commit,
     commit root, revert root → the substorage lists the file name). Fixed: 0
     of 300 seeds fail; unfixed: 35 of 300 crash, hang or break the tree. But
     the Frame Analysis assertion stayed - single-threaded fuzzing could not
     reproduce it.
   - `mt.c` does what the trace showed: four threads, one file, substorages
     and streams growing past the 4 KB small-block limit, commits. Unfixed
     Wine 11.20: `Assertion failed: blockIndex != nextBlock, storage32.c line
     4157` - the Frame Analysis assertion - in 6 of 6 runs. With the lock: 0
     of 6.
5. **A diagnostic build** (not kept): the self-link case was logged with the
   chain kind, depot state and callers. It never fired - the next run hit the
   other assertion instead, which is what made the "several threads" trace
   worth a look.

### Wine tests

Both patches add tests to `dlls/ole32/tests/storage32.c`:
`test_transacted_truncate` (4 variants: root or nested transacted storage,
truncated stream in the parent or in the scratch file) fails 8 times without
fix 2; `test_threads` (4 threads × 20 rounds) dies on the assertion without
fix 1. The whole `storage32` test (19102 checks), `stg_prop`, `ole2`,
`hglobalstream`, `moniker`, `propvariant` pass with both. `marshal` hangs in
a headless prefix with and without the patches (no display), unrelated.
To run them:

```bash
bash scripts/build-wine-dll.sh ole32 --test
```

### Inventor 2027

Confirmed 2026-10-22: Simulate and results work in Inventor 2027 too (its own
`Robot Structural Analysis Engine 2027`), with the same Wine build.

Open, intermittent (2027 only so far): after switching to the Frame Analysis
environment a pane stayed at the far left of the window, next to the Frame
Analysis browser, that could not be moved or closed. A second screenshot
showed what it is: the **iLogic** pane (its tabs Rules | Forms | Global
Forms at the top), with the assembly's model tree still painted below the
tabs - it stayed like that even on the Home page with no document open. So
the pane is shown but its contents are never repainted: it keeps the pixels
of the window that was there before. Probably a Wine redraw problem of a
docked pane (compare the sketch dimension and status bar sections), not a
saved layout. Workaround: View → User Interface → untick and tick *iLogic*
(the pane is destroyed and created again). Could be repeated a few times
the same day, then no longer - switching to Frame Analysis, Stress Analysis
and Dynamic Simulation all went fine. No reliable steps yet; when it shows
again, note the exact steps and take a `+win,+msg` trace.

### Still open (found by the fuzzer, not needed by Inventor)

- `Commit` on a transacted substorage whose parent was reverted dereferences
  NULL (`TransactedSnapshotImpl` uses the invalidated parent). Native ole32
  presumably returns `STG_E_REVERTED` - not checked on Windows yet.
- The fuzzer runs keep the substorages closed around a root `Revert` because
  of that.

### For a Wine bug report

The patches are not sent to Wine (AI-generated, see `patches/README.md`); the
bugs are reported in words with the public tests. The two patches are
independent and apply in either order. The lock patch is large only because of
the wrappers (generated, one per vtable method); the logic is "enter
`storage_cs` / call the original method / leave". Still to check (level L1 in
`AGENTS.md`): whether native ole32 really serialises - the `test_threads` test
should pass on Windows 10 (`rkernel.exe` suggests it does) - and whether a
per-file lock would be closer to Windows.

## Import CAD (STEP) and Property Mapping crash in 2027 (issue #10, open)

Reported by @krokosik on 2026-11-10 (NixOS, Hyprland, RTX 3060, Wine 11.20,
Inventor 2027). Not yet reproduced here; to be fixed for the next release,
after the winum release tests.

- **Symptom 1:** Assembly -> Place -> Import CAD with a STEP file (a
  Thorlabs part, PC4QR) and default options ends with "Could not import
  object". The same file imports on Windows.
- **Symptom 2:** the Property Mapping button of the import dialog opens
  Wine's crash window: page fault on write in
  `AnyCADPropertyMappingTool.exe`, in Autodesk's
  `rxapprenticeservercore` (+0x15ff9). The written address lies in the
  range where `libmono-2.0-x86_64` is loaded, and the tool's process has
  Wine Mono (`mscoree`, `libmono`, `presentationnative_cor3`) loaded: it
  runs on Wine Mono, not on the .NET Framework.
- **First hypothesis (unproven):** the import and property-mapping tools
  need the .NET Framework that the planned .NET 4.8 step of the installer
  provides (3D PDF already needed it). Check that first, before any Wine
  change.
- **Also seen in the report:** `report.sh` on NixOS found no prefix and no
  Wine ("system ()", prefix 2026 for a 2027 install, "NOT patched" for
  every DLL), so the report helper needs a look on NixOS too.

**2026-11-11, Arch, Inventor 2027, winum-11.20-1 build (Build Wine run
43022221734), a prefix with .NET Framework 4.8:** the Property Mapping
dialog opens and works (no crash), so .NET 4.8 fixes symptom 2. The import
itself still fails: Load Model reads the STEP file and shows its preview
and tree (tested with two files, one of them a simple bolt), but OK ends
with "Data Exchange Import: problems encountered ... Could not Insert
Object". Next: the same files in Inventor 2027 on Windows, to see whether
Windows inserts them; then a filtered trace of the insert step.

**2026-11-11, trace of the insert step:** Windows (Inventor 2027 in the
maintainer's VM) inserts the same files. On Linux, with a line-count marker
taken just before OK and `WINEDEBUG=err+all,fixme-all,+debugstr,warn+ole`,
the insert step on the main thread shows:

- `err:ole:com_get_class_object class {cfe9f29b-e1b6-4240-aed7-360846769314}
  not registered`, right after `RxPart.dll` is loaded. On Windows this
  class is "Microsoft APC 7.1 Object Library" (`apc71.dll`, VBA 7.1), but
  there VBA was installed by SOLIDWORKS 2026 (`InstallSource` in its
  `PreReqs\VBA`), not by Inventor: the Inventor 2027 image has no VBA
  package (not in the plan, the manifests or the files), and our installer
  skipped nothing but AGS, CER, ODIS and Access. A Windows machine with only
  Inventor would miss the class too, so this is most likely Inventor
  probing for VBA - **not the cause** (not proven: the VM has VBA).
- `RunningObjectTableImpl_GetObject Moniker unavailable (0x800401e3)` once.
- About 60 `ITypeInfo_fnInvoke invoked function failed` (0x80004005 and
  0x80070057) and some `ITypeInfo_fnGetIDsOfNames no names found`: IDispatch
  calls whose callee returned an error; which interfaces is not known yet.
- About 40 `err:dialog:EndDialog got invalid window handle`.
- No `OutputDebugString` text (`+debugstr` printed nothing).

Clean prefix with .NET Framework 4.0 + 4.8 from the installer (2026-11-11,
L4 of the .NET step): Property Mapping opens; importing the STEP file into
a part works, into an assembly it still ends with "Could not Insert
Object". So the assembly insert is what remains of this issue.

Tests in Inventor (2026-11-11): File -> Open of the STEP file works (the
part opens, but the same "Could not Insert Object" message shows). In an
assembly, Place -> Import CAD fails with both Reference Model and Convert
Model, with every Output Location (User Path, Source Path, Workspace) and
also with the assembly saved first: Load Model shows the model and its
bodies, and after OK nothing is inserted. So it is not an empty or
unwritable output path. What works and what does not: placing an existing
`.ipt` into an assembly works; Manage -> Import of the STEP file into an
open part works (the body is inserted). What fails is every import that has
to create a **new document** (File -> Open of the STEP file, Import CAD into
an assembly): the preview shows, after OK no document appears. The
templates are all in the prefix (`Templates\en-US\`, Metric and English)
and File -> New creates a part, so a missing template is ruled out too.
Next: repeat on a clean install with .NET 4.8 from the installer, to rule
out state left over from earlier tests in this prefix. Parked for now; the next step is a trace that
names the failing IDispatch calls (`trace+ole` around `ITypeInfo_fnInvoke`,
from the marker on).

Noise seen with `+seh` in the same step: access violations on the main
thread inside Autodesk's `rse.dll`, `SMData.dll`, `Cm.dll`, handled by a
handler in `rse.dll` (continue execution); C++ exceptions on another thread
from `AdpSDKCore.dll` (analytics). Neither is related to the import.

To do: reproduce on Arch with the same STEP file (2026 and 2027); repeat
with .NET 4.8 in the prefix (done 2026-11-11, see above); if it still fails, `+seh` and a filtered
`+relay` around the crash, and the import log from Inventor. Clean room:
only the crash address and module list of Autodesk's binaries, nothing
from inside them.

## GPU ray tracing (Inventor 2027, works in testing)

**Symptom (until 2026-11-06):** *Enable Viewport GPU Ray Tracing* was greyed
out ("The graphics card in use does not support this option"), although
vkd3d-proton reported DXR 1.1 on the RX 6400. The earlier investigation is
archived in [archive/arch-hyprland-retired-2026-11-08.md](archive/arch-hyprland-retired-2026-11-08.md).

**Cause, two separate problems:**

1. Wine (opengl32): Windows reports window pixel formats with 8/8/8 bits of
   colour and no alpha as 32 colour bits; GLX and EGL report 24.
   `wglChoosePixelFormat` compares colour bits before alpha, so Inventor's two
   pixel-format choices disagreed, the second `SetPixelFormat` failed and
   Inventor declared the card unsupported. Fixed by
   `opengl32-window-format-color-bits` in winum (values measured on
   Windows 10 with an own MEASURE program, Wine test passes on Windows 10
   x86_64 and i686).
2. vkd3d-proton (dxil-spirv): ray payloads with matrices became 12-component
   vectors, which SPIR-V does not allow (RADV has no long-vector extension),
   so the ray tracing pipelines failed. Fixed by
   `gpu/vkd3d-proton/dxil-spirv-ray-payload-long-vector.patch` in winum
   (vectors longer than 4 become arrays; synthetic shaders fail without and
   validate with it in CI).

**Settings it needs** (set by hand for now; the installer will do it in the
next release):

- `HKCU\Software\Autodesk\Inventor\RegistryVersion31.0\System\Preferences\Driver`
  `EnableHydra` = 1 (DWORD);
- `HKCU\Software\Wine\AppDefaults\Inventor.exe\X11 Driver` `UseEGL` = `N`
  (GLX; the tested path);
- `HKCU\Software\Wine\AppDefaults\Inventor.exe\X11 Driver`
  `ClientSideWithRender` = `N` (see the status bar section below);
- a GPU with hardware ray tracing and a Vulkan driver with
  `VK_KHR_ray_tracing_pipeline` and `VK_KHR_acceleration_structure`
  (tested: AMD RDNA 2 with RADV, NVIDIA RTX with the proprietary driver);
  `INV_GPU` picks the card when there are several.

**What to expect:** the option is available, the ray tracing panel shows
**GPU**, Low/Draft/High render on the graphics card (High converges in about
a second on a small part on an RTX 5080). Known side effects: without
`ClientSideWithRender=N` the status bar text overlaps; after ray tracing has
been started, Restore Down and maximising again can leave parts of the window
drawn shifted (section below). Inventor 2026 is not tested.

**Validation:** opengl32 fix L1 (Windows 10, both architectures) and cross
review (Codex); vkd3d-proton port cross review (Codex, 2026-11-07; one CI
check fixed after it, an inherited `float2x2` payload limitation of
vkd3d-proton 3.0.1 open). L4: Inventor 2027 on an RX 6400 (maintainer,
part, assembly, drawing, PDF, save/reopen) and on an RTX 5080 (tester in
PR #3). Not a guarantee for other cards or drivers - reports welcome.
Details: winum `docs/patches/opengl32-window-format-color-bits.md`,
`docs/wine-repro/opengl32-pixel-format-alpha/`, `gpu/vkd3d-proton/`.

## Status bar: old text stays after GPU ray tracing (workaround)

**Symptom:** once GPU ray tracing has been started in a maximised window, new
status texts ("Ready", coordinates, prompts) are drawn over the old ones and
the strip never clears; Restore Down cleans it, maximising again brings it
back. Seen on AMD (RX 6400) and NVIDIA (RTX 5080).

**Cause, as far as measured:** not the status bar patch. Windows 10
measurements (own MEASURE program) and Wine traces show that Inventor asks
for the erase and fills the strip with an opaque `ExtTextOutW` before
drawing the text, the same before and after ray tracing, and Wine's paint
areas do not change. A Wine trace channel added only to a diagnostic build
(`+sbdiag`) showed that after ray tracing starts in a maximised window Wine
stops drawing the status bar into the window's bitmap surface and draws
directly to the X11 window through XRender; the fills report success, but
the old text survives on screen. With Wine's XRender drawing disabled for
Inventor the direct path is still taken and the text stays clean in all four
states (before, after ray tracing, restored, maximised again), with ray
tracing working. The exact faulty XRender operation is not identified yet.

**Workaround:** with Inventor closed, using the same Wine and prefix as
Inventor:

```bash
export WINEPREFIX=~/.wine-inventor2027
wine reg add 'HKCU\Software\Wine\AppDefaults\Inventor.exe\X11 Driver' /v ClientSideWithRender /t REG_SZ /d N /f
```

It disables Wine's XRender 2D drawing for Inventor only. Smoke test on AMD
(part, assembly, drawing, 2D PDF, ray tracing, save, close, reopen): OK, no
change in fonts or responsiveness noticed. NVIDIA not yet confirmed.

The status bar patch (`comctl32-statusbar-erase-background`, the dark status
bar) matches Windows for Inventor's themed status bar; its divergence for
unthemed status bars is corrected by a v2 candidate in winum. Full
investigation: winum `docs/wine-repro/comctl32-statusbar-erase/README.md`.

**For a Wine bug report:** a synthetic reproducer has not reproduced it yet
(Vulkan, D3D12, OpenGL and their combinations in a maximised window, two
GPUs); the trigger is still Inventor's switch to GPU ray tracing. Report
when there is a public test case.

## Window drawn shifted after ray tracing (open)

After GPU ray tracing has been started, Restore Down and maximising again can
leave parts of the interface drawn in other places, with a white strip along
the top and left of the viewport. Minimising and showing the window again, or
reopening it, clears it. In a fresh session without starting ray tracing,
repeated Restore Down/maximise is correct. `ClientSideWithRender=N` does not
change it. Cause unknown; possibly the same window-surface change as the
status bar, not proven.

## Home page stays stale after a dialog (open)

After closing Application Options, the Home page (WebView2) can keep showing
an old picture until it is clicked. Seen on AMD and NVIDIA, also before the
ray tracing work. `ClientSideWithRender=N` does not change it. Not yet
investigated; an earlier attribution to WebView2's GPU process was premature.

## 3D PDF (Anark) - works in testing

**Current release:** *Publish* crashes Anark's `corewrapper.exe` under
wine-mono, so 3D PDF is off.

**In testing (next release):** with Microsoft's .NET Framework 4.8 installed
in the prefix (used as a black box) instead of wine-mono for the .NET
Framework parts, `corewrapper.exe` runs. The export then took about
7 minutes: every typelib-marshaled proxy for an Inventor interface parsed
Inventor's type library again, because Wine dropped the library from its
cache when the last reference went. The winum patch
`oleaut32-typelib-keep-released` keeps up to 8 released libraries (Windows
keeps released libraries too, measured): part 15 s, assembly 20 s, the PRC
model present in the PDF (Inventor 2027.2, 2026-11-03, with a draft of the
patch). The patch passed cross review and L1 and is in winum-11.20-1. The
installer's .NET Framework 4.8 step (section ".NET Framework 4.8 in the
prefix") turns the two add-ins on. Open: L4 with winum-11.20-1 and a prefix
from the clean installation, and tests by others.
Measurements: [wine-repro/oleaut32-typelib-cache](wine-repro/oleaut32-typelib-cache/README.md).

## .NET Framework 4.8 in the prefix (installer step)

**Why:** Inventor's .NET Framework programs ran on wine-mono and crashed
there: Anark's `corewrapper.exe` (3D PDF Publish) and AnyCAD's
`AnyCADPropertyMappingTool.exe` (Import CAD -> Property Mapping, issue #10).
With Microsoft's .NET Framework 4.8 in the prefix (used as a black box) both
run. The test prefixes got it with winetricks' `dotnet48` verb.

**Where the installer comes from:** Autodesk's own image, not a download.
The 2027 image has `3rdParty/dotNetFramework/48/pkg.dotnet48.xml` (".NET
Framework Runtime 4.8", build 4.8.3928.0): `dotNetFx48_Full_x86_x64.exe` with
`/q /norestart`, success code 5100 besides 0, `ignoreFailure`, and the
condition `528039 < %NET_FRAMEWORK_RELEASE%` (the `Release` value under
`HKLM\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full`) for "already
installed". For reference only, the file in the maintainer's 2027 image
(`..._db_002_002`) has SHA-256
`9b1f71cd1b86bb6ee6303f7be6fbbe71807a51bb913844c85fc235d5978f3a0f`; it is not
checked, other images (2026, updates) may carry another build. The language
packs (`dotNetFx48LP_*`, `pkg.dotnet48_<lcid>.xml`) are not needed.

**Why it never ran:** in both images (2026 and 2027, `..._db_002_002`) the
only manifest that names it is DWG TrueView's (`x64/dwgviewr/pkg.dwgviewr.xml`,
a `core` dependency with `external="true"`), and DWG TrueView is not part of
the product's plan - it comes with the 2027.2 Update. `odis.py` plans what
the application manifests and their `<Dependencies>` reach, so the product
installation never met the package; on Windows, Setup runs it as a
prerequisite when its condition says it is missing. And under Wine the
installer finds wine-mono claiming 4.8: it exits 0 and installs nothing (the
2027.2 Update runs the same installer with that result, see the Ubuntu VM
entry in the Result log).

**What the step does** (`install_dotnet48` in `scripts/install-from-image.py`,
after the product's packages, product images only, skipped when already
done; `--no-dotnet48` leaves it out). It does what winetricks'
[`dotnet48` verb](https://github.com/Winetricks/winetricks/blob/master/src/winetricks)
does, **including the `dotnet40` step it runs first** (`load_dotnet48`,
`load_remove_mono`, `load_dotnet40`, read at version `20260125-next`); only
the 4.8 installer comes from Autodesk's image instead of a download:

1. Find the package by its `Identity/DisplayName` among the image's
   `pkg.*.xml` (`odis.find_package`), so the folder is not hard-coded; read
   the file and parameters from it.
2. Remove wine-mono as `remove_mono` does: every "Wine Mono" entry of
   `wine uninstaller --list`, then the `NDP\v3.5` and `NDP\v4` keys it wrote,
   and Wine's mono-backed `mscoree.dll` in `system32`/`syswow64` (the copy
   that contains `WINE_MONO_OVERRIDES`).
3. Check that `NDP\v4\Full\Release` is gone and no "Wine Mono" entry is
   left (else stop: the 4.8 installer would do nothing).
4. **.NET Framework 4.0, as `dotnet40` does:** `dotNetFx40_Full_x86_x64.exe`
   from Microsoft (pinned like DXVK: URL and SHA-256
   `65e064258f2e418816b304f646ff9e87af101e4c9552ab064bb74d281c38659f` as in
   winetricks, confirmed by the maintainer's download 2026-11-11; cached in
   `DOWNLOAD_DIR`, a wrong checksum deletes it and stops), Windows version
   `winxp` while it runs, `/q /c:"install.exe /q"`, then `mscoree=native`,
   `NDP\v4\Full` `Install`=1 and `Version`=4.0.30319, `OnlyUseLatestCLR=1`
   in `HKLM\Software\(Wow6432Node\).NETFramework`, the previous Windows
   version back. Checked by Microsoft's `mscoree.dll` in `system32` and
   `syswow64`; skipped when they are already there. **Why it is needed:**
   4.0 brings `mscoree.dll`; the 4.8 installer does not carry it (on Windows
   7 and later it is a file of the system) - found by the maintainer: on a
   prefix with 4.8 alone, even a repair (`REINSTALL=ALL`, "Final Result ...
   Success (0x00000000)") left no `mscoree.dll`.
5. **.NET Framework 4.8** from the image, as `load_dotnet48` runs it:
   Windows version `win7` while it runs (the verb leaves it; we put the
   previous value back), `fusion=b`, the manifest's parameters.
6. For both installers: `wineserver -k` before; afterwards wait until none
   of the setup's processes (`Setup.exe`, `SetupUtility.exe`,
   `msiexec.exe`, `ngen.exe`, `mscorsvw.exe`, the package itself) has run
   for 20 s (limit one hour), then `wineserver -k` (what is left are the
   prefix's services, which never exit) and set `mscoree=native` in
   `DllOverrides`.
7. Check the result, not the exit code: `clr.dll` in
   `windows\Microsoft.NET\Framework64\v4.0.30319` and `...\Framework\...`,
   Microsoft's `mscoree.dll` in `system32` and `syswow64` (there, and not
   Wine's mono one), the `mscoree` override, and a "Final Result" line with
   "Success" in the newest `Microsoft .NET Framework 4.8 Setup_*.html` of
   the prefix's Temp folder (the setup writes it in UTF-16; the value can
   be in the next table cell). If it is not there, the install stops with a
   message (wine-mono is gone by then, so a prefix without either is not
   left silently).

**First clean installation (2026-11-11, `f6a280b`) stopped in this step,
two faults:**

- *wine-mono was not removed, so the installer did nothing.* The log said
  "Wine Mono: not installed", but a new winum-11.20-1 prefix has the entry
  "Wine Mono Windows Support" and `NDP\v4\Full` with `Release` 0x82348
  (533320), `Version` 4.7.03190, `Install` 1. Cause: `wine uninstaller
  --list` prints its list on **stderr** (`{GUID}|||Wine Mono Windows
  Support`) and the step read only stdout (winetricks reads `2>&1`); the
  NDP keys were deleted only after an uninstall, so they stayed, the
  package condition `528039 < Release` held, and `dotNetFx48_Full_x86_x64.exe
  /q /norestart` exited 0 after 23 s with no `clr.dll`. Fix: both streams
  are read; the `NDP\v3.5` and `NDP\v4` keys are deleted every time; before
  the installer runs, `NDP\v4\Full\Release` must be gone and no "Wine Mono"
  entry left, else the step stops with that message. Checked here with
  winum-11.20-1 in a new prefix: entry found and removed, keys gone, mono
  `mscoree.dll` deleted from `system32` and `syswow64`.
- *`wineserver -w` never returned.* After the installer it waited for
  `MicrosoftEdgeUpdate.exe /c` (WebView2's updater) and
  `FNPLicensingService64.exe`. These are Windows services that Autodesk's
  and WebView2's packages register and that Wine's `services.exe` starts by
  itself whenever a Wine process starts in the prefix; they never exit.
  `stop_licensing_service()` only ends the `AdskLicensingService.exe` that
  `install-from-image.py` starts itself as a plain process, so the FlexNet
  service was still running - most likely (to confirm: its `Start` value
  under `HKLM\System\CurrentControlSet\Services`). Fix: `wineserver -k`
  before the step, and after the installer has exited (`wine` returns with
  it) `wineserver -k` and only then `-w`.

**Second clean installation (2026-11-11, `75712cc`): .NET 4.8 incomplete.**
`clr.dll` was in both Framework folders, but `mscoree.dll` in neither
`system32` nor `syswow64`, so with `mscoree=native` no .NET Framework
program could start. `wine dotNetFx48_Full_x86_x64.exe /q /norestart`
returned 0 after 41 s - the package is a self-extractor that exits while
the `Setup.exe` it started goes on - and the `wineserver -k` right after it
ended the setup half-way: its log
(`Microsoft .NET Framework 4.8 Setup_<time>.html` in Temp) has no "Final
Result". The 2027.2 Update's run of the same installer then said "BlockIf:
.NET Framework 4.8 or a later update is already installed" and "Final
Result: ... Success" without adding anything. The step's check (clr.dll and
the override only) passed it. Fixes:

- *Wait for the setup, not for the prefix.* Two ways were possible:
  stopping and disabling the services that never exit (FlexNet's
  `FNPLicensingService64`, Edge Update) for the step and restoring them,
  then `wineserver -w`; or waiting for the setup's own processes. The step
  waits for the processes (read from `/proc`: `WINEPREFIX` of this prefix
  in the environment, the Windows image name as the first word of the
  command line): it does not change services that Autodesk's and
  WebView2's installers registered, does not depend on their names, which
  differ between releases, and needs nothing restored if the step stops
  half-way. The process names are the .NET setup's own and stable; an
  unknown helper would show as a missing file or a missing "Final Result",
  not as a silent success.
- *Check what makes .NET usable:* `mscoree.dll` in `system32` and
  `syswow64` and the setup's "Final Result" (above), in
  `dotnet48_missing()`; `dotnet48_present` (launcher, add-ins) checks the
  files and the override - the setup log can be cleaned from Temp later.
- *A prefix left like this* repairs itself when the same command runs
  again: the step sees the missing files, deletes the NDP keys again (the
  setup's "BlockIf" reads them) and runs the installer again. The failure
  message says so, and that deleting the prefix and installing again also
  works.
- *Anark and Publisher:* in this state the old `dotnet48_present` returned
  true (no `mscoree.dll` at all, so `! grep -qs` on it was true), so
  `cfg_disable_addins` did not disable them and, finding nothing in
  `Addins.disabled`, printed nothing - its `info` lines go to stdout,
  which `install.sh` writes to its log, but that branch had no line of
  its own. It now always prints which way it went (".NET Framework 4.8 in
  the prefix - 3D PDF (Anark, Publisher) on" or "... not in the prefix -
  ... stays off"). If the two add-ins showed as off in Inventor, the
  likely reason is that without `mscoree.dll` no .NET add-in can load,
  not that they were moved (to confirm: `bash scripts/addins.sh list`).

**Anark and Publisher off after the second clean installation (follow-up):**
`addins.sh list` showed exactly `Anark.Core.addin`,
`Autodesk.Publisher.Inventor.addin` and
`autodesk.translatorfusion.inventor.addin` in `Addins.disabled`, and the
install log had neither the ".NET Framework 4.8 ... stays off" nor an "on
(.NET Framework 4.8)" line - one of the two is printed whenever the
`topic/dotnet48` code of `75712cc` runs `cfg_disable_addins`. Run here with
winum-11.20-1 under `set -Eeuo pipefail` (as `finish-install.sh` runs),
`dotnet48_present` saw the right `wine` and `WINEPREFIX` and returned the
right answer. Two wrong guesses were made here: another checkout, and then
that `config.env` named an emptied prefix. The maintainer found what it
was: no fault at all. The installer had done it right
(`~/.wine-inventor2027/.../Addins.disabled` held only AssistantAddin,
Feedback, InteractiveTutorial, PerfFeedback, SharedViews and
translatorfusion, moved at 18:28 by step 8). `addins.sh list` without
`INV_YEAR` read the maintainer's working Inventor 2026 prefix
(`~/.wine-invclean`, named in `config.env` on purpose), where Anark and
Publisher are off by the old default list - correct for that prefix.
What came out of it: `addins.sh` prints the release, the prefix and where
the prefix came from on its first line, so it is clear which one it reads;
`list` no longer exits 1 without an `Addins.disabled/libs`; and only when
the prefix `config.env` names holds no Inventor at all does `common.sh`
take the release it finds installed (a `config.env` prefix with Inventor is
kept; with `INV_YEAR=2027` given, the 2027 prefix is used as before).
Still useful from the first round:
`cfg_disable_addins` now logs the `wine` it uses,
the prefix, the list it applies and, when .NET 4.8 counts as missing, the
first condition that failed (`dotnet48_why`); it decides once, so the list
and the message cannot disagree; and the registry query no longer goes
through a pipe that `pipefail` could fail.

**Wine update:** with winum-11.20-1, after the removal above, a stand-in
native `mscoree.dll` (a small DLL built with MinGW, not Microsoft's) and
`mscoree=native`, `wineboot -u` brought back neither the uninstall entry
nor the NDP keys, left the override and did not touch the DLL. To catch it
should a later Wine do so, `dotnet48_present` also fails when Wine's
mono-backed `mscoree.dll` (it contains `WINE_MONO_OVERRIDES`) is back in
`system32`, and the launcher warns when the prefix's install state records
the step but `dotnet48_present` fails.

**`dotnet40` (2026-11-11, third round):** the first version left the
verb's `dotnet40` step out, on the assumption that 4.8 replaces 4.x in
place. It does not bring `mscoree.dll`, so the step now runs `dotnet40` as
well (item 4 above). The same round fixed the "Final Result" check: the
setup's HTML log is UTF-16, which the check read as UTF-8 and so never
found the line.

**Why after the product's packages, in install-from-image.py:** the test
prefixes got .NET 4.8 after Inventor was installed (winetricks on a finished
prefix), so this is the tested order; on Windows Setup installs it first,
which would run Autodesk's own MSI custom actions on Microsoft's .NET under
Wine - untested. `install-from-image.py` is the place that has the image;
`finish-install.sh` only has the prefix. Updates (`--prepared-prefix`, Nix,
`install.sh`) run after the product image, so they find .NET 4.8 installed.
An existing prefix gets it by running the product image again:
`python3 scripts/install-from-image.py IMAGE --prefix ~/.wine-inventor2027`
(done packages are skipped), then `bash scripts/finish-install.sh`.

**Not planning prerequisites in general:** `odis.py` could plan every
prerequisite and evaluate its `<Conditions>` like Setup. Under Wine the
conditions are what is unreliable (wine-mono reports a 4.8 release), the
step needs work around the installer that a generic one would not do
(remove wine-mono, overrides, check the files), and other prerequisites
would start running in the prefix, untested. So only this one package, by
name.

**Add-ins:** `Anark.Core.addin` and `Autodesk.Publisher.Inventor.addin` are
off by default only while .NET Framework 4.8 is missing
(`INV_DOTNET48_ADDINS`, `inv_default_disabled_addins` in `common.sh`);
`finish-install.sh` and `addins.sh reset` turn them on in a prefix that has
it.

**Nix:** the 4.8 installer is part of the image that `requireFile` already
covers; the 4.0 installer is a `fetchurl` with the same URL and SHA-256,
linked into `DOWNLOAD_DIR` as DXVK and vkd3d-proton are. `nix/inventor.nix` keeps Microsoft's
`mscoree.dll` when the library prunes Wine's stock DLLs and checks for both
`clr.dll` after the installation. Open for @krokosik: how removing wine-mono
(uninstaller, deleted files and keys) looks in the captured installation
layer over the base layers.

**Inventor 2026:** its image (`..._db_002_002`) has the same package at the
same place (`3rdParty/dotNetFramework/48/pkg.dotnet48.xml`, also referenced
only by DWG TrueView), so the step runs for 2026 too.

**L4, clean installation (2026-11-11, maintainer):** Arch, winum-11.20-1,
Inventor 2027.2, a new prefix installed from `topic/dotnet48` at `bea99d2`.
.NET Framework 4.0 and 4.8 installed: Microsoft's `mscoree.dll` in
`system32` (444 752 bytes) and `syswow64` (297 808 bytes), the 4.8 setup's
"Final Result" Success; 3D PDF's add-ins on. Start, sign-in, Wine 11.20
with no warning from the launcher, part, assembly, save/reopen, restart:
OK. 3D PDF Publish: OK. Import CAD's Property Mapping opens (it crashed on
wine-mono). Stress Analysis on a 500 mm tube with a hole: element size
0.01 -> 68 718 elements / 109 318 nodes, 0.005 -> 558 221 elements /
816 748 nodes; mesh and simulation about 4 minutes, OK. Import of a STEP
file into an assembly still fails on the clean prefix ("Could not Insert
Object"), into a part it works - issue #10, a separate matter (section
"Import CAD (STEP) and Property Mapping crash in 2027").

**Open:** whether `wineboot -u` (the launcher after a Wine update) brings
wine-mono back with a real winum update (tested only with a stand-in DLL);
a clean installation of Inventor 2026; L5 (a week of use).

## Prefix migrations: updating an installed prefix (2026-11-11)

**Problem:** everything in the prefix (registry, DLL overrides, DXVK,
add-ins, ...) was set only by `finish-install.sh` at installation; an
existing installation got a change only by reinstalling. Plan:
`docs/drafts/prefix-migrations.md`.

**What it is now:** numbered steps in `scripts/lib/migrations/`
(`NNNN-<what>.sh`, runner `scripts/lib/migrations.sh`, overview in the
folder's README). The prefix records what it has had in
`<prefix>/.inventor-on-linux/state`; each step saves what it changes to
`.inventor-on-linux/backup/<step>/` (the registry files always) and, if it
fails, that is put back and the run stops. `finish-install.sh` runs all
steps (0001 is its former setup, moved unchanged); `launch-inventor.sh`
runs the pending ones at every start (seconds when there are none);
`scripts/migrate-prefix.sh` does it by hand (`--status`, `--dry-run`,
`--all`, `--run`, `--restore`); the GUI's Update runs `--all`. A prefix from
before migrations is adopted: recorded as having step 0001, nothing
changed. Each step runs in its own `bash -Eeuo pipefail`: a first version
ran it in a subshell, where bash ignores `set -e` when the call sits in an
`||` - a failing `wineboot -u` was not stopped; a test now covers it.

**The first steps:**
- `0002-winum-runtime`: `wineboot -u` when the prefix was last updated for
  another Wine, then `runtime=` in the state. The launcher compared only
  `wine --version`, which is `wine-11.20` for `wine-inventor-11.20-6` and
  for winum-11.20-1, so it would not have updated a prefix moving to winum.
  Finding on the way: `wineboot -u` does not replace the copies of Wine's
  builtin DLLs in `system32`/`syswow64` (winum-11.20-1, with copies from
  Wine 11.21 and a non-Wine file; mtime unchanged), so a prefix without a
  record is judged by them only as "made by this Wine" (equal) or not; the
  launcher now also runs `wineboot -u` when the record differs (a new winum
  build of the same Wine version) and writes the record.
- `0003-x11-driver-inventor`: `UseEGL=N`, `ClientSideWithRender=N` for
  `Inventor.exe` (sections "GPU ray tracing" and "Status bar: old text
  stays after GPU ray tracing").
- `0004-enable-hydra` (**optional**, `migrate-prefix.sh --run 0004` only):
  `EnableHydra=1`, `RegistryVersion30.0` (2026) or `31.0` (2027). Not for
  every prefix: on a card without ray tracing hardware (RX 580, the
  maintainer's measurement of 2026-10-21 in PR #3) it switches Inventor to
  Hydra/USD and ray tracing runs on the CPU at about 1200 % CPU. It becomes a
  normal step with a GPU check and an L4 on a ray tracing card.
- Waiting: vkd3d-proton with the ray payload fix (no release from winum
  yet); optional .NET 4.8 for old prefixes (phase 4, proposal in the plan).

**Rule (AGENTS.md):** every change to what a prefix gets is a new step,
listed in `SHA256SUMS`; `tests/test_migrations.py` fails on an edited or
unlisted step and on prefix changes in `finish-install.sh`.

**Checked:** 13 tests with fake prefixes and a fake Wine whose registry is
the prefix's `user.reg`/`system.reg` (old prefix gets 0002-0003 and then
"nothing to do"; a prefix made by winum gets 0003; 0004 only by name; a prefix with
everything is untouched; a failing step and a failing `wineboot -u` are put
back; `--restore`; a busy prefix is left alone; `--status` writes nothing;
optional steps only by name; `--all`; the runtime check; a failing command
in the middle of a step), and 2 guard tests. With winum-11.20-1
on a test prefix whose `ntdll.dll` copies came from Wine 11.21 (as a
pre-winum prefix): 0002-0004 applied in 15 s (0004 was not optional yet), the values readable with
`wine reg query`, a second run "nothing to do", backups 3 MB each. Open:
the maintainer's copy of `~/.wine-invclean` (Inventor 2026 from before
winum) and the clean `~/.wine-inventor2027`; Nix (@krokosik): the steps run
inside `finish-install.sh` in the build, the launcher part is not wired.

## This project's own Wine (v0.2)

Up to v0.1 the fixes were built per DLL and copied over the system's Wine
(`build-wine-dll.sh --install`). Every Arch Wine update replaced them, and the
prefix then ran without them until `rebuild-wine-fixes.sh`. Since v0.2 the
whole Wine is built once, in public, by `.github/workflows/build-wine.yml`
(`scripts/build-wine.sh`: vanilla source of the version in `wine/version.env`,
all of `patches/`, `--enable-archs=x86_64,i386`, Arch Linux container) and
published as release `wine-<version>-<build>`. `scripts/get-wine.sh` downloads
it, checks it against `wine/SHA256SUMS` and unpacks it to
`~/.local/share/inventor-on-linux/`; `common.sh` puts its `bin/` first in
`PATH` (`INV_WINE=auto|bundled|system`). The system's Wine is not touched.
The build also patches the 32-bit (i386) PE DLLs, which the per-DLL builds
never did. A build made on Arch also runs on Ubuntu 24.04 (glibc 2.38 symbols).

**Do not mix Wine versions on one prefix.** The first test used a 11.19 build
while Arch had moved to 11.20: the launcher's `wineboot -u` then switched the
prefix between the two versions on every start, and under KDE the maximized
Inventor window lost its own title bar row (quick access toolbar, user name)
behind a KDE title bar, and only part of the window was drawn. With the 11.20
build (`wine-11.20-1`) maximizing is correct again. Keep `wine/version.env` on
the version the prefix was last updated with, and move forward only.

## winum as the Wine for Inventor (winum-11.20-1)

**What changed for the user:** Inventor runs on
[winum](https://github.com/Harvi654/winum) `winum-11.20-1` instead of this
project's own `wine-inventor-11.20-6`. `scripts/get-wine.sh` downloads
`winum-11.20-1-x86_64.tar.xz` from winum's releases, checks it against
`wine/SHA256SUMS` and unpacks it to `~/.local/share/inventor-on-linux/`; an
installed older `wine-inventor-*` build keeps working until then (the
launcher says a newer one is named). NixOS builds the same series from the
flake input `winum` (`nix/wine.nix`).

**Why:** winum carries the same fixes, now each with a Wine test that passed
on real Windows 10 (or a recorded reason why there cannot be one), paired L2
runs against vanilla Wine, cross review by a second assistant and L4 in
Inventor; the series is shared with the SOLIDWORKS project. All 27 patches
of `wine-inventor-11.20-6` are in winum's series of 62; 15 of them in a
revised version, the other 12 with the same code (for
example the toolbar `TB_SETROWS` fix, which now gives the symbol palette
Windows' 40x24 buttons); winum also has fixes from the SOLIDWORKS work and
the two oleaut32/opengl32 fixes that were drafts here. Record:
`docs/release/winum-11.20-1.md` in winum.

**False "Wine fixes not installed" warning:** with winum in `PATH`
(`INV_WINE=system`, `PATH=<winum>/bin:$PATH`) the launcher warned that the
fixes were missing and asked for `rebuild-wine-fixes.sh`. It compared the
per-DLL backups of the v0.1 way (`build-wine-dll.sh --install`, `*.orig-<wine
version>` next to the system's DLLs), which a winum never has. The check and
the per-DLL builds are retired; the launcher reads the `BUILDINFO` next to the
Wine in `PATH` (`wine_winum_name` in `common.sh`): a winum is named in the
start line, any other Wine gets one line that the fixes are only in winum.

**Archived:** `patches/*.patch` (with `debug/`, `drafts/`), `build-wine.sh`,
`make-wine-source.sh`, `lib/wine-patches.sh`, the "Build Wine" workflow and
the per-DLL scripts (`build-wine-dll.sh`, `build-wbemprox.sh`,
`rebuild-wine-fixes.sh`) are in `docs/archive/own-wine-build/`, unchanged.
`patches/libgsf/` stays (the flake's libgsf overlay).

**Checks:** `bash -n` on all scripts, `python3 -m unittest discover -s
tests`; the launcher's Wine detection with a fake winum and a fake plain Wine
in `PATH` (commands in the commit). Nix: `flake.lock` gains only the input
`winum` (narHash equal to `nix hash path` of `git archive winum-11.20-1`);
`nix flake check` with the new check `winum-pin` (version.env and the flake
input name the same release) runs in this repository's CI and with
@krokosik.

**Open:** L4 of the downloaded winum-11.20-1 release in Inventor 2026 and
2027 (start, part, assembly, drawing, save/reopen, restart, plus the symbol
palette); the NixOS build of the winum series (@krokosik).

## Known harmless log messages

- `senddmp.exe` / `upi.exe` "does not exist", `failed to launch ... 87`: Autodesk's
  crash reporter (CER) and usage-data uploader are not in the prefix, so nothing
  is sent. Intended.
- `class {cfe9f29b-...} not registered`: not registered on Windows either.
- `class {1060954f-...} not registered`: the Fusion interop add-in, disabled by
  default (`scripts/addins.sh enable translatorfusion` to try it).

## Result log

**2026-11-11 - Prefix migrations (phases 1-3):** numbered steps that update
an installed prefix with backups and rollback, run by the launcher,
`migrate-prefix.sh` and the GUI's Update; first steps: winum runtime
(`wineboot -u`), the X11 driver values for Inventor; `EnableHydra` only on
request (it moves ray tracing to the CPU on a card without RT). Details:
section "Prefix migrations".

**2026-11-11 - .NET Framework 4.8 step: L4 on a clean installation:**
Inventor 2027.2 installed into a new prefix from `topic/dotnet48`
(`bea99d2`) with winum-11.20-1: .NET 4.0 + 4.8 in place (`mscoree.dll` in
both system folders, Final Result Success), 3D PDF Publish works, Property
Mapping opens, start, sign-in, part, assembly, save/reopen, restart and a
Stress Analysis up to 558 221 elements work. STEP import into an assembly
still fails (issue #10). Merged into `main`. Details: section ".NET
Framework 4.8 in the prefix".

**2026-11-11 - .NET Framework 4.8 step, third round:** `mscoree.dll` was
still missing because .NET 4.8 does not carry it - .NET 4.0 does, and
winetricks' `dotnet48` installs `dotnet40` first. The step now does the
same (4.0 downloaded from Microsoft, pinned, SHA-256 confirmed by the
maintainer), and reads the setup's UTF-16 log for its "Final Result".
Details: section ".NET Framework 4.8 in the prefix".

**2026-11-11 - .NET Framework 4.8 step, second clean installation:**
`clr.dll` in place but no `mscoree.dll`: the installer is a self-extractor
that returned while its setup went on, and the step's `wineserver -k`
ended the setup. The step now waits for the setup's processes, checks
`mscoree.dll` and the setup's "Final Result", repairs such a prefix on a
rerun, and the add-in step always logs its decision. Details: section
".NET Framework 4.8 in the prefix".

**2026-11-11 - .NET Framework 4.8 step, first clean installation:**
stopped in the step - wine-mono's uninstall entry was read from stdout
while Wine prints it on stderr, so wine-mono and its NDP keys stayed and the
installer did nothing; and `wineserver -w` waited for services that never
end. Fixed (keys always deleted, check before the installer, `wineserver
-k`); `wineboot -u` does not bring wine-mono back (tested with winum).
Details: section ".NET Framework 4.8 in the prefix".

**2026-11-11 - .NET Framework 4.8 step in the installer (in testing):**
`install-from-image.py` replaces wine-mono with the image's own .NET
Framework 4.8 installer after the product's packages, as winetricks'
`dotnet48` does, and checks `clr.dll`; 3D PDF's add-ins are on when it is
there. Details: section ".NET Framework 4.8 in the prefix".

**2026-11-11 - winum-11.20-1:** the installer, launcher and Nix packaging
switch from this project's own Wine build to winum-11.20-1; the own build,
its patches and the per-DLL fixes for the system's Wine are archived; the
false "Wine fixes not installed" warning with winum in `PATH` is gone.
Details: section "winum as the Wine for Inventor".

**2026-11-10 - Issue #10 recorded (open):** Import CAD of a STEP file fails
with "Could not import object" and Property Mapping crashes in
`AnyCADPropertyMappingTool.exe` running on Wine Mono (NixOS, Inventor 2027).
First hypothesis: needs .NET 4.8; to be fixed for the next release.

**2026-11-11 - Issue #10 with .NET 4.8:** Property Mapping no longer
crashes (fixed by .NET 4.8, which goes into the installer). The STEP import
still ends with "Could not Insert Object" after a successful Load Model;
to be compared with Windows.

**2026-11-10 - NixOS font experiment:** with compositor scaling already
disabled for XWayland, changed Inventor 2027's grayscale smoothing to ClearType
in its user state before UI startup. Registry readback passed; the user saw no
improvement. A probe traced unsmoothed Tahoma to Wine's GASP handling. A second
local experiment substituted Segoe UI for system menu/status fonts; probe
rendering is antialiased and the user confirmed improvement. The Nix launcher
now applies the mapping conditionally on real Segoe UI availability. Six
regression cases cover host/prefix detection, fallback families, disappearance,
idempotence and custom substitutions. All 17 repository tests and flake checks
passed; the updated 2027 launcher built and started Inventor, and a probe in
its namespace confirmed Segoe UI for menu/status fonts. DPI unchanged. No Wine
patch.

**2026-10-26 - Native Wayland remains unusable:** the draft bridge rendered
WebView2 Home content, but was terribly slow and glitchy. Keep X11/XWayland.
The [reproducer README](wine-repro/winewayland-cross-process-gdi/README.md)
contains the investigation, experiment results and upstream issue links.

**2026-10-15 - Inventor 2026 build 30.40.43500 (.NET 10), Wine 11.19, Arch + Hyprland, RX 580 (RADV):**
UI starts, Autodesk sign-in works, Part created, sketch + Extrude rendered in the
3D viewport through DXVK - **without the OGSFactory.dll binary patch**, with only
the Win32_TimeZone wbemprox patch. Fixes needed on the way (all in these scripts):
font folders as drive letters (isolation), registry import as UTF-16, disabled
add-ins outside `Bin\Addins`, Windows fonts copied and registered, `Backgrounds`
copied. Open: App Home page blank and File menu closes (WebView2), iLogic,
Realistic visual style not tested yet.

**2026-10-15, later:** with `Default.ipj` in place, materials and appearances
are listed and applied, parts are shaded and lit (Default IBL), shadows and
selection highlight work, Visual Style list complete.

**2026-10-15, evening:** WebView2 renders (Windows 7 + wined3d + HKLM policy):
licensing dialog shows and closes normally, Home tab works (project picker,
Open/New, Recent, Help links) after copying `ProgramData\Autodesk\Inventor 2026`.

**2026-10-18 - iLogic:** enabled with `addins.sh enable ilogic`. The iLogic
ribbon panel, the iLogic browser, the Edit Rule dialog (snippets, model tree,
parameters, code editor with syntax colours) work, and a rule
`MessageBox.Show("Ahoj", "Test")` ("hello") runs in an assembly. The old `E_FAIL` on
`get_ActiveDesignProject` was the missing `Default.ipj`, not iLogic itself.
A rule `Dlzka = CDbl(InputBox("Dĺžka v mm", "Test", Dlzka))` (Slovak for
"length in mm", quoted as run: the non-ASCII prompt was part of the test) with
`iLogicVb.UpdateWhenDone = True` in a part changed a renamed extrusion
parameter from 50 to 120 mm and the model updated (checked with Measure).
iLogic is now on by default.

**2026-10-18 - Stress Analysis hangs on start (ntdll, activation contexts):**
Environments → Stress Analysis left Inventor with a busy cursor for good.
`winedbg bt all`: the main thread waits (`WaitForSingleObject`, no timeout) in
`fea_addin_utils` for a worker thread; the worker sits in `combase` creating
`{E4E2FE54-5A90-4006-AC58-9E11DE19817B}` (`+ole`: `CoCreateInstance` from the
MTA, then the main apartment is looked up). The class is not in the registry;
it comes from the manifest embedded in `FEA_Application_Common.dll`:
`<comClass clsid="{E4E2FE54-...}" threadingModel="free">` - lower case.
Wine's manifest parser compared the value case-sensitively, took "free" as no
threading model, and no threading model means "create it in the main STA" -
which was the thread waiting for the worker: deadlock. Windows (and Wine for
the same value in the registry) compares case-insensitively.
Fix: `patches/ntdll-actctx-threadingmodel-case.patch` (`xmlstr_cmpi`), part
`ntdll` of the Wine fixes (only the PE `ntdll.dll` is replaced).

**2026-10-18 - Stress Analysis Mesh View: Inventor disappears (rpcrt4):**
with the ntdll fix the Stress Analysis environment opens; Mesh View then ended
Inventor without a message. `debug-crash.sh` (+seh): `EXCEPTION_WINE_STUB`,
`Call ... to unimplemented function RPCRT4.dll.NdrStubCall3, aborting`, raised
on the server side of a COM call (the client got `I_RpcReceive ... fault
packet with status 0x80000100`). `NdrStubCall3` is what MIDL puts in the stub
dispatch table of interfaces built for both NDR and NDR64 (`/protocol all`,
the 64-bit default). Wine had the client side (`NdrClientCall3`, which picks
the NDR syntax) but not the stub. Fix: `patches/rpcrt4-ndrstubcall3.patch`
implements it the same way - the NDR format strings from `pSyntaxInfo`, then
the existing `NdrStubCall2` interpreter (factored out as `ndr_stub_call`).

**2026-10-18 - Mesh View crash (combase, activation context of incoming calls):**
with `NdrStubCall3` the mesh progress window appears, then Inventor
disappears. `debug-crash.sh`: right after `class {A9485C80-...} not
registered` (the second class of the same `FEA_Application_Common.dll`
manifest) the main thread reads address 0 in `FEA_Addin_Utils.dll+0x757fc`.
`+actctx`: the lookup happens on an RPC worker thread executing an incoming
call (`ICommunicator`, from the mesher) with no activation context active, so
the manifest's classes cannot be found. Windows runs incoming COM calls in the
activation context the object was created/marshaled in (it is part of the
object's COM context). Fix: `patches/combase-stub-activation-context.patch` -
the stub manager records the active activation context when it is created and
`rpc_execute_call` activates it around `IRpcStubBuffer_Invoke`.

**2026-10-18 - Stress Analysis works:** with the ntdll, rpcrt4 and combase
fixes: mesh (18195 nodes / 10517 elements on a pipe elbow), Simulate with
convergence, Von Mises / displacement results, animation. Screenshots:
`docs/images/stress-mesh.png`, `docs/images/stress-analysis.png`. The add-in
is now on by default.

**2026-10-18 - Home page hover highlight lags (winex11, X flush):** the
highlight of Recent rows showed the row the mouse was over a moment ago and
stayed lit after the mouse left; clicks hit the right row. Same on KDE Plasma,
so not Hyprland. With DevTools attached (`--remote-debugging-port`): the page
gets 100-500 `mousemove` events/s and a dot drawn at the event position
follows the cursor - input is fine, the window shows an older frame.
`--in-process-gpu` did not change it. WebView2 draws into a child window of
Inventor's window, owned by another process; win32u gives child windows no
window surface, so winex11 draws straight to the top-level X window with
`XPutImage` on `gdi_display` - without `XFlush`. A small update (a hover
change) stays in Xlib's output buffer until that process next handles X events
(the next mouse move), which is exactly "one frame behind". Fix:
`patches/winex11-flush-putimage.patch` flushes after `X11DRV_PutImage` and `xrenderdrv_PutImage` (with XRender - the usual case - GDI image puts go through the XRender driver).
Confirmed fixed with `--disable-gpu`; with the GPU process (ANGLE/SwiftShader)
the page still lags behind - another presentation path. Inventor.exe's
WebView2 now gets `--disable-gpu` by default (`INV_WEBVIEW2_ARGS_INVENTOR`);
the licensing agent and Identity Manager keep the previous switches.

**2026-10-22 - Frame Analysis works (ole32, compound files and threads):**
Simulate in Frame Analysis ended `rkernel.exe` (the Robot solver) on
`Assertion failed: blockIndex != nextBlock` in `storage32.c`. First a
single-threaded fuzzer found a real ole32 bug (a stream truncated to zero in
a transacted storage was left out of Commit) - fixed, but the solver still
crashed, next time on `depotBlockCount < bigBlockDepotCount`. A `+storage`
trace of the solver alone showed four threads using one compound file at once;
a four-thread test program reproduced the original assertion every time.
Wine's storage code has no locking; one recursive lock around all storage,
stream and enumerator methods fixed it. Tested: Frame Analysis with loads and
constraints on a frame of ISO 10799-2 40x40x3 tubes, Simulate finishes,
displacement results shown. Wine build `wine-11.20-6`; Frame Analysis is now
on by default. Details: section "Frame Analysis: Simulate crashes the solver".

**2026-10-22 - Frame Analysis in Inventor 2027:** Simulate and results work
with `wine-11.20-6` (Shear Stress Ty shown on the same test frame). New issue:
the iLogic pane sometimes stays on the left with an old picture (not
repainted), even on the Home page; toggling View → User Interface → iLogic
clears it. Intermittent, no reliable steps yet (2027 only).

**2026-10-27 - Source of the Wine releases (LGPL):** every `wine-*` release
gets `wine-inventor-<v>-<b>-source.tar.xz` next to the binary - vanilla Wine
with the patches applied as built, `PATCHES.txt` and a "Modified by" comment
at the end of each changed file, plus the build files of that tag
(`scripts/make-wine-source.sh --ref <tag>`; same ref and Wine tarball give
the same bytes, checked twice for `wine-11.20-6`). `build-wine.sh` now applies
the patches through the same `scripts/lib/wine-patches.sh`, copies
`PATCHES.txt` into the binary and lists the wine-mono/wine-gecko versions and
their source URLs in `BUILDINFO`. The releases `wine-11.19-1` … `wine-11.20-6`
were published before this; their source is added by running the "Build Wine"
workflow with `tag` set (no binary is rebuilt or replaced).

**2026-11-03 - Inventor 2027.2, unpacked image (issue #6):** in a clean
Ubuntu 26.04 VM the release of an unpacked 2027 image is read from its
manifests (e171b0f); a forced `INV_YEAR=2026` stops before anything is
installed. A full installation by the README (GUI, the two downloads plus
`Inventor_2027.2_Update.exe`) finished; Inventor 2027.2 signs in, parts,
assemblies and Content Center work. Fixed on the way: the Update's new
MCP Server package (`%ALLUSERSPROFILE%`), `uninstall.sh` always assuming
2026, the Assistant panel (off by default), two GUI details. The Arch machine's
2027 prefix was updated to 2027.2 (build 334). Details: section "Inventor
2027: unpacked image without a year, the 2027.2 Update (issue #6)".

**2026-11-06 - Inventor 2027 on Ubuntu 26.04.1 LTS (VM, llvmpipe), with the
SOLIDWORKS project's MSI test runtime:** fresh install with
`install.sh ~/Downloads/Inventor2027 --prefix ~/.wine-inventor2027-msitest
--skip-wine --no-desktop --no-content`, Wine = the SOLIDWORKS profile -8 with
the 18 MSI candidates (59 patches, msi.dll is shared with Inventor). All 27
ODIS steps exit 0; the 2027.2 update installs all 19 steps. Inventor installs
only three MSI packages (`adsk-hive-host.msi`, `InvPrivate.msi`,
`InvPrivateLoc.msi`); the 2027.2 update is not an MSP but a new ODIS image
(ADIX/EXE plus `adsk-hive-host.msi` 1.4.1.2). File list of
`Program Files/Autodesk` against the Arch install (2027.1): 5238 files in
both; the 5 + 14 differences are Assistant/MCP and `Microsoft.Extensions.*`
DLLs that differ between 2027.1 and 2027.2, `vkd3d-proton.cache` and the home
path inside `uninstall.dat`. Sign-in, Open, New part, sketch, Extrude,
assembly, save and double-click on a `.ipt` in Nautilus work.
Found on the way, to fix in the scripts:
- `--no-desktop` also skips the `adskidmgr://` handler, so the browser
  sign-in cannot reach Inventor; a test prefix needs
  `install-desktop-integration.sh` (or the handler alone).
- `install.sh` hides 7-Zip's error and reports a damaged download as "not an
  Inventor download" (here: a copy broken on the way into the VM).
- The SOLIDWORKS test runtime has no wine-mono inside, so Wine asked to
  download it (the project's own Wine release bundles it).
- The update runs Autodesk's `dotNetFx48_Full_x86_x64.exe`, which exits 0 but
  installs nothing while wine-mono reports .NET 4.8 (no `clr.dll`, builtin
  `mscoree`).
- Cosmetic: Inventor files show the Inventor app icon in the file manager,
  not their type icon or a preview.

**2026-11-06 - GPU ray tracing works (Inventor 2027, RX 6400):** with the
winum opengl32 window colour-bits fix and the vkd3d-proton ray payload fix,
*Enable Viewport GPU Ray Tracing* is available and Low/Draft/High render on
the GPU; part, assembly and save work. Confirmed on an NVIDIA RTX 5080 by a
tester (PR #3, 2026-11-07). Details: section "GPU ray tracing".

**2026-11-07 - Status bar text overlaps after GPU ray tracing; workaround:**
the overlap appears only after ray tracing starts in a maximised window.
Measurements on Windows 10 and Wine traces ruled out the status bar patch;
a diagnostic Wine build showed the switch to direct XRender drawing, and
`ClientSideWithRender=N` for Inventor keeps the text clean with ray tracing
working (smoke test: part, assembly, drawing, 2D PDF, save/reopen). Still
open: window drawn shifted after Restore Down/maximise once ray tracing ran,
and the Home page staying stale after Application Options. Details: section
"Status bar: old text stays after GPU ray tracing".

**2026-11-08 - This file re-organised:** a contents list, sections grouped
by topic, new sections for GPU ray tracing, the status bar workaround, the
open repaint issues and 3D PDF. The sections of the first setup (copying a
Windows installation) and the superseded GPU ray tracing notes moved to
`docs/archive/arch-hyprland-retired-2026-11-08.md`, unchanged.
