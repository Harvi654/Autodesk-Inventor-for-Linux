# Tools for the installer completeness review

Used to compare what Autodesk's installer (ODIS) does on Windows with what
`scripts/install-from-image.py` does in a Wine prefix, from the same install
image. See [docs/installer-completeness-review.md](../docs/installer-completeness-review.md).

Everything these tools read stays local: captures, registry exports, logs
and `.PML` files are never committed. What they print is names (files,
registry keys and value names, MSI property names, a few paths), with user
names, SIDs and long hex IDs masked.

| Tool | Runs on | What it does |
|---|---|---|
| `capture-state.ps1` | Windows VM (admin PowerShell) | Snapshot before and after an install: file list, registry exports, services, scheduled tasks, machine environment, uninstall entries; after the install also the installer's and every MSI package's logs. |
| `compare-reference.py` | Linux | Windows "after minus before" against a prefix: packages, MSI properties per package, files, registry keys and value names, services, uninstall entries, environment. Summary to stdout, full lists with `--details`. |
| `odis-audit.py` | Linux | Reads the image's manifests (nothing is installed): applications in the image, `%VARIABLES%` the installer cannot fill in (install location, MSI properties, parameters, actions), action types it does not run. |
| `adix-extensions.py` | Linux | What the `AppxManifest.xml` of each ADIX package declares beyond files (COM, file types, fonts, shortcuts). |
| `pml-who-wrote.py` | Linux, `pip install procmon-parser` | Which process (command line, parents) wrote a registry key or file, from a Process Monitor capture. |

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
