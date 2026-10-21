# Draft patches

Unfinished Wine patches kept for later. They are **not** applied: the Wine
build (`scripts/build-wine.sh`, `nix/wine.nix`) only takes `patches/*.patch`.

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
Wine build yet. For upstream it needs a test (dlls/win32u or the
display-device tests) and a check what real Windows drivers write for each
vendor (the names above come from AMD/NVIDIA/Intel driver INF files and a
Windows install).
