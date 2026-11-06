# Draft: updating existing prefixes without reinstalling

Status: draft (2026-11-06), not implemented. For Autodesk-Inventor-for-Linux
first, then the same library in Solidworks-for-Linux.

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
| 4 | Optional migration to native .NET 4.8, with a backup | after a test in a fresh prefix (Ubuntu VM) |
| 5 | The same in Solidworks-for-Linux | |

Each phase is tested with fake prefixes in a temporary HOME (no Wine) and
on the maintainer's prefix after a full copy of it.
