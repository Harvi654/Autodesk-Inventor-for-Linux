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
  always saved): a word list, or one path per line for paths with a space
  (`Program Files`, 0010); a path that does not exist yet is recorded and
  removed again on a restore; `none` saves nothing (installation-time
  steps only);
- `MIG_OPTIONAL=1` - run only when asked for by name
  (`migrate-prefix.sh --run NNNN`), never from the launcher or an update.

If a step fails, what was saved is put back and the run stops. A step
whose `mig_apply` returns 75 (`MIG_DEFER`) cannot be done now for a reason
outside the prefix - a download while offline (0006): what was saved is
put back, the step is not recorded as done, the run (and the launcher)
goes on, and automatic runs try it again after 24 hours
(`MIG_DEFER_HOURS`); `--run NNNN` tries it at once. The launcher runs the
migrations at every start, so a step there must never need the network to
let Inventor start. The state
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
| 0005-inventor-registration | `Inventor.exe /install 0` once, with winemenubuilder off, then `wineserver -k`: the COM server `Inventor.Application` and the document types (`Inventor.PartDocument`, ...) that Windows' install registers (`docs/installer-completeness-review.md`, "Needed" 1); a registration that does not finish is a warning (Inventor runs without it), try again with `--run 0005` | 2026-11-16 |
| 0006-bsdtar-tar-exe | `tar.exe` in system32 (and syswow64): libarchive's signed Windows build of bsdtar 3.5.3, pinned and SHA-256 checked (`scripts/lib/bsdtar.env`, also in `nix/inventor.nix`), license text in `<prefix>/.inventor-on-linux/doc/libarchive-3.5.3/`. Windows 10 ships bsdtar as `System32\tar.exe`; the Electrical Catalog Browser's installer unpacks its library with it | 2026-11-16 |
| 0007-public-documents-paths | registry: Autodesk's plain string values (REG_SZ) under `Software\Autodesk` and `HTML Help` that hold the text `%PUBLIC%\...` (Task Scheduler `DBQ`, `LogFile`; `admapi_31_0.chm`) -> `C:\users\Public\...`; the installer wrote the `[{Common Documents}]` mapping's target unexpanded before 2026-11-16. Wine's own REG_EXPAND_SZ values stay | 2026-11-16 |
| 0008-public-documents-paths-wow64 | the same as 0007 for the 32-bit view (`Software\Wow6432Node\Autodesk`, `...\Wow6432Node\Microsoft\Windows\HTML Help`), which 0007 missed: `admapi_31_0.chm` there kept `%PUBLIC%\` on the maintainer's prefix | 2026-11-16 |
| 0009-vkd3d-proton-winum | `d3d12.dll`, `d3d12core.dll` (system32, syswow64) from winum's `vkd3d-proton-3.0.1-winum-1` (upstream 3.0.1 plus the ray payload fix, the same archive as the NixOS package) in place of upstream's 3.0.1; only with `INV_VKD3D=pinned`, the default `VKD3D_VER` (the one `VKD3D_DLL_SHA256_VER` names) and when the DLLs differ from the pinned ones (`VKD3D_DLL_SHA256`); the old DLLs in the backup; offline put off like 0006 | 2026-11-16 |
| 0010-default-addins-on | add-ins on as on Windows: Feedback, PerfFeedback, InteractiveTutorial (and `InteractiveTutorial.dll`, `en-US\InteractiveTutorial.resources.dll` from `Addins.disabled\libs` back to `Bin`), translatorfusion, and SharedViews with .NET Framework 4.8 - moved from `Addins.disabled` back to `Bin\Addins` (maintainer's test, 2026-11-16, `notes/disabled-addins.md`); the Assistant stays off; an add-in already in `Bin\Addins` is left as it is; both ends of every move in the backup | 2026-11-16 |
| 0011-winemenubuilder-off | `HKCU\Software\Wine\DllOverrides` `"winemenubuilder.exe"=""` (disabled, as Wine's loader reads an empty load order): Wine's menu builder off in the prefix itself, not only through `WINEDLLOVERRIDES` (a plain `wine reg query` by hand wrote 18 file-association and protocol entries, 2026-11-16); then the prefix's menu entries and Wine's MIME packages for Inventor's file types are removed (`remove_wine_menu_entries`, as `install-desktop-integration.sh`), not in the backup (outside the prefix) | 2026-11-16 |
| 0012-tutorial-off-without-dotnet48 | without .NET Framework 4.8 (Wine Mono: every prefix from before 2026-11-11): `Autodesk.InteractiveTutorial.Inventor.addin` from `Bin\Addins` back to `Addins.disabled` - 0010 had turned it on in every prefix, and on Wine Mono it crashed Inventor right after the splash at every start (found by @Lukas10999); its two libraries stay in `Bin`; with .NET 4.8 nothing changes; both ends in the backup | 2026-11-18 |

## Tested

L4 on reflink copies of the maintainer's prefixes (2026-11-11): Inventor
2026 from before winum with isolation (0002, 0003 applied; start, part,
assembly, save/reopen, restart OK) and Inventor 2027 with .NET 4.8 (0002
forced: no .NET shim window with `mscoree=d`, wine-mono not back, Property
Mapping and 3D PDF Publish OK). Details: `docs/arch-hyprland.md`, "Prefix
migrations".

Steps 0005-0008 on a copy of the maintainer's everyday 2027 prefix
(2026-11-16): 0005 "already so" (the keys were there), 0006-0008 applied,
no new `wine-*.desktop`; Inventor starts. 0005 then on the same copy with
both registration keys deleted: keys back, no new `wine-*.desktop`. After testing on a copy, the everyday prefix may need a new
Autodesk sign-in: signing in in one copy invalidates the session of the
others ("Licensing Error" -> "Change license type"). Details:
`docs/installer-completeness-review.md`, "Migrations on a copy of the
everyday prefix".

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
