# Draft patches

Unfinished Wine patches kept for later. They are **not** applied: the Wine
build (`scripts/build-wine.sh`, `nix/wine.nix`) only takes `patches/*.patch`.

## win32u-foreign-process-gdi.patch

**Outcome (2026-10-26): not usable.** The patch helped render Inventor's
WebView2 Home page, but the Nix maintainer reported terribly slow and glitchy
interaction. Screenshot success did not establish usability. Further work is
deferred in favour of upstream support; see the
[Wayland summary](../../docs/arch-hyprland.md#native-wayland-summary-not-ready-for-inventor-2026-10-26)
and [Wine #58921](https://bugs.winehq.org/show_bug.cgi?id=58921).

Opt-in opaque GDI bridge for drivers without X11's direct drawing fallback.
The sending process paints to a private DIB and sends bounded dirty tiles to
the top-level window's owner through a marshalled internal Wine message.
Enable only in the experimental runtime with `WINE_WAYLAND_GDI_BRIDGE=1`.

The full Wine 11.20 flake WoW64 build passed (x86_64 and i386 PE output, full
normal patch set plus this draft, no hunk fuzz). The synthetic native Wayland
test changes from zero blue pixels to 47,619, with the same-process panel
remaining visible. Both test processes exit normally. Inventor 2027.1 Home
renders Open/New, project selection, recent files and help links on private
KWin at scale 1.5. New opens its dialog; explicitly focusing it and clicking
Cancel returns to Home; explicitly focused close exits Inventor with status 0.

Known limits: white-edge artifacts after focus changes, a detached small
control, transparent/destination-dependent drawing, changing clipping,
resize/DPI/surface-generation races, synchronous message waits and per-tile
flush overhead. A first run timed out after unfocused modal close requests;
the focused pointer-input repeat succeeded. This is not general native
Wayland usability validation. Real Windows tests and neighbouring Wine
regression suites remain outstanding. Independent review read the draft in
full and did not find distinctive copied implementation; it did find the
limits above. No Microsoft or Autodesk implementation code was inspected.

Build explicitly with `nix build "path:$PWD#wine-wayland-gdi-experimental"`
while the patch is untracked, or `nix build .#wine-wayland-gdi-experimental`
once it is tracked. This builds Wine only. The initial application experiment
used temporary copies
of its launcher scripts with only the Wine runtime paths changed, against
the same existing user state in place. Do not copy an authenticated prefix.

See [the reproducer](../../docs/wine-repro/winewayland-cross-process-gdi/README.md)
and the native Wayland Home section in `docs/arch-hyprland.md`. Keep this
draft out of normal builds until the remaining correctness issues and
Windows/regression validation are resolved. WINE_BUILD is unchanged because
the normal patch set is unchanged.

## win32u-installed-display-drivers.patch

Writes `InstalledDisplayDrivers` (REG_MULTI_SZ, the vendor's user-mode driver
names: AMD `aticfx64`/`amdxc64`, NVIDIA `nvldumdx`, Intel `igdumdim64`/
`igd10iumd64`/`igd12umd64`) into each GPU's display class key, as Windows
drivers do. Wine's `prepare_devices` recreates that key at every start, so a
registry entry set from outside is lost.

Why: Inventor's Help > Diagnostics showed no driver name and version
(`launch-inventor.sh` has the same as an experiment: `INV_DRIVER_NAMES=1`).
It did **not** make GPU ray tracing available (see the README and
docs/arch-hyprland.md) - so it is a cosmetic/diagnostic fix.

State: applies to Wine 11.20 and current upstream; not built or tested as a
Wine build yet. Before it can move to `patches/` it needs a test (dlls/win32u
or the display-device tests) and a check what real Windows drivers write for each
vendor (the names above come from AMD/NVIDIA/Intel driver INF files and a
Windows install).
