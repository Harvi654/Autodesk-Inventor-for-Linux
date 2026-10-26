# Notes for AI assistants (Codex, Claude Code, ...) working on this repository

Autodesk Inventor (2026, 2027) on Linux with Wine, installed from the user's
own Autodesk download. Maintainer: @Harvi654. NixOS flake (`flake.nix`,
`nix/`) is contributed and maintained by @krokosik.

Read the README first, then the commit history (`git log`): commit messages
explain why things are the way they are.

For Nix/NixOS work, also read [nix/AGENTS.md](nix/AGENTS.md).

## Layout
- `scripts/install.sh` - terminal installer (8 phases); `scripts/install-gui.sh`
  + `scripts/gui/installer.py` - GTK 4 window around it (follows `@@phase` lines).
- `scripts/install-from-image.py` + `scripts/lib/odis.py` - runs Autodesk's
  ODIS install image under Wine (MSI/EXE/ZIP/7Z/ADIX, quirks, skip list).
- `scripts/finish-install.sh`, `scripts/lib/configure.sh` - prefix setup
  (DXVK, vkd3d-proton, WebView2, fonts, disabled add-ins, isolation).
- `scripts/launch-inventor.sh` - starts Identity Manager, licensing service,
  then Inventor. `scripts/lib/common.sh` - shared settings, release/prefix
  detection (`INV_YEAR`, `INV_PREFIX`, `inventor_installs`).
- `patches/*.patch` - Wine patches; `wine/version.env` + `wine/SHA256SUMS`;
  `.github/workflows/build-wine.yml` builds and publishes `wine-<ver>-<build>`.
- `notes/`, `docs/` - findings (disabled add-ins, Hyprland, NixOS).

## Rules
- **One Autodesk release per Wine prefix**, never a second program or release
  into an existing prefix. Default prefix `~/.wine-inventor<year>`.
- **Never commit or publish:** `registry/*.reg`, logs, Autodesk binaries or
  installers, Autodesk tokens/session URLs (ODIS `.info` files, IdServices
  logs), personal data (names, e-mails, home paths of real users).
- Autodesk files are never fetched, mirrored or cached publicly (NixOS uses
  `requireFile` + `unfree`).
- Downloads (DXVK, vkd3d-proton, Wine) are version-pinned and SHA-256 checked.
  Something new that `finish-install.sh` downloads must also be added to
  `nix/inventor.nix` (fetchurl + link into `DOWNLOAD_DIR`) - the Nix build
  sandbox has no network.
- No AUR packages. Microsoft DLLs only as black boxes (no disassembly).
- Don't reverse engineer or work around Autodesk licensing or copy protection.
- Commits: plain English subject, body says why; signed release tags `v*` are
  created by the maintainer locally (`git tag -s`), never by an assistant.
  Releases are published by the maintainer (`gh release create --verify-tag`).
- Push only to `github.com/Harvi654/Autodesk-Inventor-for-Linux` (`main`, and
  experimental branches such as `autocad`).
- Pull requests from others: read the whole diff; pay special attention to
  `scripts/`, anything that downloads, `.github/workflows/`, and `flake.lock`
  input changes (review the external repo's diff too). Say what was read in
  full and what was only skimmed.

## Wine changes
- A fix is a `patches/<dll>-<what>.patch` against the Wine version in
  `wine/version.env`, with a test in Wine's test suite where possible.
- Raise `WINE_BUILD` when patches change; the workflow publishes the release;
  then add its SHA-256 to `wine/SHA256SUMS` (`[skip ci]`).
- Patches are written with AI help and are **not** sent to Wine: Wine does not
  accept LLM-generated code and requires the author's real name. Never submit
  them or hide their origin. What goes to Wine is a bug report on
  bugs.winehq.org in words: what the application calls, what Wine returns,
  what Windows returns, the steps and a public synthetic test.
- Write them as Wine would anyway: one DLL, small, in the style of the
  surrounding code, with the `/*** name (DLL.@) */` headers kept, and a test in
  `dlls/<dll>/tests/` that uses `ok()` / `todo_wine` (fails on unpatched Wine,
  passes with the patch). The test describes Windows, so it has to pass on
  Windows (below).
- Patches modify LGPL code, so they are LGPL 2.1 or later (see
  `patches/README.md`), whatever the license of the rest of the repository.

### Validation levels
A patch is recorded with the level it reached:
- **L0** builds from the official Wine source with the full patch set, both
  architectures, no fuzz.
- **L1** its Wine test passes on real Windows 10 (x86_64 and i686 executables
  built with MinGW, run in the maintainer's Windows VM, which has no network;
  only text results come back, never DLLs). Expected values come from what
  Windows returned, not from documentation or guesses; where a value is
  unknown, add a trace and measure it first. If a test fails on Windows, the
  test is wrong - fix the test, then the patch.
- **L2** the existing tests of the touched DLL show no new failures (for
  server, user32, win32u, winex11 also run the neighbouring suites).
- **L3** reproducers or fuzzing for complex cases (`docs/wine-repro/`).
- **L4** the maintainer's smoke test in Inventor (and SOLIDWORKS when the DLL
  is shared): the feature itself plus start, part, assembly, save/reopen,
  restart.
- **L5** a week of normal use.
Diagnostic or trace patches stay in `patches/debug/` and never go into a
normal build. A patch that passes its tests but does not fix the user's
problem is not added.

### Clean room
- Allowed: observing behaviour from outside - Wine debug channels (`+relay`,
  `+seh`, `+ole`, ...), also with native Microsoft components (.NET 4.8,
  WebView2), and stack addresses at a crash. When a native Microsoft component
  was traced, say so in the docs.
- Not allowed: disassembly, debug symbols or source of Microsoft code, copying
  Microsoft files out of Windows or the VM, and looking inside Autodesk (or
  other vendors') binaries beyond crash addresses.
- Bug reports for Wine contain only the application's side and our own tests,
  never internals of Microsoft DLLs.
- AI may have seen other projects' code (Mesa, ReactOS, ...): ask for original
  code and say so in the patch; for a larger patch ask a second model whether
  it resembles a known project.

### Working with AI
- Test first, then the fix; one task at a time.
- Three rounds: if three fix attempts do not bring the result closer, stop,
  write down the state and the best hypothesis, and move to something else.
- Cross review: a patch written by one assistant is read in full by another
  before it goes into a normal build.
- Every patch gets a short plain-language explanation in the docs that the
  maintainer can follow without reading the code.

## Documentation
- Every fix or finding gets written up in `docs/arch-hyprland.md`, in the
  same style as the sections there: a section for the problem (symptom as the
  user saw it, cause down to the Wine function, the fix, how it was found -
  with the commands, so others and Wine developers can repeat it - what is
  still open, notes for a Wine bug report, the validation level reached) and
  a dated entry in its "Result log".
  Reproducers and test programs go to `docs/wine-repro/<dll>-<topic>/` with a
  README. Also update `README.md` (status table) and `notes/` where they
  mention the topic.

## Testing
- `bash -n scripts/*.sh scripts/lib/*.sh`, `python3 -m py_compile`,
  `python3 -m unittest discover -s tests`.
- Release/prefix logic can be tested with fake prefixes in a temporary `HOME`
  (a file `drive_c/Program Files/Autodesk/Inventor <year>/Bin/Inventor.exe`).
- Wine and Inventor run on the maintainer's machine; ask for filtered logs
  (`grep`/`tail`) rather than whole files.
