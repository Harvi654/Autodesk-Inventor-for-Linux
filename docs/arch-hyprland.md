# Arch Linux + Hyprland

Notes for running this project on vanilla Arch with the Hyprland compositor,
with Windows (and Inventor) installed on a second disk in a dual-boot.

The original setup was done on CachyOS. Everything Inventor-specific is the same;
the differences are packages, mounting, and Wayland/XWayland details.

## Order of operations

```bash
bash scripts/phase0-setup.sh                 # packages from official repos only (asks for sudo)
sudo mount -t ntfs3 -o ro /dev/sdXN /mnt/windows   # see "Mounting Windows" below
bash scripts/check-system.sh                 # read-only; fix anything it marks ERROR
bash scripts/export-registry.sh              # registry/autodesk-full.reg (gitignored)
bash scripts/build-wbemprox.sh --install --hook   # patched Wine WMI DLL
bash scripts/rebuild-prefix.sh               # ~15-30 min, mostly copying
bash scripts/install-desktop-integration.sh  # adskidmgr:// handler + launcher entry
bash scripts/launch-inventor.sh              # first run opens the browser for SSO
```

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

Work in progress, but it gets to a working Inventor. Instead of copying a
Windows installation, Autodesk's own packages are installed under Wine:

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

## Mounting Windows

Mount **read-only**. The scripts only read from it, and if Windows Fast Startup
or hibernation is on, mounting NTFS read-write can corrupt it (the kernel `ntfs3`
driver refuses rw in that case anyway).

```bash
sudo mkdir -p /mnt/windows
sudo mount -t ntfs3 -o ro /dev/sdc2 /mnt/windows      # replace sdc2 with your partition
```

Permanent (`/etc/fstab`, use the UUID from `lsblk -f`; `nofail` so boot doesn't
hang if the disk is missing):

```
UUID=XXXXXXXXXXXXXXXX  /mnt/windows  ntfs3  ro,nofail,uid=1000,gid=1000  0 0
```

Windows only has to be mounted while building the prefix. Launching Inventor
uses the copy inside `~/.wine-inventor2026`.

## Hyprland

Wine runs through **XWayland** (the prefix pins Wine's X11 driver). Make sure
XWayland is enabled (it is by default) and `DISPLAY` is set in your session.

### HiDPI / fractional scaling

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

## wine-mono on Arch

README "Key Discovery #1" says the WPF stub assemblies in the wine-mono GAC must
be deleted. On Arch the `wine-mono` package is a **shared system install**
(`/usr/share/wine/mono/wine-mono-*`), not a copy inside the prefix, so
`rebuild-prefix.sh` only warns instead of deleting system files.

Status: **untested on Arch.** If Inventor exits right after starting (log shows
a mono assertion and `Environment.Exit`), options to try, in this order:

1. Remove the four DLLs from the system install
   (`PresentationCore`, `PresentationFramework`, `WindowsBase`, `System.Xaml`
   under `/usr/share/wine/mono/wine-mono-*/lib/mono/gac/`). A `wine-mono` update
   restores them.
2. Uninstall the `wine-mono` package and let Wine install mono into the prefix
   (it offers to on `wineboot`), then rerun `rebuild-prefix.sh`, which then
   finds and removes the stubs inside the prefix.

Please report which one was needed.

## Differences from the original scripts

| Area | Original | Here |
|------|----------|------|
| Component versions | hard-coded (Licensing 15.4.2.4, Components 1.8.0, IdMgr 1.16.5.1/1.14.0.3, build 30.0.17500) | detected from `/mnt/windows` and the registry export |
| Registry export | generated but never imported | imported with `regedit` **as UTF-16** before setting keys (see below) |
| `rebuild-prefix.sh` | under `set -e`, any failing `cp`/`mv ... 2>/dev/null` of an optional file (license cache, Design Data dir that doesn't exist yet, `wineserver -k` with nothing running) can abort the run | optional steps warn and continue |
| OGSFactory.dll patch | written blindly at fixed offsets | not needed: fixed in Wine (wbemprox patch), Autodesk files stay untouched |
| WebView2 installer | expected in `/tmp`, never downloaded | downloaded to `downloads/` |
| Wine patch | `patch -p1` fails (absolute `/tmp/...` paths in header) | regenerated as a proper `a/ b/` patch |
| Logs | `~/Projects/Inventor on linux/logs` | `logs/` in the checkout |
| IPC cleanup | only `interprocess/01000000` | whole `interprocess/` (Open Problem #4) |
| `msquic=` override | documented, not set | set in `launch-inventor.sh` |
| Packages | `dxvk-mingw-git` via pacman (not in Arch repos) | official repos only, no AUR |
| DXVK | `setup_dxvk` from a system package | release 2.7.1 from github.com/doitsujin/dxvk, SHA-256 pinned (same hash as winetricks `dxvk2071`); `INV_DXVK=system` to use `setup_dxvk`; vkd3d-proton 3.0.1 (Direct3D 12) from github.com/HansKristian-Work/vkd3d-proton, SHA-256 pinned, `INV_VKD3D=off` keeps Wine's d3d12 |
| File access | `Z:` = whole filesystem, Documents/Desktop/... linked into `$HOME` | only `C:` (prefix) and `D:` = `~/Inventor`; `--no-sandbox` restores Wine defaults |

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

## Registry import must be UTF-16

`hivexregedit` writes strings as `hex(1):` UTF-16LE bytes into a plain-text
file. Wine's `regedit` reads a file without a UTF-16 byte-order mark as ANSI and
widens each byte of `hex(1)` data separately, so `"False"` is stored as
`F\0a\0l\0s\0e\0`. It looks normal in logs, but .NET rejects it. Inventor's
InfoCenter then fails silently (`InfoCenter.log` in
`%LOCALAPPDATA%\Autodesk\Inventor 2026\ENU\`: *String 'False' was not
recognized as a valid Boolean*) and Inventor dies at startup with
`NullReferenceException` in `InforCenterUtil.GetInfoCenterHwnd()`.

`import_reg_file` converts the export to UTF-16LE with a BOM before importing.
To repair an older prefix: `bash scripts/import-registry.sh`.

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
(Upstream still needs tests for it.)

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
Confirmed working. The delay is empirical - before proposing it upstream,
measure when Windows delivers that mouse move.

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
as on Windows.

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

## Known harmless log messages

- `senddmp.exe` / `upi.exe` "does not exist", `failed to launch ... 87`: Autodesk's
  crash reporter (CER) and usage-data uploader are not in the prefix, so nothing
  is sent. Intended.
- `class {cfe9f29b-...} not registered`: not registered on Windows either.
- `class {1060954f-...} not registered`: the Fusion interop add-in, disabled by
  default (`scripts/addins.sh enable translatorfusion` to try it).

## Result log

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
`MessageBox.Show("Ahoj", "Test")` runs in an assembly. The old `E_FAIL` on
`get_ActiveDesignProject` was the missing `Default.ipj`, not iLogic itself.
A rule `Dlzka = CDbl(InputBox("Dĺžka v mm", "Test", Dlzka))` with
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
