# AutoCAD 2027 – status (experimental, `autocad` branch)

Tested 2026-10-21 on Arch / KDE Wayland, RX 580, Wine 11.20 (this project's build).

## Works
- Install from the downloaded image: `INV_PRODUCT=autocad bash scripts/install.sh`
  into its own prefix (`~/.wine-autocad2027`), 31 steps.
- Start: window, ribbon, Drawing1.dwg, DirectX 12 through vkd3d-proton.

## Fixed along the way
- **Status bar / ".NET Assertion Failed: AcSbGridDisplay"** – Wine's urlmon
  returned an invalid zone for `res:///…` icon URLs, WPF refused the images.
  Fixed in Wine (`patches/urlmon-res-zone-local-machine.patch`,
  `patches/urlmon-maptozone-null-terminate.patch`, wine-11.20-5).
- **`D3DCOMPILER_47.dll` not found** – override `d3dcompiler_47=native,builtin`.
- **ADP Desktop SDK empty** – the installer ran the package's preInstall
  action after unpacking it, which deleted the files. Actions now run in order.
- ODIS installer, Autodesk Access and CER are skipped like for Inventor.

## Open: "License Error – The License manager is not functioning"
AutoCAD shows its UI, then exits with this error. What is known:
- The licensing service runs and AutoCAD 2027 (`001S1`) is registered in it.
- AutoCAD's licensing SDK (`AdskLicensingSDK_10.dll`) never connects to the
  service – the service log has no `SDK(...)` / `Features in service` lines.
  Inventor 2027 uses the same SDK and service version and does connect.
- Not the cause: Identity Manager version (1.16.5.1 vs 1.17.0.4), ADP SDK,
  missing COM classes from AdWindows.dll, Wine stubs (no fixme in that window).

Next ideas: compare the environment AutoCAD's SDK sees with Inventor 2027's
(registry under `HKLM\SOFTWARE\Autodesk\…`, process command line, the
order the launcher starts Identity Manager / licensing).
