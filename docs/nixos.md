# NixOS setup

> **Do not upload Inventor to a public binary cache.** The built Inventor package
> contains Autodesk’s proprietary software. Publishing it to Cachix or any other
> public binary cache would redistribute that software and must never be done.
> This also applies to Autodesk installation media, extracted images, application
> layers, and cache uploads of a system closure that includes Inventor.

The exact pinned Inventor package builds, and `nix flake check` passes.
The built application layer contains the verified x86-64 `Inventor.exe`,
packaged fonts, and valid licensing and Identity Manager links. Fresh-state
GUI validation passed browser sign-in and basic part creation, save, and reopen.
Broader application compatibility has not been validated.

The default target is Inventor Professional 2026 English with the 2026.4 update
and Content Center, on x86_64 Linux. Inventor 2027 English with update 2027.1
is also available as a separate package. The runtime builds Wine 11.20 with every
top-level patch in `patches/`. Nixpkgs and the nix-overlayfs fork are pinned in
`flake.lock`; no local checkout is required by the committed input definitions.
The pinned nix-overlayfs revision includes Wine 11.20's Mono 11.3.0 dependency
mapping and sandbox MSI link-action fix, published from the local development
fork. That base environment builds successfully with the patched Wine runtime.
The pinned library also preserves Wine's registry symbolic-link markers and
propagates failed installer exit statuses. The WebView2 layer has been built
and checked for its actual executable. The Inventor base image, all 21 selected
installation steps, the 2026.4 update, and final configuration completed in the
Nix sandbox. The library's opt-in portable directory-reparse support preserves
installer junctions without changing host security policy; its FUSE ownership
mapping allows runtime modification of packaged files.
A separate libgsf patch fixes empty OLE streams; it was
verified by rebuilding msitools with all 29 of its tests enabled and passing.

## Installation media

Obtain your own direct downloads from Autodesk. Import these original files:

```sh
nix-store --add-fixed sha256 ~/downloads/Inventor/Inventor_Professional_2026_English_Win_64bit_db_002_002.7z
nix-store --add-fixed sha256 ~/downloads/Inventor/Inventor_2026.4_Update.exe
```

For Inventor 2027, import its own archive and update instead (import both sets
when installing both releases):

```sh
nix-store --add-fixed sha256 ~/downloads/Inventor/2027/Inventor_Professional_2027_English_Win_64bit_db_002_002.7z
nix-store --add-fixed sha256 ~/downloads/Inventor/2027/Inventor_2027.1_Update.exe
```

The small `001_002.exe` unpacker is unnecessary. The archive and update must
match the hashes in `nix/media.nix`. Installation runs from original media in a
build prefix; existing personal prefixes are not used as package sources.
Autodesk media, updates, the installed application, and Microsoft WebView2 are
marked unfree. This application flake explicitly enables unfree packages in its
private Nixpkgs instance; it does not change your system-wide Nixpkgs policy.

```sh
nix flake check
nix build .#inventor
nix run .#inventor
```

When developing with new files that have not yet been added to Git, use
`path:$PWD` as the flake reference, for example `nix build "path:$PWD#inventor"`.

## Declarative integration

Requires x86_64 NixOS with flakes enabled and Vulkan-capable system graphics
drivers. Keep your existing Nixpkgs input, hardware configuration, and GPU driver
settings. Add the following sections to your system configuration.

### 1. Add the flake input

Inside your system `flake.nix`, add this alongside your existing inputs:

```nix
inputs.inventor.url = "github:Harvi654/Autodesk-Inventor-for-Linux";
```

Commit the resulting `flake.lock` so the repository revision is pinned. Leave
Inventor's own Nixpkgs input pinned as supplied by this project.

### 2. Wire the module into your host

In the same `flake.nix`, include `inputs` in the outputs arguments and add both
the project's module and a local `inventor.nix` module to your existing host's
`modules` list. Replace `your-host` with your existing configuration name:

