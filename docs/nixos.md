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

The default flake target is Inventor Professional 2027 English with the 2027.1
update and Content Center, on x86_64 Linux. Inventor 2026 English with update
2026.4 is also available as a separate package. The runtime builds Wine 11.20 with the patches of
[winum](https://github.com/Harvi654/winum) `winum-11.20-2` (its `patches/series`,
in order; flake input `winum`, pinned to the tag's commit). Nixpkgs, the
nix-overlayfs fork and winum are pinned in `flake.lock`; no local checkout is required by the committed input definitions.
The base environment has no Wine Mono (`managedRuntime = "external"`):
.NET comes from the layer described below.

Two Wines are involved. The winum release of the flake input `winum-install`
builds the base environment and the WebView2, .NET and Inventor layers;
Inventor runs on the release of the input `winum` plus the winum candidates
listed in `wineCandidates` in `flake.nix` (with the same release and no
candidates, both are the same Wine). Trying a candidate that
changes only code therefore rebuilds Wine and the launcher, not the
installations: Wine loads a builtin DLL from its own installation when the
prefix holds Wine's copy of it, and the prefix is not updated automatically
at runtime. What a candidate changes in the prefix itself - `wine.inf`
(registry, files), COM registration, modules added or removed - would not
reach the layers, so `nix/wine-prefix.nix` looks for such changes in the
candidate patches and evaluation refuses them in `wineCandidates`. Those,
and candidates needed while installing (for example an msi fix), go into
`installWineCandidates`, which rebuilds the layers. The detection is a
heuristic over the patch text; a candidate that changes the prefix in
another way has to be put into `installWineCandidates` by hand. Candidates
come from the input `winum`. To test candidates from a winum checkout:

```nix
wineCandidates = [ "inventor-reference-model" ];
```

```sh
nix run .#inventor-2027 --override-input winum path:/path/to/winum
```

This rebuilds the launch Wine and the launcher only: the installations are
built from `winum-install`. The checkout must be at the same winum release
(its `wine/version.env`), since the launch Wine has to make the same prefix
as the install Wine.

Candidate series and patch files retain their path type when their source is
a local path. This lets `nix flake check --no-build --show-trace`, the CI
command, read the synthetic candidate fixture without first copying it into
the store. The `launch-wine-candidates` check also asserts that local candidate
patches remain paths, so a previously cached fixture cannot hide a regression.

The pinned library also preserves Wine's registry symbolic-link markers and
propagates failed installer exit statuses. Microsoft's .NET Framework 4.8
is a layer below the installation (nix-overlayfs's `dotnet-framework-4-8`,
pinned downloads), used instead of Wine Mono for the .NET Framework parts
such as 3D PDF and Import CAD's Property Mapping; the installer's own .NET
step is skipped in the Nix build. WebView2 is nix-overlayfs's pinned
`webview2` layer (154.0.4258.62, x64), built on the same base environment
(`modules.webview2.override { managedRuntime = "external"; }`); its build
checks that `msedgewebview2.exe` of that version and architecture is
installed. Moving to it from this flake's own WebView2 derivation rebuilt
the installation once. The Inventor base image, all 21 selected
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
nix build .#inventor-2026
nix run .#inventor-2026
```

For installer development, `nix build .#checks.x86_64-linux.installer`
runs the complete Python regression suite, checks each installer shell script's
syntax and compiles the Python sources. It uses synthetic images and fake Wine
executables; no Autodesk media or application build is needed. The check
provides iconv and standalone coreutils, and fixture scripts resolve their
shells from PATH while keeping the caller's executable search path. CI first
runs `nix flake check --no-build --show-trace`, then builds this check.

When developing with new files that have not yet been added to Git, use
`path:$PWD` as the flake reference, for example `nix build "path:$PWD#inventor-2026"`.

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
  # Select a version explicitly; the default [] installs nothing.
  programs.autodesk-inventor.versions = [ "2027" ];

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
  programs.autodesk-inventor.versions = [ "2027" ];
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

The module installs the application and desktop entries, enables NixOS
graphics and FUSE support, and associates `adskidmgr://` links with one
hidden handler, `autodesk-inventor-url-handler.desktop`. The handler gives a
callback to the installed release whose session is running (nix-overlayfs
forwards it to Identity Manager in that composed prefix) and starts the newest
release only when no release runs. If a running release cannot take the
callback, the handler reports that and stops rather than trying another
release. The module's launchers do not register their own
handlers at runtime, and remove the ones earlier launches wrote. Sign-in
requires your Autodesk account and license.

The enabled NixOS module owns this association; no separate Home Manager
association is needed. Remove any existing
`xdg.mimeApps.defaultApplications."x-scheme-handler/adskidmgr"` setting from
Home Manager and rebuild, so the module's system default can take effect.
A user default takes precedence over the system default, even when Home
Manager manages unrelated MIME types. In particular, an old association with
`autodesk-inventor.desktop` or a release-specific handler can bypass the
dispatcher and send a 2026 sign-in callback to 2027.

After activating the configuration, check the effective association:

```sh
xdg-mime query default x-scheme-handler/adskidmgr
```

It should report `autodesk-inventor-url-handler.desktop`. If it reports
another handler, check user MIME defaults in `~/.config/mimeapps.list` and
`~/.local/share/applications/mimeapps.list`. Enabling the module with at least
one selected release installs the dispatcher; changing only the MIME default
does not install it. When testing a fix from a pull request, the system flake's
Inventor input and lock must include that fix, and the rebuilt configuration
must be activated before testing browser sign-in.

Packages used without the module (`nix run .#inventor-2026` or
`nix run .#inventor-2027`) still register a
handler for their release at every launch, as before; `lib.mkInventor` accepts
`registerHostUrlHandlers = false`, and a package made with it has
`passthru.withArgs` to change such arguments.

A desktop entry in `$XDG_DATA_HOME/applications` (by default
`~/.local/share/applications`) with the same name as one of the module's
(`autodesk-inventor-2027.desktop`, ...) hides it: the menu
item then starts whatever that file names, for example an older launcher, or
one written by the script installer or `nix run`. At the start of each
graphical session the module's user service
`autodesk-inventor-desktop-check` reports such entries, the old
`...-wayland.desktop` ones, and `adskidmgr` handlers outside the module,
with the program each one starts (or the raw `Exec=` line when the program
cannot be found): always in the journal
(`journalctl --user -u autodesk-inventor-desktop-check`), and as a desktop
notification when the session has a notification service (best effort). It
changes nothing; remove or rename the files it names.
`programs.autodesk-inventor.checkUserDesktopEntries = false;` turns it off.

## Install both releases side by side

The flake defaults to 2027. The NixOS module defaults to `versions = [ ]`;
select releases explicitly. Enabling it with an empty list installs nothing
and does not register a browser callback. To install both releases:

```nix
programs.autodesk-inventor = {
  enable = true;
  versions = [ "2026" "2027" ];
};
```

Use `versions = [ "2027" ];` for 2027 only. Each release has its own desktop
entry, Wine prefix, licensing database, lock, settings, and logs. The commands
are `inventor` for 2026 and `inventor-2027` for 2027. From the checkout, use
`nix run .#inventor-2026` or `nix run .#inventor-2027`; `nix run` defaults to 2027.

Both releases share the `adskidmgr://` callback. The module's handler gives it
to the release that is running and asked for it; with neither running it
starts the newest. With both open, it goes to 2027 first, so complete sign-in
for one release at a time.

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

The writable state is an overlay above the Nix layers, and its files always
win. nix-overlayfs therefore keeps Wine from updating the prefix at runtime
(an update would copy Wine's own `d3d11.dll` and friends above DXVK), and
after a rebuild moves Wine builtin copies that hide a layer file to
`.nix-overlayfs/shadowed/<time>/`; other hiding files are listed in
`.nix-overlayfs/shadowed-files`. To check that DXVK is used, start with
`DXVK_HUD=1`. Directories of sessions that were killed are removed from
`~/.cache/nix-overlayfs/tmp` on the next launch.

Changes to the launcher alone (environment, DLL overrides, URL handling) no
longer rebuild the installed layers (since nix-overlayfs `543c070`; moving the
input past it rebuilt them once).

The prefix setup does not use the script installer's `finish-install.sh` and
prefix migrations (`scripts/lib/migrations/`); a Nix layer is built in one go,
so there is no older prefix to migrate. The installation layer runs
`install-from-image.py` and then `nix/post-install.sh` (what needs the
installed files: `Current` links, Shared Components registry, licensing SSO
plugin, default add-ins, crash sources, RealDWG settings). Settings that do
not, fonts (`linux-fonts.sh`), WebView2 and the X11 values for `Inventor.exe`,
are the separate `inventor-config` layer (`nix/config-layer.sh`): changing
them rebuilds that layer and the launcher, not the installation.
`nix/migrations.nix` says for every migration where the Nix package has it,
and the `migration-parity` check warns about a migration without an entry
there (a warning, so that the script installer's commits do not fail the Nix
checks).

### Installation layer

[nix/LAYERS.md](../nix/LAYERS.md) has diagrams of the layers and their
inputs, the order in which files and registry are combined, and a table of
what each change rebuilds.

The installation is one layer: the install image, its update and
`nix/post-install.sh` in one build. It stays one on purpose: nix-overlayfs
drops `windows/Installer` (the MSI cache an MSP update patches against) from a
captured layer, and its builds (direct mode) record files they add or change
but not files they delete from a layer below. An update built as a separate
layer would therefore fail to patch, or bring back the files it removes
(2027.1 moves 176 to `.inventor-on-linux/removed-by-update/`). So a new
Autodesk update reinstalls Inventor. For the same reason the rename of
`bcp47langs.dll`, a file of the Wine base environment, has never taken effect
in the Nix package.

The layer is built from the flake's inputs and, from this repository, only
the files it runs (`install-from-image.py`, `odis.py`, `regf.py`,
`bsdtar.env`, the libarchive license, `nix/post-install.sh`; the bsdtar
archive's URL and hash are read from `bsdtar.env`). Changes to those files,
to `nixpkgs`, `nix-overlayfs` or `winum-install` reinstall Inventor; other
edits in `scripts/` do not. Those inputs change often, so update them on
purpose and in batches rather than with every commit.

Wine has two inputs, both by winum's release tag (now `winum-11.20-2`):
`winum-install` builds the layers, `winum` is the Wine Inventor runs. The Nix
package does not read this repository's `wine/version.env` (the script
installer's release); the `winum-pin` check verifies that each input's tag
matches the release in winum's own `wine/version.env`. The launch Wine has to
make the same prefix as the install Wine (`prefixCompatibility` in
`nix/wine.nix`: the release plus a hash of the release and candidate patches
that change prefix contents), which today means the same release; while both
name it, they are one derivation.

The writable state's registry is merged after the layers', so a value an
existing user already has wins over a changed packaged default; a changed
setting in `inventor-config` reaches new users only (nix/LAYERS.md). The
values that name the installed Shared Components version are the exception:
the launcher writes them again at every start, so an update reaches existing
users.

DXVK (Direct3D 8-11) and vkd3d-proton (Direct3D 12) are not part of the
installation either: the launcher mounts them as separate layers (below the
installation in nix-overlayfs's order; they share no files with it), so a new
version rebuilds only the launcher. The defaults are DXVK 2.7.1 and winum's
vkd3d-proton 3.0.1-winum-1 (with the GPU ray tracing fixes), both pinned by
SHA-256. Their `native` overrides live in the layers' registry rather than in
`WINEDLLOVERRIDES`, so the prefix setup's exception for `msedgewebview2.exe`
(wined3d and Wine's d3d12, which WebView2 needs) still applies. To use other
builds:

```nix
inputs.inventor.lib.mkInventor {
  # ...media, year, version as above...
  dxvkLayer = modules.dxvkRelease {
    version = "2.7.2";
    src = pkgs.fetchurl { url = ".../dxvk-2.7.2.tar.gz"; hash = "sha256-..."; };
  };
  vkd3dLayer = modules.vkd3d-proton.override {
    archiveVersion = "3.0.2";
    archive = pkgs.fetchurl { url = ".../vkd3d-proton-3.0.2.tar.zst"; hash = "sha256-..."; };
  };
}
```

(`modules` is nix-overlayfs's module scope for the flake's install Wine.) The
script-based installer keeps installing both into the prefix as before; the
Nix installation does not run that part (`nix/post-install.sh` has no DXVK or
vkd3d-proton step).

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
- `nix build .#inventor --no-link --keep-failed -L` (now `.#inventor-2026`): passed.
- Application layer: `/nix/store/38y9yn20sg5nxi06fr6pfgh78v0a8g7l-inventor-2026.4`.
- Launcher: `/nix/store/kbrqwdmy6g8qmzd82s82x2fs137w6pgv-inventor-overlay-2026.4/bin/inventor`.
- `Inventor.exe`: PE signature and x86-64 machine type verified; 1,587,032 bytes.
- Required Noto Sans, Liberation Sans, and DejaVu Sans font files verified.
- All ten DXVK replacement DLLs retained in the captured layer (since
  2026-11-16 they are in their own layer, see above).
- NixOS module evaluation confirms graphics, FUSE, and callback defaults.
- Relative `Current` links resolve to installed licensing and Identity Manager versions.
- Library tests: portable reparse metadata, installer failure propagation, direct
  builds, namespace/FUSE ownership, shared helper/application credentials,
  runtime cleanup, and browser callback VM checks passed.

## Runtime evidence

On 2026-11-16, the contributor confirmed signing into Inventor 2026 with
2027 installed, tested directly on NixOS. The browser callback reached 2026
and sign-in completed. Before correcting the host integration, a stale user
MIME association bypassed the dispatcher and launched 2027 instead.

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

## Fonts and small UI text

The launcher checks actual host font families with `fc-list` and prefix font
files with `fc-scan`. If **Segoe UI** is available, it adds the Wine
`FontSubstitutes` entry `Tahoma=Segoe UI` for smoother system menu/status text.
This is conditional on the actual family, not Wine's Segoe-to-Noto alias or
Fontconfig's fallback matching. If Segoe UI disappears, that specific mapping
is removed; substitutions to other families are preserved. The check runs in
the composed prefix at launch, for both Inventor releases. Microsoft fonts are
not downloaded or included in the package by this change.

On 2026-11-10 the user confirmed the substitution improved Inventor 2027's UI.
ClearType settings alone had not helped: Wine's font trace showed smoothing
disabled by small Tahoma glyphs' GASP instructions. Explicit application
requests for Tahoma can remain unsmoothed; this changes system font selection.
See the [diagnosis and synthetic probe](arch-hyprland.md#hidpi--fractional-scaling).

Which fonts to provide:

| Fonts | Purpose and existing coverage |
|---|---|
| Segoe UI (regular, bold, italic, semibold as available) | Optional Windows UI family; needed for the conditional substitution. Supply it through your own host fonts or prefix. |
| Tahoma / Microsoft Sans Serif | Legacy UI families. Providing them does not itself solve small-text smoothing; free replacements already exist. |
| Arial, Times New Roman, Courier New | Useful for matching documents that name these fonts. Liberation Sans, Serif and Mono are already bundled as substitutes. |
| Calibri / Cambria | Optional for documents that use them; Carlito and Caladea substitutes are already bundled. |
| AIGDT / AMGDT | Autodesk engineering-symbol fonts. Verified present in the built Inventor 2027 application layer from the user's installation media; do not replace them with general-purpose sans fonts. |
| Other template/import fonts | Supply the specific families used by your drawings and templates when exact appearance matters. |

Autodesk documents [AIGDT as necessary for correct drawing symbols](https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Special-characters-and-symbols-are-not-displayed-correctly-in-drawings.html)
and explains that [DWG import maps source fonts to available Windows/TrueType families](https://help.autodesk.com/cloudhelp/2021/ENU/Inventor-Help/files/GUID-8AF446D5-3854-43B2-B88B-711E6AA2FF5F.htm).
The table distinguishes observed UI usage and document compatibility; it is not
an exhaustive inventory of every font requested by Inventor or its add-ins.
