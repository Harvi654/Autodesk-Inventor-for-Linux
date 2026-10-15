# Arch Linux + Hyprland

Notes for running this project on vanilla Arch with the Hyprland compositor,
with Windows (and Inventor) installed on a second disk in a dual-boot.

The original setup was done on CachyOS. Everything Inventor-specific is the same;
the differences are packages, mounting, and Wayland/XWayland details.

## Order of operations

```bash
bash scripts/phase0-setup.sh                 # packages (asks for sudo), DXVK from AUR
sudo mount -t ntfs3 -o ro /dev/sdXN /mnt/windows   # see "Mounting Windows" below
bash scripts/check-system.sh                 # read-only; fix anything it marks ERROR
bash scripts/export-registry.sh              # registry/autodesk-full.reg (gitignored)
bash scripts/build-wbemprox.sh --install --hook   # patched Wine WMI DLL
bash scripts/rebuild-prefix.sh               # ~15-30 min, mostly copying
bash scripts/install-desktop-integration.sh  # adskidmgr:// handler + launcher entry
bash scripts/launch-inventor.sh              # first run opens the browser for SSO
```

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

Inventor opens many dialogs and tool windows. In tiling mode they get tiled,
which is unusable. Float everything except the main window. Find the class with
`hyprctl clients` while Inventor runs (expected: `inventor.exe`).

Syntax below is for Hyprland 0.48+ (`windowrule` with `class:`/`title:`); check
`hyprctl version` and the Hyprland wiki if your version differs.

```ini
windowrule = float, class:^(inventor\.exe)$
windowrule = tile, class:^(inventor\.exe)$, title:^(Autodesk Inventor Professional.*)$
# Identity Manager / licensing popups
windowrule = float, class:^(adskidentitymanager\.exe|adsklicensingservice\.exe)$
# Wine tooltips/menus sometimes steal focus
windowrule = nofocus, class:^(inventor\.exe)$, title:^$
```

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
| Registry export | generated but never imported | imported with `regedit` before setting keys |
| `rebuild-prefix.sh` | under `set -e`, any failing `cp`/`mv ... 2>/dev/null` of an optional file (license cache, Design Data dir that doesn't exist yet, `wineserver -k` with nothing running) can abort the run | optional steps warn and continue |
| OGSFactory.dll patch | written blindly at fixed offsets | original bytes verified first; skipped on a different build; `scripts/ogs-patch.sh status|apply|revert` |
| WebView2 installer | expected in `/tmp`, never downloaded | downloaded to `downloads/` |
| Wine patch | `patch -p1` fails (absolute `/tmp/...` paths in header) | regenerated as a proper `a/ b/` patch |
| Logs | `~/Projects/Inventor on linux/logs` | `logs/` in the checkout |
| IPC cleanup | only `interprocess/01000000` | whole `interprocess/` (Open Problem #4) |
| `msquic=` override | documented, not set | set in `launch-inventor.sh` |
| Packages | `dxvk-mingw-git` via pacman (not in Arch repos) | official repos + `dxvk-bin` from AUR |

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
