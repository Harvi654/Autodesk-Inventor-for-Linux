# This project's own Wine build (archived 2026-11-11)

Until winum-11.20-1, Inventor ran on a Wine this project built itself:
vanilla Wine with the patches in `patches/`, published as
`wine-inventor-<version>-<build>` (last one `wine-inventor-11.20-6`). Since
then Inventor uses [winum](https://github.com/Harvi654/winum), which took
over every patch here, gave each a Wine test checked on real Windows 10 (or
a recorded reason why there cannot be one) and publishes the release from a
signed tag. `wine/version.env` names the winum release; new Wine fixes go to
winum.

Nothing here is used by the installer, the launcher or the Nix packaging any
more. It is kept as the record of what the published `wine-inventor-*`
releases were built from (their source archives stay on the releases page).

| Here | Was | What it did |
| --- | --- | --- |
| `patches/*.patch` | `patches/` | the 27 Wine patches of `wine-inventor-11.20-6` (LGPL 2.1 or later, see `patches/README.md`) |
| `patches/debug/` | `patches/debug/` | diagnostic patches, never in a release |
| `patches/drafts/` | `patches/drafts/` | unfinished patches; their continuation is in winum |
| `scripts/build-wine.sh`, `scripts/lib/wine-patches.sh` | `scripts/` | the build of `wine-inventor-*` |
| `scripts/make-wine-source.sh` | `scripts/` | its source archive |
| `workflows/build-wine.yml` | `.github/workflows/` | the "Build Wine" workflow that published the releases |
| `scripts/build-wine-dll.sh`, `build-wbemprox.sh`, `rebuild-wine-fixes.sh` | `scripts/` | `INV_WINE=system`: single DLLs built from these patches and copied into Arch's Wine (the v0.1 way), with a pacman hook reminding to rebuild after Wine updates |

The scripts are kept as they were and do not run from here (they look for
`lib/common.sh` and `patches/` next to them). Fixes copied into Arch's Wine
by `build-wine-dll.sh --install` are removed by reinstalling Arch's `wine`
package (`scripts/uninstall.sh` offers it); the pacman hook by
`scripts/uninstall.sh` as well.

What changed in each patch on its way into winum is on winum's patch pages
(`docs/patches/<name>.md` there) and in `docs/release/winum-11.20-1.md`.
