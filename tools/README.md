# Tools for the installer completeness review

Used to compare what Autodesk's installer (ODIS) does on Windows with what
`scripts/install-from-image.py` does in a Wine prefix, from the same install
image. See [docs/installer-completeness-review.md](../docs/installer-completeness-review.md).

Everything these tools read stays local: captures, registry exports, logs
and `.PML` files are never committed. The installer-review tools report
names, MSI properties and a few paths with identifying information masked.
The companion capture also reports selected registry values and file hashes.

| Tool | Runs on | What it does |
|---|---|---|
| `capture-state.ps1` | Windows VM (admin PowerShell) | Snapshot before and after an install: file list, registry exports, services, scheduled tasks, machine environment, uninstall entries; after the install also the installer's and every MSI package's logs. |
| `compare-reference.py` | Linux | Windows "after minus before" against a prefix: packages, MSI properties per package, files (missing, and Autodesk files of a different size: another build), registry keys and value names, services, uninstall entries, environment. Summary to stdout, full lists with `--details`. |
| `odis-audit.py` | Linux | Reads the image's manifests (nothing is installed): applications in the image, `%VARIABLES%` the installer cannot fill in (install location, MSI properties, parameters, actions), action types it does not run. |
| `adix-extensions.py` | Linux | What the `AppxManifest.xml` of each ADIX package declares beyond files (COM, file types, fonts, shortcuts). |
| `pml-who-wrote.py` | Linux, `pip install procmon-parser` | Which process (command line, parents) wrote a registry key or file, from a Process Monitor capture. |
| `pml-process-context.py` | Linux, `procmon-parser` | Which installer files (.msi, .mst, ...) the parent of a process had opened before it started it ("which package's action ran this"). |
| `admeta-check.py` | Linux | File integrity of a prefix: every file the image's `.admeta` lists for an ADIX package is present and identical (size, SHA-256) to the file inside the package. |
| `installdir-check.py` | Linux | Per MSI package of the image: its `installLocation` next to the `INSTALLDIR` Windows' command line had (does ODIS pass `%INSTALL_DEST%` to MSIs without an `installLocation`?). |
| `adix-registry-names.py` | Linux | ADIX packages with a `Registry.reg` next to `Registry.dat`: key and value NAMES of both compared (never the data) - does the `.reg` hold anything the imported `.dat` does not? |
| `image-manifest.ps1` / `image-manifest.py` | Windows VM / Linux | SHA-256, size and path of every file of an install image in one format (`make`), and a comparison of two such lists (`compare`): is the image Autodesk's Create Installer writes under Wine the same as on Windows? |

## How the 2026-11-15 comparison was made

In a clean, offline Windows 10 VM (local user without a personal name,
en-US, Windows Installer logging on:
`reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\Installer" /v Logging /t REG_SZ /d voicewarmupx /f`),
the same `Inventor_Professional_2027_English_Win_64bit_db_00?_002` files as on
Linux (SHA-256 compared), unpacked first:

```powershell
powershell -ExecutionPolicy Bypass -File capture-state.ps1 -Label before -Out C:\cap
Procmon64.exe /AcceptEula /Quiet /Minimized /BackingFile C:\cap\install.PML
# Setup.exe from the unpacked image, defaults, wait until everything is installed
Procmon64.exe /Terminate
powershell -ExecutionPolicy Bypass -File capture-state.ps1 -Label after -Out C:\cap
```

On Linux, a fresh prefix from the same image (without updates):

```bash
bash scripts/install.sh <..._db_001_002.exe> <..._db_002_002.7z> \
    --prefix /path/.wine-inventor2027-ref --skip-packages --no-desktop
python3 -I tools/odis-audit.py <unpacked image>
python3 -I tools/compare-reference.py <cap> /path/.wine-inventor2027-ref \
    --linux-log logs/odis-install-<date>/install.log --details compare-details.md
venv/bin/python -I tools/pml-who-wrote.py <cap>/install-1.PML --path 'Inventor\.Application'
```

## Comparing an update (2027.2)

