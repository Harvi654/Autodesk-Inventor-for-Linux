# Compatibility patches

- Top-level `*.patch` files target Wine. Both `nix/wine.nix` and the script-based
  Wine build discover these automatically.
- `libgsf/` contains the empty OLE stream fix used by the flake's libgsf overlay.
- `debug/` contains optional diagnostic patches, excluded from normal builds.
- `drafts/` contains unfinished patches that are not applied.

Keep patches for other projects and optional runtime variants in subdirectories
so Wine's automatic top-level patch discovery cannot apply them accidentally.

## License

The patches change LGPL-licensed code, so they are licensed like that code:
the Wine patches under the GNU Lesser General Public License 2.1 or later
(Wine's `COPYING.LIB`), the libgsf patch under libgsf's license (also
LGPL 2.1 or later). The MIT license of the rest of this repository does not
apply to them.

Each published Wine release has its source archive next to the binary
(`wine-inventor-<version>-<build>-source.tar.xz`, made by
`scripts/make-wine-source.sh` from the release's tag): the patched tree with
`PATCHES.txt` and a short "Modified by" comment at the end of every changed
file (`scripts/lib/wine-patches.sh`, used by `build-wine.sh` too, so the
binary is built from exactly that tree). The comment goes at the end so line
numbers in messages stay the same as in the patch.

## Origin

The patches were written with AI help (Claude by Anthropic) and tested by
people on real machines; patches from other contributors say which tool they
used. `wbemprox-timezone.patch` comes from the original project
([cakelesscoder/inventor-on-linux](https://github.com/cakelesscoder/inventor-on-linux)).
No Microsoft code, disassembly or debug symbols were used.

Because Wine does not accept AI-generated code, these patches are **not** sent
to Wine. Problems they fix are reported to Wine as bug reports (what the
application calls, what Wine returns, what Windows returns, a public test).

How a patch is validated (tests on real Windows, levels L0-L5) is described in
`AGENTS.md`.