```nix
outputs = inputs@{ nixpkgs, ... }: {
  nixosConfigurations.your-host = nixpkgs.lib.nixosSystem {
    system = "x86_64-linux";
    modules = [
      ./configuration.nix
      inputs.inventor.nixosModules.default
      ./inventor.nix
    ];
  };
};
```

Create `inventor.nix` beside your system flake:

```nix
{ lib, ... }:
{
  programs.autodesk-inventor.enable = true;

  # Optional narrow system policy; the default package also works without it.
  nixpkgs.config.allowUnfreePredicate = pkg:
    builtins.elem (lib.getName pkg) [
      "inventor"
      "inventor-overlay"
    ];
}
```

`inventor` names the installed application layer; `inventor-overlay` names the
launcher package. The flake already enables its proprietary Autodesk media,
update, and Microsoft WebView2 dependencies in its own private Nixpkgs instance,
so you do not need to list those sources in your system's predicate or set
`nixpkgs.config.allowUnfree = true` globally. The predicate above is optional;
if you already maintain an allowlist, add these two names to it instead of
replacing it. If you already enable all unfree packages, omit the predicate.
For the minimal setup, `inventor.nix` can contain just:

```nix
{
  programs.autodesk-inventor.enable = true;
}
```

For a local checkout, use `path:/absolute/path/to/Autodesk-Inventor-for-Linux`
as the input URL instead. The initial build compiles patched Wine and can take
substantial time and disk space.

### 3. Rebuild and launch

After importing the installation media above, rebuild your system and launch
Inventor (replace the path and `your-host`):

```sh
sudo nixos-rebuild switch --flake /path/to/system-flake#your-host
inventor
```

Or select **Autodesk Inventor 2026** in your application menu. Complete first
sign-in in your normal browser and allow the Autodesk callback to open Inventor.

The module installs the application and desktop entry, enables NixOS graphics
and FUSE support, and associates `adskidmgr://` links with the launcher. nix-overlayfs
forwards callbacks to Identity Manager in the active composed prefix and
provides browser integration. Sign-in requires your Autodesk account and license.

If Home Manager already manages your user MIME defaults, set its association
too; a user default takes precedence over the system default:

```nix
xdg.mimeApps.defaultApplications."x-scheme-handler/adskidmgr" = "autodesk-inventor.desktop";
```

## Install both releases side by side

The NixOS module keeps the existing 2026-only default. To install both releases:

```nix
programs.autodesk-inventor = {
  enable = true;
  versions = [ "2026" "2027" ];
};
```

Use `versions = [ "2027" ];` for 2027 only. Each release has its own desktop
entry, Wine prefix, licensing database, lock, settings, and logs. The commands
are `inventor` for 2026 and `inventor-2027` for 2027. From the checkout, use
`nix run .#inventor-2026` or `nix run .#inventor-2027`; `.#inventor` remains 2026.
Native Wayland remains experimental for both releases.

The module's browser callback default selects the newest installed release.
If Home Manager manages MIME defaults and you install 2027, use
`"autodesk-inventor-2027.desktop"` instead of `"autodesk-inventor.desktop"`.
The launcher also registers a release-specific callback handler when started;
complete sign-in for one release at a time when both are open.

For custom 2027 media, set `programs.autodesk-inventor.packages."2027"` to a
package made with `inputs.inventor.lib.mkInventor { year = "2027"; ...; }`.
The existing `programs.autodesk-inventor.package` override still targets 2026.

For other fixed-output media sources or to omit Content Center, use a package
constructed with the flake library:

```nix
programs.autodesk-inventor.package = inputs.inventor.lib.mkInventor {
  media = myUnpackedMedia; # derivation containing manifest/app.inventor.xml
  updates = [ myUpdateInstaller ];
  version = "2026.4";
  contentCenter = false;
};
```

The sources should be hash-pinned fetchers or `requireFile` derivations.
Changing an update or runtime rebuilds immutable layers; login and application
settings remain in nix-overlayfs's writable state at
`${XDG_DATA_HOME:-~/.local/share}/autodesk-inventor-2026` or
`${XDG_DATA_HOME:-~/.local/share}/autodesk-inventor-2027`.
Service logs are under `${XDG_STATE_HOME:-~/.local/state}/autodesk-inventor-<year>`.
Do not delete existing writable state when testing upgrades. Use temporary XDG
data/cache/state directories for clean smoke tests.

