# Prefix migrations

Numbered steps that bring an Inventor Wine prefix to what this project sets
up today, so an existing installation gets a change without reinstalling.
The runner is `scripts/lib/migrations.sh`; `scripts/migrate-prefix.sh` is
the command, and `finish-install.sh` (installation), `launch-inventor.sh`
(every start) and the GUI's "Update" run it. Design:
`docs/drafts/prefix-migrations.md`; write-up: `docs/arch-hyprland.md`,
"Prefix migrations".

**Rule: every change to what a prefix gets is a new file here, never an
edit of an old one** (AGENTS.md). `SHA256SUMS` lists every file with its
hash; `tests/test_migrations.py` fails when a listed file changes or a file
is missing from the list. Add a step, then add its line:

```bash
cd scripts/lib/migrations && sha256sum [0-9][0-9][0-9][0-9]-*.sh > SHA256SUMS
```

## A step

`NNNN-<what>.sh`, sourced by a new `bash -Eeuo pipefail` for the prefix in
`WINEPREFIX` (common.sh, configure.sh and migrations.sh are loaded):

- `MIG_DESC` - one line for the log;
- `mig_apply` - the change; any failing command stops it;
- `mig_needed` (optional) - return 1 when the prefix already has it; the
  step is then recorded as done without changing anything;
- `MIG_BACKUP` (optional) - paths relative to the prefix to save first
  besides the registry files (`system.reg`, `user.reg`, `userdef.reg`,
  always saved); `none` saves nothing (installation-time steps only);
- `MIG_OPTIONAL=1` - run only when asked for by name
  (`migrate-prefix.sh --run NNNN`), never from the launcher or an update.

If a step fails, what was saved is put back and the run stops. The state
is `<prefix>/.inventor-on-linux/state` (`done.<step>=<date> applied|already
so|adopted`, `runtime=` the Wine the prefix was last updated for); the
backups are in `<prefix>/.inventor-on-linux/backup/<step>/`.

## Steps

| Step | What | Since |
| --- | --- | --- |
| 0001-base-setup | the whole setup `finish-install.sh` did before migrations, unchanged; prefixes from before are recorded as having it | 2026-11-11 |
| 0002-winum-runtime | `wineboot -u` for the Wine in use when the prefix was last updated for another one (this project's `wine-inventor-*`, the system's Wine), and the record of the runtime | 2026-11-11 |
| 0003-x11-driver-inventor | `UseEGL=N`, `ClientSideWithRender=N` for `Inventor.exe` (GPU ray tracing on GLX; the status bar text) | 2026-11-11 |
| 0004-enable-hydra | **optional** (`--run 0004` only): `EnableHydra=1` in Inventor's driver preferences (`RegistryVersion30.0` for 2026, `31.0` for 2027) - for a GPU with ray tracing hardware only; on an RX 580 it moved ray tracing to the CPU (~1200 % CPU, 2026-10-21) | 2026-11-11 |

## Planned, not written yet

- **0004 as a normal step** - waits for a check of the GPU (ray tracing
  hardware and the Vulkan extensions) and an L4 on a ray tracing card;
  until then it runs only by name.
- **vkd3d-proton with the ray payload fix** - waits for a release from
  winum: `build-vkd3d.yml` there builds it but publishes nothing yet. The
  step will download that release (pinned, SHA-256, also in
  `nix/inventor.nix`) and replace `d3d12.dll`/`d3d12core.dll`, with the old
  ones saved.
- **.NET Framework 4.8 for an existing prefix (phase 4, optional)** - see
  `docs/drafts/prefix-migrations.md`, "Phase 4".
