# Nix/NixOS work

Read `../docs/nixos.md` and `../flake.nix` before changing packaging. Use the
pinned inputs in `flake.lock`; prefer Nix-packaged dependencies. Builds run
without network: pin downloads with hashes and prefetch/link anything the
installation scripts need into `DOWNLOAD_DIR` in `inventor.nix`.

The main development effort happens within the scripted part of the repo.
To reduce maintenance burden, the Nix flake is updated on demand, adopting
fixes in batches so as to reach feature parity with the rest of the project.
Users in general move from tagged release to tagged release.

## Flake commands

Run from the repository root:

- `nix develop`: shell with the matching patched Wine and packaging tools.
- `nix flake check`: evaluate the flake and run installer/runtime-state checks.
- `nix build .#inventor-2026 --no-link -L`: build 2026.
- `nix build .#inventor-2027 --no-link -L`: build 2027.
- `nix run .#inventor-2026` / `nix run .#inventor-2027`: launch the chosen release.
- `nix build .#wine`: build the patched Wine runtime independently.
- `nix build .#inventor-2026-media` / `.#inventor-2027-media`: extract the selected installation image.
- `nix fmt -- flake.nix nix/*.nix`: format Nix expressions.
- `nix log /nix/store/<name>.drv`: inspect a failed build.

Import original Autodesk downloads with `nix-store --add-fixed sha256 FILE`;
the extraction launcher EXE is unnecessary, but the update EXE is required.
Add new source files to Git before building, or use `path:$PWD` as the flake
reference to include untracked files.

## All builds and tests run through Nix

Every build and test for Nix/NixOS work must be defined in this repository's
Nix pipeline and executed through its named flake outputs. This includes early
diagnostics, experimental patches, synthetic reproducers, regression tests,
syntax checks, unit tests and GUI validation, not just final acceptance tests.

- Add or extend a named flake package, check or app before running the work.
  Build with `nix build .#<package>`, run automated checks with
  `nix flake check` or `nix build .#checks.<system>.<check>`, and run interactive
  tests through `nix run .#<app>`. Use the pinned inputs for all dependencies.
- Do not compile with host tools, invoke test scripts directly, use ad hoc
  `nix build --expr` overrides, or build/test from temporary source or patch
  copies. `nix develop` is for development tooling, not an exception allowing
  untracked build or test commands. Nix derivations may use their own temporary
  build directories normally.
- Package diagnostic programs and their runners in Nix too. GUI automation may
  use the isolated agent workspace and its screenshot/input tools, but it must
  launch a Nix-defined test app or runner using the intended packaged runtime.
  Do not edit generated launchers or replace their runtime paths by hand.
- Define experimental package/app outputs and connect their runtime from the
  outset. Keep unfinished patches out of the default runtime. For an Inventor
  fix, exercise the composed Inventor package and launcher, not only Wine or a
  standalone reproducer. Verify which runtime the launcher actually selects.
- Build, test and hand over the same named outputs. Finalize patch contents,
  headers, source paths and runtime wiring before an expensive build; changes
  to these can invalidate reuse even when executable code is unchanged.
  Reuse cached outputs and installation layers through Nix where supported.
  Do not reinstall Autodesk manually or copy authenticated prefixes.
- Record exact flake targets and tested store paths. Distinguish evaluation,
  compilation and GUI validation; passing `nix flake check` or building Wine
  alone does not establish that the composed Inventor package was tested.
  If the pipeline lacks a required test, add it before running that test. If
  blocked, report the missing Nix integration rather than bypassing it.
- once the experimental outputs have been verified, merge them into existing ones
- while modules like `wine.nix` have automatic loading, additional draft patches should be supplied there explicitly during testing.

## Overlay filesystem

We use the pinned `nix-overlayfs` library to compose Wine dependency layers and
Inventor's installed application layer from the read-only Nix store. At launch,
a FUSE overlay combines these lower layers with a persistent writable upper
layer for that release, presenting Wine with one complete `WINEPREFIX`.
Writes copy files into the upper layer; deleting a lower-layer file records a
whiteout rather than modifying the store. The temporary mount is removed on
exit, while user changes persist across launches and package rebuilds. Upper
files can therefore override newer packaged files; preserve user state and
check for stale overrides when diagnosing upgrade problems.

The persistent state directory alone is not the complete prefix. Run Wine tools
against the mounted composition with the launcher's matching Wine runtime.
Each release has its own state. nix-overlayfs allows one session per writable
layer: it locks the state before the registry merge and the mount, keeps the
lock out of Wine's processes, refuses a second launch with exit status 75,
and runs the session (Inventor's licensing and Identity Manager services
included) in its own PID namespace so that nothing outlives it. Do not add a
lock of our own in the launch scripts (Wine would inherit it). `launch-state.sh`
only sets the release and its state directory. The licensing database is kept
on the native filesystem under `.nix-overlayfs/licensing-data` and linked into
the composition because it needs memory-mapped access outside the FUSE overlay.