The same tools, with Windows' "before" taken in the VM snapshot with the
product installed (`inventor2027-base`) and "after" once the update has
run; the base install's logs in `%TEMP%` are moved aside after "before",
so that "after" collects only the update's. On Linux the update goes into
a reflink copy of a prefix made from the same image, with
`scripts/install.sh UPDATE.exe --prefix COPY` (the prefix has the
installer's state, so only the update runs). `compare-reference.py
--changed` also lists files whose size the update changed but the prefix
did not (an update mostly replaces files).

## Inventor Nastran 2027 companion capture

Use these tools to compare the registrations and files added by Nastran
before installation, after installation, and after Inventor first opens the
Nastran environment. The last phase matters because Nastran registers its
per-user NEWPFUI class at startup. Use Inventor 2027.2 and the same Autodesk
Create Installer images for Inventor and Nastran on both systems.
[Observed Wine behavior](../docs/arch-hyprland.md#result-log).

Keep captures, comparison reports and Fusion logs in a private folder outside
the checkout. Only the masked text captures leave the VM. Review them before
sharing filtered excerpts. The tools never transmit data, and their outputs
stay out of Git.

### Windows 10 reference

Use Windows PowerShell 5.1. Capture as the Inventor user so HKCU belongs to
the account that ran Inventor. Use elevated PowerShell for enabling and
disabling Fusion logging.

In the offline snapshot with Inventor 2027.2 installed, copy in the Nastran
image and capture script. Use a private output folder that already exists.

~~~powershell
powershell.exe -NoProfile -File .\companion-capture.ps1 -Phase before -DryRun
powershell.exe -NoProfile -File .\companion-capture.ps1 -Phase before -Output C:\capture\win-before.txt
# Install Nastran from its image. Wait for setup to exit with Inventor closed.
powershell.exe -NoProfile -File .\companion-capture.ps1 -Phase installed -Output C:\capture\win-installed.txt
~~~

Use the separate online snapshot for sign-in and first startup. Prepare it
independently with the same Inventor and Nastran versions and an empty
`C:\fusionlog`. Turn on failure logging before launching Inventor.

~~~powershell
# Elevated PowerShell
powershell.exe -NoProfile -File .\companion-capture.ps1 -FusionLog on
# Sign in to Inventor, open Nastran and note whether 0x80040154 appears.
# After startup, capture as the Inventor user.
powershell.exe -NoProfile -File .\companion-capture.ps1 -Phase started -FusionLog collect -Output C:\capture\win-started.txt
# Elevated PowerShell
powershell.exe -NoProfile -File .\companion-capture.ps1 -FusionLog off
~~~

The `on` switch sets `LogFailures=1` (DWORD) and `LogPath=C:\fusionlog\` in
native `HKLM\SOFTWARE\Microsoft\Fusion`. The `off` switch removes those two
values. It leaves the log files in place. Collect records the `.HTM` names
and the Calling assembly, DisplayName and Bind result lines. A dry run
lists the selected scope or planned Fusion operation without opening the
registry or inspecting paths. Use the offline before-to-installed pair
to attribute installer changes. The online started capture can also
include differences between snapshots.

### Wine

Start with a fresh copy of the Inventor 2027.2 prefix and a Wine runtime with
all three candidates (`wbemdisp-method-invoke`, `msado15-stream-charset`,
`combase-per-user-classes`). Close the original prefix before copying it.
Set `prefix` to the copy, `out` to an existing private output directory,
`nastran_image` to the installer image and `runtime` to the candidate
Wine directory. Wait for Wine to finish and flush `system.reg` and `user.reg`
before each capture.

~~~bash
(
    set -e
    export PATH="$runtime/bin:$PATH"
    export WINE="$runtime/bin/wine" WINESERVER="$runtime/bin/wineserver" WINELOADER="$runtime/bin/wine"
    export WINEDLLOVERRIDES='wbemdisp,msado15,combase=b'

    python3 tools/companion-capture.py capture "$prefix" before --output "$out/wine-before.txt"
    python3 scripts/install-from-image.py "$nastran_image" --prefix "$prefix"
    python3 tools/companion-capture.py capture "$prefix" installed --output "$out/wine-installed.txt"

    # Optional Fusion capture. Use a copy without earlier Fusion logs.
    mkdir -p -- "$prefix/drive_c/fusionlog"
    fusion='HKLM\SOFTWARE\Microsoft\Fusion'
    WINEPREFIX="$prefix" "$WINE" reg add "$fusion" /v LogFailures /t REG_DWORD /d 1 /f /reg:64
    WINEPREFIX="$prefix" "$WINE" reg add "$fusion" /v LogPath /t REG_SZ /d 'C:\fusionlog\' /f /reg:64

    # Switch to Nastran and note the dialog. Close Inventor before capturing.
    INV_PREFIX="$prefix" INV_YEAR=2027 INV_WINE=system bash scripts/launch-inventor.sh
    python3 tools/companion-capture.py capture "$prefix" started --fusion-log collect \
        --output "$out/wine-started.txt"

    WINEPREFIX="$prefix" "$WINE" reg delete "$fusion" /v LogFailures /f /reg:64
    WINEPREFIX="$prefix" "$WINE" reg delete "$fusion" /v LogPath /f /reg:64
)
~~~

Omit the Fusion setup, cleanup and collect option for a capture without bind
diagnostics. The Linux tool reads Wine registry files directly and opens
vendor files solely to compute their hashes. Linux skips symlinks and Windows
skips reparse points. The default output is `companion-capture-PHASE.txt`.
Both collectors require a new output path.

### Compare the captures

~~~bash
python3 tools/companion-capture.py compare "$out/win-before.txt" "$out/win-installed.txt" \
    --details "$out/windows-install-diff.txt"
python3 tools/companion-capture.py compare "$out/wine-before.txt" "$out/wine-installed.txt" \
    --details "$out/wine-install-diff.txt"
python3 tools/companion-capture.py compare "$out/win-started.txt" "$out/wine-started.txt" \
    --details "$out/started-diff.txt"
~~~

The comparison shows the first 40 changes per registry root or file folder.
`--details` writes the complete comparison to a new file. Compare
installed-to-started within either environment to isolate the startup
registrations before comparing the two environments.

The collectors write UTF-8 with LF in ordinal order. Registry paths, value
names and relative file paths are lowercase. `REG` records keep the registry
type, use a blank name for the default value, and use `KEY` for an empty
selected key. PATH and `REG_MULTI_SZ` data list their entries in order,
separated by ` ; `. A literal percent, pipe, control character or semicolon
within a list entry is percent-escaped. GAC names use `FILE path | - | -`.
Optional `FUSION` rows identify an HTM name and field. Account names,
profiles, SIDs and machine names are masked. Sensitive registry values appear
as `<masked>`, and licensing and identity paths are skipped.

### Check the Nastran registry count on Wine

Use the same, flushed prefix for both commands and a fresh output path.
The first count is explicit sections in Wine's save file. The second
reports captured values and empty keys separately. The capture also
reconstructs ancestor keys whose sections Wine omitted, so total unique
keys can be higher than the raw count.

~~~bash
rg -ic '^\[Software\\\\Autodesk\\\\Autodesk Inventor Nastran 2027(?:\\\\|\])' "$prefix/system.reg"
python3 tools/companion-capture.py capture "$prefix" installed --output "$out/wine-installed-recheck.txt"
rg -i '^REG HKLM\\software\\autodesk\\autodesk inventor nastran 2027(?:\\| \| )' \
    "$out/wine-installed-recheck.txt" |
    awk -F ' \\| ' '$3 == "KEY" {empty++; next} {values++; keys[$1]=1}
        END {for (key in keys) count++; printf "value_keys=%d values=%d empty_keys=%d\n", count, values, empty}'
~~~

On a disposable Wine 11.22 prefix populated with 35 synthetic keys of that
shape, all 35 explicit sections appeared in the capture. A direct count
also found one machine PATH key under `System\ControlSet001`. The capture
now resolves Wine's `CurrentControlSet` alias and emits the active PATH
under `System\CurrentControlSet`, as the Windows collector does.