The launcher prepares each release's writable public `Macros` directory and
per-user `Addins` directory before startup, preserving existing files.

Launchers prevent overlapping sessions that share this state. The licensing
database is linked to `.nix-overlayfs/licensing-data/AdskLicensingService.sds`
inside the writable state directory so its memory-mapped file stays outside the
overlay mount. The first launch migrates the existing database without resetting
sign-in. Include this directory when backing up your installation's user state.

The launcher defaults to automatic namespace selection and the system graphics
stack at `/run/opengl-driver`. Keep the default host security policy. Diagnostics
can select `NIX_OVERLAYFS_NAMESPACE_MODE=direct` or
`NIX_OVERLAYFS_GRAPHICS_STACK=auto`.

## Build evidence

Validated on 2026-10-20 with the library pinned to
`8bf7c5cfa2541cf1478b87b519dcdc4c75831407`:

- `nix flake check`: passed, including seven installer boundary/regression tests.
- `nix build .#inventor --no-link --keep-failed -L`: passed.
- Application layer: `/nix/store/38y9yn20sg5nxi06fr6pfgh78v0a8g7l-inventor-2026.4`.
- Launcher: `/nix/store/kbrqwdmy6g8qmzd82s82x2fs137w6pgv-inventor-overlay-2026.4/bin/inventor`.
- `Inventor.exe`: PE signature and x86-64 machine type verified; 1,587,032 bytes.
- Required Noto Sans, Liberation Sans, and DejaVu Sans font files verified.
- All ten DXVK replacement DLLs retained in the captured layer.
- NixOS module evaluation confirms graphics, FUSE, and callback defaults.
- Relative `Current` links resolve to installed licensing and Identity Manager versions.
- Library tests: portable reparse metadata, installer failure propagation, direct
  builds, namespace/FUSE ownership, shared helper/application credentials,
  runtime cleanup, and browser callback VM checks passed.

## Runtime evidence

A fresh test state under `/tmp/inventor-flake-qa/data4` launched Inventor 2026.4,
displayed its licensing UI, handed sign-in to the user's normal browser, and
received the callback. Identity Manager reported a valid login, and the main
Inventor window opened. The user's original browser callback association was
restored afterward. Normal exit returned status 0 in both software-graphics and
system-graphics tests. System graphics detected the NVIDIA RTX 3060.

The user then ran the exact launcher above on the normal desktop with system
graphics and the separate authenticated test state. They confirmed creating a
basic part, saving it, closing and reopening it, and exiting Inventor. The saved
`nix-flake-smoke.ipt` is 132,608 bytes with the expected OLE compound-file header
(`d0cf11e0a1b11ae1`), SHA-256
`74e1513cb8c460b12322162e08f83bf45a33a20b295008d62c36164998f7ad1a`.
This completes the basic runtime smoke test; broader Inventor features and
performance have not been validated.

The hidden Xvfb desktop still stops at “Loading…” when creating a standard part
with either graphics setup. Its cause remains undetermined; the successful
normal-desktop test establishes the supported smoke-test result. The isolated
desktop was stopped, and the authenticated test state was preserved.

## Native Wayland limitation

Use the regular **Autodesk Inventor 2026** desktop entry on Wayland desktops;
it runs through XWayland and is the validated configuration. Native fractional
scaling is currently unavailable with this setup.

**Autodesk Inventor 2026 (Wayland)** remains an experimental entry and is not
working yet. It explicitly selects Wine’s `wayland` driver. On 2026-10-20 the
user confirmed that a window appears, but remains unresponsive after resolving
a separate sign-in/licensing issue. Native Wayland is therefore not a usable
alternative to the regular launcher at present. Close Inventor before changing
launchers because they share persistent state and the running Wine session.

