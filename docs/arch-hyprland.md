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
| OGSFactory.dll patch | written blindly at fixed offsets | original bytes verified first; skipped on a different build; `scripts/ogs-patch.sh status|apply|revert` |
| WebView2 installer | expected in `/tmp`, never downloaded | downloaded to `downloads/` |
| Wine patch | `patch -p1` fails (absolute `/tmp/...` paths in header) | regenerated as a proper `a/ b/` patch |
| Logs | `~/Projects/Inventor on linux/logs` | `logs/` in the checkout |
| IPC cleanup | only `interprocess/01000000` | whole `interprocess/` (Open Problem #4) |
| `msquic=` override | documented, not set | set in `launch-inventor.sh` |
| Packages | `dxvk-mingw-git` via pacman (not in Arch repos) | official repos only, no AUR |
| DXVK | `setup_dxvk` from a system package | release 2.7.1 from github.com/doitsujin/dxvk, SHA-256 pinned (same hash as winetricks `dxvk2071`); `INV_DXVK=system` to use `setup_dxvk` |
| File access | `Z:` = whole filesystem, Documents/Desktop/... linked into `$HOME` | only `C:` (prefix) and `D:` = `~/Inventor`; `--no-sandbox` restores Wine defaults |

## Experiment: is the OGSFactory.dll patch still needed?

Wine's `IEnumWbemClassObject::Next()` (`dlls/wbemprox/class.c`) cannot return
`S_OK` with a NULL object: on an empty result it returns `WBEM_S_FALSE` (1)
with `*puReturned = 0`. `S_FALSE` is a success code, so OGS most likely only
checks `FAILED(hr)` and then dereferences the NULL object. The result was empty
because `Win32_TimeZone` did not exist in Wine.

The binary patch was made in session 2, the wbemprox patch in session 3. If
this reasoning is right, **with the patched wbemprox.dll installed, the
unmodified OGSFactory.dll should not crash**, and the patch's side effects
(darker materials, "Material Library not available" in Realistic style) would go
away.

```bash
bash scripts/ogs-patch.sh status    # expects: wbemprox has Win32_TimeZone
bash scripts/ogs-patch.sh revert    # original DLL
bash scripts/launch-inventor.sh     # create a Part, switch to Realistic style
bash scripts/ogs-patch.sh apply     # back, if it crashes
```

If it works, that resolves Open Problems #1 and the Realistic Visual Style
entry, and makes the wbemprox upstream patch the only fix needed.

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

Still the old "I" icons after the import above, also with HKLM DefaultIcon set
to `SrvRes.dll`. A `+shell` trace shows the dialog does **not** call
`IShellItemImageFactory::GetImage`; it calls
`ExtractIconW(...\Inventor.exe, 2..5)` itself - apparently its fallback when the
system hands back a generic document icon. Next: find which shell call returns
the generic icon for `.ipt`/`.iam` (trace limited to the moment the dialog opens).
The shell32 GetImage patch is still worth upstreaming for other programs.

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

## Drawings: editing dimension text

Editing a dimension's text aborted Inventor with
`Assertion failed ... riched20/caret.c line 232: ~para->nFlags & MEPF_REWRAP`:
the RichEdit caret was placed before the text had been rewrapped.
`patches/riched20-caret-rewrap.patch` rewraps at that point instead
(`build-wine-dll.sh riched20 --install --hook`). Confirmed working.

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

## Open: black rectangles around the sketch input boxes

While drawing, the length/angle input boxes sit on a shared window that should
be transparent; under the X11 driver it is drawn black. Wine's Wayland driver
(`HKCU\Software\Wine\Drivers` `Graphics=wayland`) was tried: the Home page
(WebView2, a window embedded from another process) stays empty there, so it is
not usable yet. Back to `x11`; the transparency has to be fixed in winex11.

Cause (trace `+win`): the boxes are child Edits of one `HUDFieldDialog`
popup, resized to span both boxes and clipped with `SetWindowRgn`. winex11
turns the region into an X bounding shape, which Xwayland/Wayland
compositors ignore when drawing - hence black. First try
(`patches/winex11-shape-alpha-xwayland.patch`, NOT for use): switch every
window that gets a region to an ARGB visual and write the outside as
transparent. That broke Inventor (and the WebView2 Home page): other
windows with regions (the main frame, Chromium's) then mixed 32- and
24-bit drawables -> `BadMatch` in `X_CopyArea`/`RenderCreatePicture`, the
process exits. Undo with `build-wine-dll.sh winex11 --restore`. Needs to
be limited to plain popups that only draw through the window surface.

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
