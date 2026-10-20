# NixOS setup

The flake migration is under validation. Evaluation and installer boundary tests
pass; a complete Inventor build and GUI validation are still required before
this setup can be considered working.

The default target is Inventor Professional 2026 English with the 2026.4 update
and Content Center, on x86_64 Linux. The runtime builds Wine 11.20 with every
top-level patch in `patches/`. Nixpkgs and the nix-overlayfs fork are pinned in
`flake.lock`; no local checkout is required by the committed input definitions.
The consumer applies a checked-in patch to that pinned nix-overlayfs source to
register Wine 11.20's Mono 11.3.0 dependency. The same change is present in the
local development fork. A separate libgsf patch fixes empty OLE streams; it was
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

## Validation remaining

The GUI acceptance check must launch with fresh state, exercise the browser
sign-in handoff, create a part, save and reopen it, and exit cleanly. Passing
`nix flake check` alone does not establish Inventor compatibility.
