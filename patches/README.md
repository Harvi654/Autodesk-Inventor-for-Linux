# Patches

The Wine patches are in [winum](https://github.com/Harvi654/winum) since
winum-11.20-1 (`patches/series` there); `wine/version.env` names the
release this project uses. This project's former Wine patches and build are
kept in [docs/archive/own-wine-build/](../docs/archive/own-wine-build/README.md).

- `libgsf/libgsf-empty-stream.patch`: libgsf 1.14.59 rejects valid empty OLE
  streams, which crashes msitools; the flake's libgsf overlay applies it
  (`flake.nix`). It is under libgsf's license (LGPL 2.1 or later), not the
  MIT license of the rest of this repository.
