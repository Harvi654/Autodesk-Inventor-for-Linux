# NixOS setup

The exact pinned Inventor package builds, and `nix flake check` passes.
The built application layer contains the verified x86-64 `Inventor.exe`,
packaged fonts, and valid licensing and Identity Manager links. Fresh-state
GUI validation is in progress; application compatibility is not yet proven.

The default target is Inventor Professional 2026 English with the 2026.4 update
and Content Center, on x86_64 Linux. The runtime builds Wine 11.20 with every
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

The small `001_002.exe` unpacker is unnecessary. The archive and update must
match the hashes in `nix/media.nix`. Installation runs from original media in a
build prefix; existing personal prefixes are not used as package sources.

```sh
nix flake check
nix build .#inventor
nix run .#inventor
```

When developing with new files that have not yet been added to Git, use
`path:$PWD` as the flake reference, for example `nix build "path:$PWD#inventor"`.

## Declarative integration

Add this project as an input to your system flake, import
`inputs.inventor.nixosModules.default`, and enable:

```nix
programs.autodesk-inventor.enable = true;
```

The module installs the application and desktop entry, enables NixOS graphics
support, and associates `adskidmgr://` links with the launcher. nix-overlayfs
forwards callbacks to Identity Manager in the active composed prefix and
provides browser integration. Sign-in requires your Autodesk account and license.

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
`${XDG_DATA_HOME:-~/.local/share}/autodesk-inventor-2026`.
Service logs are under `${XDG_STATE_HOME:-~/.local/state}/autodesk-inventor-2026`.
Do not delete existing writable state when testing upgrades. Use temporary XDG
data/cache/state directories for clean smoke tests.

The launcher defaults to automatic namespace selection. Keep the default host
security policy. For diagnostics, nix-overlayfs supports
`NIX_OVERLAYFS_NAMESPACE_MODE=direct` and opt-in
`NIX_OVERLAYFS_GRAPHICS_STACK=system` for `/run/opengl-driver`.

## Build evidence

Validated on 2026-10-20 with the library pinned to
`df35cc43f9d3c7e5605636455c8f3119407e7f27`:

- `nix flake check`: passed, including seven installer boundary/regression tests.
- `nix build .#inventor --no-link --keep-failed -L`: passed.
- Application layer: `/nix/store/7aajsbka0cqb3pnyyx6hamzqccg82sqg-inventor-2026.4`.
- Launcher: `/nix/store/n3d8lmy6c0m5pvivslsbk81j4dzrdmax-inventor-overlay-2026.4/bin/inventor`.
- `Inventor.exe`: PE signature and x86-64 machine type verified; 1,587,032 bytes.
- Required Noto Sans, Liberation Sans, and DejaVu Sans font files verified.
- Relative `Current` links resolve to installed licensing and Identity Manager versions.
- Library tests: portable reparse metadata, installer failure propagation, direct
  builds, and namespace/FUSE ownership VM checks passed.

## Validation remaining

The GUI acceptance check must launch with fresh state, exercise the browser
sign-in handoff, create a part, save and reopen it, and exit cleanly. Passing
`nix flake check` alone does not establish Inventor compatibility.
