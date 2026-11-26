# Layers and dependencies of the Nix package

This page shows how `nix/inventor.nix` and `flake.nix` put Inventor together,
and what a change to each input rebuilds. Background: [AGENTS.md](AGENTS.md),
[../docs/nixos.md](../docs/nixos.md) ("Installation layer").

## What the launcher mounts

At launch, nix-overlayfs stacks read-only layers from the Nix store under one
writable layer per release (`~/.local/share/autodesk-inventor-<year>`). Files
and registry are combined in different orders
(nix-overlayfs `lib/mkOverlayfsPackage.nix`):

```mermaid
flowchart TB
    subgraph files["Files: the first layer that has a path wins"]
        direction TB
        f0["writable state"] --> f1["installation<br/>install image + update + post-install.sh"]
        f1 --> f2["vkd3d-proton"] --> f3["DXVK"] --> f4["inventor-config"]
        f4 --> f5[".NET Framework 4.8"] --> f6["WebView2"] --> f7["Wine base environment"]
    end
    subgraph registry["Registry: merged in this order, later values win"]
        direction TB
        r0["Wine base environment"] --> r1["WebView2"] --> r2[".NET Framework 4.8"]
        r2 --> r3["inventor-config"] --> r4["DXVK"] --> r5["vkd3d-proton"]
        r5 --> r6["installation"] --> r7["writable state"]
    end

    classDef install fill:#fde2c8,stroke:#c46a1b,color:#000
    classDef runtime fill:#d6ecd2,stroke:#3f7f36,color:#000
    classDef user fill:#dbe4f5,stroke:#3a5a9a,color:#000
    class f1,f5,f6,f7,r0,r1,r2,r6 install
    class f2,f3,f4,r3,r4,r5 runtime
    class f0,r7 user
```

Orange layers are expensive to rebuild (the installation takes hours); green
ones are small and rebuild in minutes.

This has two consequences:

- The writable state's registry is merged three-way. nix-overlayfs keeps a
  record of what the layers provided at the last merge. A value that the
  user never changed follows the layers, so a changed packaged value (a new
  Shared Components version, a changed setting in `inventor-config`)
  reaches existing users. A value that the user changed, added or deleted
  is kept. The launcher writes no registry values (nix/AGENTS.md).
- The installation's files and registry win over `inventor-config`, DXVK and
  vkd3d-proton where both have the same file or value. The layers are kept
  disjoint.

The installation is one layer on purpose: nix-overlayfs drops
`windows/Installer` (the MSI cache that an MSP update patches against) from a
captured layer, and its builds cannot record files deleted from a lower
layer. An update built as a separate layer would therefore fail, or bring
back the files it removes.

## What is built from what

```mermaid
flowchart LR
    subgraph inputs["Flake inputs"]
        np["nixpkgs"]
        no["nix-overlayfs"]
        wi_i["winum-install<br/>(tag winum-11.22-3)"]
        wi["winum<br/>(tag winum-11.22-3)"]
    end
    subgraph repo["This repository"]
        inst["install-from-image.py, odis.py, regf.py,<br/>bsdtar.env, libarchive license"]
        post["nix/post-install.sh"]
        cfgsh["nix/config-layer.sh, scripts/lib/common.sh,<br/>scripts/linux-fonts.sh, requirements.env/.py"]
        launch["nix/launch-*.sh"]
    end
    subgraph autodesk["Autodesk media (requireFile)"]
        media["install image"]
        upd["update EXE"]
    end

    wine["install Wine"]
    launchWine["launch Wine<br/>= install Wine while both name<br/>the same release, with no candidates"]
    envL["base environment"]
    wv2["WebView2"]
    net[".NET 4.8"]
    instL["installation"]
    cfgL["inventor-config"]
    gfx["DXVK, vkd3d-proton"]
    launcher["launcher<br/>inventor / inventor-2027"]

    np --> wine
    wi_i --> wine
    wine --> envL
    no --> envL
    envL --> wv2
    envL --> net
    wv2 --> instL
    net --> instL
    media --> instL
    upd --> instL
    inst --> instL
    post --> instL
    envL --> cfgL
    cfgsh --> cfgL
    envL --> gfx

    np --> launchWine
    wi --> launchWine
    instL --> launcher
    cfgL --> launcher
    gfx --> launcher
    launchWine --> launcher
    launch --> launcher

    wine -. "prefixCompatibility must match" .- launchWine
```

The launch Wine must make the same prefix as the install Wine, or evaluation
stops. The two are compared by `prefixCompatibility` in `nix/wine.nix`: the
winum release plus a hash of the release and candidate patches that change
prefix contents. The same rule applies to a winum checkout given as `winum`
to test candidates.

## What a change rebuilds

| Change | Rebuilds |
|---|---|
| `scripts/` other than the files below, docs | nothing (the `installer` check reruns the unit tests) |
| `common.sh`, `linux-fonts.sh`, `requirements.env`, `requirements.py`, `nix/config-layer.sh` | inventor-config, launcher |
| `nix/launch-*.sh`, DXVK or vkd3d-proton version | launcher (and that layer) |
| a code-only winum candidate under test | launch Wine, launcher |
| `winum` alone, to a release with the same `prefixCompatibility` | launch Wine, launcher (today only the same release qualifies) |
| new Autodesk update | **installation**, launcher |
| `install-from-image.py`, `odis.py`, `regf.py`, `bsdtar.env`, the libarchive license, `nix/post-install.sh` | **installation**, launcher |
| `nixpkgs`, `nix-overlayfs`, `winum-install` | everything from Wine up, **installation** included |

The changes in the bold rows reinstall Inventor, which takes hours. Those
inputs change often, so update them on purpose and in batches.
