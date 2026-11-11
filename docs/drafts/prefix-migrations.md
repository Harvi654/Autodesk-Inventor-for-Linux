# Draft: updating existing prefixes without reinstalling

Status: phases 1-3 implemented (2026-11-11, `scripts/lib/migrations.sh`,
`scripts/lib/migrations/README.md`); phase 4 proposed below; phase 5 open.
For Autodesk-Inventor-for-Linux first, then the same library in
Solidworks-for-Linux.

What the implementation does differently from the plan below:
- Phase 1 moved `finish-install.sh`'s whole setup into one step (0001),
  unchanged, instead of splitting it into many: it only runs at
  installation, and splitting it would have changed tested code for no
  user. New changes are new steps.
- The launcher runs the pending steps itself (non-optional ones only)
  instead of offering them: it starts from the app menu, without a
  terminal to ask in. Optional steps run only by name.
- The Wine runtime: `wineboot -u` does not replace the copies of Wine's
  builtin DLLs in `system32` (measured with winum-11.20-1), so they tell
  which Wine *made* a prefix, not which one last updated it. The prefix's
  state records the runtime (`runtime=`); step 0002 and the launcher write
  it. `rollback-wine.sh` is not written.
- concrt140 and optional GPU ray tracing are not steps yet; vkd3d-proton
  with the ray payload fix waits for a release from winum.

## Problem

"Update project and Wine" (GUI) runs `update-project.sh`, `get-wine.sh`
and `install-desktop-integration.sh`. Everything that lives in the prefix
(registry, DLL overrides, DXVK, vkd3d-proton, WebView2, fonts, disabled
add-ins, GLX, later native .NET 4.8 or concrt140) is set only by
`finish-install.sh` at installation, so an existing user gets a change only
by reinstalling.

## Design: numbered prefix migrations

1. **One source of truth.** The prefix setup is split into numbered steps,
   `scripts/lib/migrations/NNNN-<what>.sh`. A new installation runs all of
   them; an update runs only those the prefix has not had. A change is
   always a new file, never an edit of an old one.
2. **The prefix records its state** in
   `<prefix>/.inventor-on-linux/state`: last step, component versions
   (Wine runtime, DXVK, vkd3d-proton, WebView2, ...), dates.
3. **Every step is idempotent and backs up** what it changes (registry
   files, replaced DLLs) to `<prefix>/.inventor-on-linux/backup/<step>/`.
   On failure it restores the backup and the update stops with a clear
   message; a prefix is never left half changed.
4. **Updating:** the GUI button and `scripts/upgrade.sh` update the project,
   Wine, all prefixes' migrations and the launcher in one go. The launcher
   compares the prefix with the project at every start and offers to run
   the missing steps (seconds; nothing is reinstalled).
5. **Wine runtime:** a new winum build is downloaded next to the old one;
   the prefix records which one it uses; `wineboot -u` once after a change;
   the previous runtime stays for `scripts/rollback-wine.sh` until the new
   one is confirmed.
6. **Large changes are optional and confirmed:** native .NET 4.8 (replacing
   wine-mono cannot easily be undone: full prefix backup or btrfs snapshot
   first, can be skipped); GPU ray tracing only on a card that has it.
7. **Guard:** a test in `tests/` fails when prefix setup changes outside a
   migration; AGENTS.md gets the rule "every prefix change is a new
   migration file".
8. **SOLIDWORKS** uses the same library (state, backups, runner); the Nix
   flake runs it at launch too.

## Phases

| Phase | Content | For the user |
| --- | --- | --- |
| 1 | Migration library and prefix state; `finish-install.sh` split into steps with unchanged behaviour; existing prefixes get a step 0 that records them as current | nothing changes yet |
| 2 | GUI update and launcher run migrations, with backups and rollback | from here on every change arrives by itself |
| 3 | First real migrations: winum runtime, native concrt140, vkd3d-proton with the ray payload fix, optional GPU ray tracing | first update without reinstalling |
| 4 | Optional migration to native .NET 4.8, with a backup | after a test in a fresh prefix (Ubuntu VM) - proposal below |
| 5 | The same in Solidworks-for-Linux | |

Each phase is tested with fake prefixes in a temporary HOME (no Wine) and
on the maintainer's prefix after a full copy of it.

## Phase 4 (proposal): .NET Framework 4.8 for an existing prefix

New installations get .NET 4.0 + the image's 4.8 from `install-from-image.py`
(since 2026-11-11). An existing prefix with wine-mono gets it only as an
**optional** step, `0005-dotnet48`, run by name:

```bash
INV_PREFIX=... INV_YEAR=... bash scripts/migrate-prefix.sh --run 0005 --image <Inventor install image>
```

- Why optional: replacing wine-mono cannot be undone step by step
  (uninstall entries, NDP keys, `mscoree.dll`, a .NET tree under
  `windows/Microsoft.NET`, the GAC). The step needs the install image (the
  4.8 installer is in it) and takes minutes.
- Backup: the whole prefix, not a few files - `cp -a --reflink=auto` into
  `<prefix>.before-dotnet48` (instant on btrfs/XFS; on other file systems a
  full copy, so the step checks free space first and says how much it
  needs), or a btrfs snapshot when the prefix is a subvolume. On failure the
  prefix is replaced by that copy; on success the copy stays until the user
  removes it (`migrate-prefix.sh --forget-backup 0005`).
- What it runs: the same code as the installer (`install_dotnet48` in
  `install-from-image.py`: remove wine-mono, .NET 4.0, the image's 4.8, the
  checks), then `finish-install.sh`'s add-in step for Anark/Publisher.
- Not from the launcher or an update; the launcher may say once that 3D PDF
  needs it.
- Test before it is offered: a copy of an old prefix (as for phases 1-3),
  then 3D PDF, Property Mapping, Stress Analysis and the usual smoke test.

