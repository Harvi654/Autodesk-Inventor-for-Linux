# Retired sections of arch-hyprland.md (2026-11-08)

Moved here unchanged from `docs/arch-hyprland.md` when that file was
re-organised. They describe the first setup of this project, which copied an
existing Windows installation of Inventor (mounting the Windows disk,
exporting its registry, `rebuild-prefix.sh`), and findings that later work
replaced. Since v0.2 Inventor is installed from Autodesk's own download
(`scripts/install.sh`); the old scripts are still in `scripts/` and are
reviewed with the installer rework.

- "GPU ray tracing (Inventor 2027, not working yet)": superseded on
  2026-11-06, see "GPU ray tracing" in `docs/arch-hyprland.md`.
- "Registry import must be UTF-16": applies to importing a registry export
  of a Windows installation (`import-registry.sh`).

The original head of the file (before 2026-11-08):

> # Arch Linux + Hyprland
>
> Notes for running this project on vanilla Arch with the Hyprland compositor,
> with Windows (and Inventor) installed on a second disk in a dual-boot.
>
> The original setup was done on CachyOS. Everything Inventor-specific is the same;
> the differences are packages, mounting, and Wayland/XWayland details.

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

## GPU ray tracing (Inventor 2027, not working yet)

Tested 2026-10-21 on an RX 6400 (RDNA 2, on the Linux host via `INV_GPU=6400`,
monitor on the other card): Inventor 2027 runs on DirectX 12 through
vkd3d-proton, which reports `DXR 1.1 support enabled` and `DX Ultimate`;
Vulkan has `VK_KHR_ray_tracing_pipeline`, `acceleration_structure`,
`ray_query`. Inventor still greys out *Enable Viewport GPU Ray Tracing*
("The graphics card in use does not support this option") and never loads
`aurora.dll` (its GPU ray tracer). Ruled out: driver name/version (Wine does not
register `InstalledDisplayDrivers`; with `INV_DRIVER_NAMES=1` Diagnostics shows
"aticfx64 ... 35.0.21025.1024" instead of "Unknown", no change), Windows build,
no capability cached in the registry (`GraphicsUtil` has `UseGPURaytracing=1`).
Still open: DXVK answers an unknown `IDXGIAdapter` query `f0db4c7f-fe5a-42a2-
bd62-f2a6cf6fc83e` (possibly DXCore) right before vkd3d-proton starts. A test
with an NVIDIA RTX card would show whether this is AMD-specific.