## Experimental GPU ray tracing

GPU ray tracing rendered the sample `madeinlinux.ipt` successfully in Inventor
2026.4 on an NVIDIA RTX 3060 with the system Vulkan driver. The isolated X11 desktop showed a
ray-traced viewport and the **GPU** progress panel completed its Low-quality
render in about two seconds; High quality completed in about twelve seconds.
This verifies the complete shader and shared-texture
path, beyond the standalone DXR capability checks. Other GPUs and large assemblies
have not been validated.

The experimental package adds patched Nixpkgs vkd3d-proton 2.14.1 Windows DLLs
and DXVK to the application layer. This overrides the normal installer's pinned
vkd3d-proton 3.0.1 for the experimental launcher only. It uses system Vulkan
drivers and reuses the application layer without rerunning the Autodesk installer. Try it from this checkout:

```sh
nix run .#inventor-rt
```

Close Inventor before switching launchers. This uses the normal authenticated
user state and sets Inventor 2026's `Driver\EnableHydra` preference to `1` before
startup. Scoped Wine, DXVK, and vkd3d-proton compatibility patches fix Autodesk's
OpenGL context setup, ray-payload matrix shader translation, and D3D12-to-D3D11
shared textures. The ordinary launcher does not set the Hydra preference;
Inventor may change it after its capability checks. To restore the prior value,
see [the runtime helper notes](../runtime/README.md).

The RT launcher selects Wine’s GLX backend for Inventor on X11. On the tested
NVIDIA/Xwayland stack, EGL fails the alpha-capable pixel-format check and can
cause Application Options to disable GPU ray tracing. GLX passes that check.
The user confirmed startup on the normal desktop after this change and repair
of a separate stale X11 socket. The launcher does not alter desktop sockets.

In Inventor, enable **Tools → Application Options → Hardware → Viewport GPU
Ray Tracing**, open a solid part, choose **View → Visual Style → Realistic**,
and enable **Ray Tracing**. The progress panel should say **GPU**.

For opt-in NixOS integration:

```nix
programs.autodesk-inventor = {
  enable = true;
  gpuRayTracing = true;
};
```

This selects the GPU-enabled package for each release in `versions`: `inventor-rt`
for 2026 and `inventor-2027-rt` for 2027. Registry preferences, shader caches, and
renderer logs remain separate by release. The 2027 GPU target is experimental
and has not yet passed the viewport test. After the upstream rebase on
2026-10-21, 2026.4 again completed a GPU render in two seconds, and opening and
closing Application Options preserved GPU mode with its Hardware checkbox
enabled and checked. Interactive verification on the normal desktop is pending.
If you override `package` or `packages`, also pass `gpuRayTracing = true` to
`lib.mkInventor`.
The native Wayland limitation above still applies.

Try 2027 with `nix run .#inventor-2027-rt` after closing any running 2027
session. Its launcher builds and starts using its separate sign-in state, but
the hidden X11 test remains at “Loading…” with repeated D3D12 swapchain errors
(`E_INVALIDARG`, invalid format). The ordinary 2027 launcher also failed to
complete sample loading on the same hidden display; this comparison does not
establish the cause. GPU rendering in 2027 is not yet verified.

`nix run .#dxr-check` checks DXR support in an ephemeral prefix.
`nix run .#shared-texture-check` checks the D3D12-to-D3D11 texture handoff. For Autodesk
plugin diagnostics, build `.#dxr-check-inventor` and follow the
[runtime helper notes](../runtime/README.md). Shader caching is under
`$XDG_CACHE_HOME/autodesk-inventor-2026/vkd3d`, and renderer logs are under
`$XDG_STATE_HOME/autodesk-inventor-2026/vkd3d.log`, with the usual `~/.cache`
and `~/.local/state` defaults. Substitute `2027` for the 2027 launcher.
A missing renderer log can mean Inventor has
not attempted D3D12 initialization.

The reusable installation, runtime configuration, and diagnostic sources live
in `runtime/`; the Nix expressions provide packages and launcher wiring.
