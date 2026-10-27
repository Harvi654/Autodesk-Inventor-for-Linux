# Nix/NixOS work

Read `../docs/nixos.md` and `../flake.nix` before changing packaging. Use the
pinned inputs in `flake.lock`; prefer Nix-packaged dependencies. Builds run
without network: pin downloads with hashes and prefetch/link anything the
installation scripts need into `DOWNLOAD_DIR` in `inventor.nix`.

## Flake commands

Run from the repository root:

- `nix develop`: shell with the matching patched Wine and packaging tools.
- `nix flake check`: evaluate the flake and run installer/runtime-state checks.
- `nix build .#inventor --no-link -L`: build 2026 (also `.#inventor-2026`).
- `nix build .#inventor-2027 --no-link -L`: build 2027.
- `nix run .#inventor` / `nix run .#inventor-2027`: launch the chosen release.
- `nix build .#wine`: build the patched Wine runtime independently.
- `nix build .#inventor-media`: extract the default 2026 installation image.
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
Each release has its own state and launch lock. The licensing database is kept
on the native filesystem under `.nix-overlayfs/licensing-data` and linked into
the composition because it needs memory-mapped access outside the FUSE overlay.

## Runtime and integration

- `nixosModules.default` provides `programs.autodesk-inventor`; `versions`
  selects releases (default `[ "2026" ]`). `lib.mkInventor` accepts custom media.
- Each release has persistent writable state in
  `$XDG_DATA_HOME/autodesk-inventor-<year>` (default `~/.local/share`), with
  logs in `$XDG_STATE_HOME/autodesk-inventor-<year>` (default `~/.local/state`).
  Preserve sign-in, licensing data, settings, and documents during upgrades.
- Use system graphics (`/run/opengl-driver`). X11/XWayland is the validated
  path; native Wayland remains experimental. Build success alone is not GUI
  validation. For GPU changes, verify 2026 before testing 2027.
- Never upload Autodesk media, extracted images, application packages, or
  containing system closures to a public binary cache. Never copy authenticated
  prefixes into disposable test directories; use fresh state or test in place.