## The writable layer is state, not configuration

Nothing that the package provides is written into the writable layer, so
that every installation stays reproducible from its layers. Registry values
and files that the package wants in the prefix go into a layer: the
installation layer (`post-install.sh`) when they need the installed files,
otherwise the config layer (`config-layer.sh`). The launch scripts do not run
`wine reg add` or `wine reg delete`, and do not copy package files into the
prefix. The writable layer holds only what Inventor and the user write.

nix-overlayfs merges the registry three-way at launch: a value that the user
never changed follows the layers, so a changed packaged value reaches
existing users, and a value that the user changed, added or deleted is kept.
`tests/test_runtime_state.py` checks that the launcher writes no registry
values.

A launch writes no package settings into the writable layer. It also does
some nix-overlayfs bookkeeping, which the nix-overlayfs README describes:
merge and session metadata in `.nix-overlayfs`, the directory skeleton of the
writable layer, the handling of shadowed files, and the removal of markers and
shims that older launchers left behind. Apart from that, it still writes these,
each for a stated reason:
- nix-overlayfs's registry merge writes the merged hives, because Wine keeps
  the registry in single files that a file overlay cannot combine. Its other
  integration settings (WineBrowser, URL schemes, the update marker, the
  `start.exe` shim) come from a layer that it generates for each launcher.
  URL schemes that are only discovered at launch, or whose program lies
  outside `drive_c`, are still registered at launch; Inventor's
  `adskidmgr` is neither.
- The licensing database lives on the native filesystem, because the
  licensing service memory-maps it, and a link in the prefix points to it.
  It is the user's licensing state, and the link target depends on the
  host's `$XDG_DATA_HOME`.
- The launcher resets the per-user IDSDK IPC folder: it holds data of one
  session only.
- The launcher seeds `RealDWGSettings.xml` and creates the per-user `Addins`
  folder in the profile `users/$USER`, because the layers are built as
  `users/nixbld`. Wine names the profile after `$USER`. Running Wine under
  the build's name would remove this exception, but it would also leave the
  existing users' profiles (settings, sign-in data) behind. So it waits for
  a migration of the state.
- The launcher creates the public `Macros` folder, because nix-overlayfs
  drops empty directories when it captures a layer.

Earlier launchers wrote some values into existing states: the Tahoma to
Segoe UI substitution, the graphics driver, and the Shared Components values
and Path. These stay there until a cleanup.

## Prefix setup without migrations

The installation layer runs `install-from-image.py` and `post-install.sh`.
Fixed settings (fonts, WebView2, X11) are in the separate `inventor-config`
layer (`config-layer.sh`). The script migrations are not run. Instead, every
migration gets an entry in `migrations.nix`, and `migration-parity` warns
about a migration without one. Do not ignore that warning: it means that the
Nix package lacks that change. Put a new setting in the config layer unless
it needs the installed files, because a change to `post-install.sh`
reinstalls Inventor.

The installation is one layer: install image, update and post-install.sh
(diagrams and rebuild table: [LAYERS.md](LAYERS.md)). Do not split the update
into its own layer: nix-overlayfs drops the MSI cache (`windows/Installer`)
that an MSP update needs, and layer builds (direct mode) cannot delete files
of a lower layer. Wine is the one duplicated input: `winum-install` builds
the layers, and `winum` is the Wine that runs Inventor (both named by winum's
release tag, now winum-11.22-3). Inventor is reinstalled by any of these:
updating nixpkgs, nix-overlayfs or winum-install, a new Autodesk update, or
editing the files in `installerSource` or `post-install.sh`. Batch such
updates and say so in the commit. A value that must follow the installation
(like the Shared Components version) is written by `post-install.sh` and
reaches existing users through the three-way registry merge.

## Runtime and integration

- `nixosModules.default` provides `programs.autodesk-inventor`; `versions`
  selects releases explicitly (default `[ ]`, installs nothing). `lib.mkInventor` accepts custom media.
- Each release has persistent writable state in
  `$XDG_DATA_HOME/autodesk-inventor-<year>` (default `~/.local/share`), with
  logs in `$XDG_STATE_HOME/autodesk-inventor-<year>` (default `~/.local/state`).
  Preserve sign-in, licensing data, settings, and documents during upgrades.
- Use system graphics (`/run/opengl-driver`). X11/XWayland is the validated
  path; native Wayland remains experimental (a separate package:
  `inventor-2027.withArgs { wineDriver = "wayland"; }`, whose config layer
  names the Wayland driver). Build success alone is not GUI
  validation. For GPU changes, verify 2026 before testing 2027.
- Never upload Autodesk media, extracted images, application packages, or
  containing system closures to a public binary cache. Never copy authenticated
  prefixes into disposable test directories; use fresh state or test in place.
