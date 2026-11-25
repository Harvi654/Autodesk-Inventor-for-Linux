# capture-state.ps1 - snapshot of what an install can change on Windows,
# for comparing a reference install with a Wine prefix.
# Run as Administrator, once before and once after the install:
#   powershell -ExecutionPolicy Bypass -File capture-state.ps1 -Label before -Out C:\cap
#   powershell -ExecutionPolicy Bypass -File capture-state.ps1 -Label after  -Out C:\cap
# Output stays local; it contains registry values and paths. Only filtered,
# masked results are used outside the VM.
param(
    [Parameter(Mandatory = $true)][ValidateSet('before', 'after')][string]$Label,
    [string]$Out = 'C:\cap'
)
$ErrorActionPreference = 'Continue'
$dir = Join-Path $Out $Label
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$log = Join-Path $dir 'capture.log'
function Note($m) { "$(Get-Date -Format s) $m" | Tee-Object -FilePath $log -Append }

Note "capture $Label on $([Environment]::OSVersion.VersionString)"

# 1. Files: path, size, last write time (UTC). Folders an install touches.
$roots = @(
    $env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:ProgramData,
    $env:APPDATA, $env:LOCALAPPDATA, "$env:USERPROFILE\Documents",
    "$env:PUBLIC", "$env:SystemRoot\System32", "$env:SystemRoot\SysWOW64",
    "$env:SystemRoot\Fonts", "$env:SystemRoot\Microsoft.NET",
    "$env:SystemRoot\assembly", "$env:SystemRoot\WinSxS\Manifests",
    "$env:SystemRoot\Installer"
)
$files = Join-Path $dir 'files.tsv'
"path`tsize`tmtime_utc" | Set-Content -Encoding UTF8 $files
foreach ($r in $roots) {
    if (-not (Test-Path $r)) { continue }
    Note "files: $r"
    Get-ChildItem -LiteralPath $r -Recurse -Force -File -ErrorAction SilentlyContinue |
        ForEach-Object { "$($_.FullName)`t$($_.Length)`t$($_.LastWriteTimeUtc.ToString('s'))" } |
        Add-Content -Encoding UTF8 $files
}

# 2. Registry exports (values included; read locally only)
$keys = [ordered]@{
    'hklm-software'  = 'HKLM\SOFTWARE'
    'hklm-services'  = 'HKLM\SYSTEM\CurrentControlSet\Services'
    'hklm-control'   = 'HKLM\SYSTEM\CurrentControlSet\Control'
    'hkcu-software'  = 'HKCU\Software'
    'hku-default'    = 'HKU\.DEFAULT\Software'
}
foreach ($k in $keys.Keys) {
    Note "registry: $($keys[$k])"
    & reg.exe export $keys[$k] (Join-Path $dir "$k.reg") /y | Out-Null
}

# 3. Services, scheduled tasks, machine environment, installed MSI products
Note 'services, tasks, environment, products'
Get-CimInstance Win32_Service |
    Select-Object Name, DisplayName, StartMode, State, StartName, PathName |
    Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $dir 'services.csv')
Get-ScheduledTask | Select-Object TaskPath, TaskName, State |
    Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $dir 'tasks.csv')
[Environment]::GetEnvironmentVariables('Machine').GetEnumerator() |
    Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value)" } |
    Set-Content -Encoding UTF8 (Join-Path $dir 'env-machine.txt')
# Uninstall entries (not Win32_Product: querying it can trigger MSI repairs)
$un = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
      'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
Get-ItemProperty $un -ErrorAction SilentlyContinue |
    Select-Object PSChildName, DisplayName, DisplayVersion, Publisher, InstallLocation |
    Sort-Object DisplayName |
    Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $dir 'uninstall.csv')

# 4. After the install: logs of the installer and of every MSI package
if ($Label -eq 'after') {
    $logs = Join-Path $dir 'logs'
    New-Item -ItemType Directory -Force -Path $logs | Out-Null
    Note 'copying installer logs'
    foreach ($p in @("$env:TEMP", "$env:SystemRoot\Temp")) {
        Get-ChildItem -LiteralPath $p -Recurse -Force -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in '.log', '.txt', '.json', '.xml' -and
                           $_.LastWriteTime -gt (Get-Date).AddDays(-2) } |
            ForEach-Object {
                $rel = $_.FullName.Substring($p.Length).TrimStart('\') -replace '[\\:]', '_'
                Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $logs ("{0}_{1}" -f ($p -replace '[\\:]', '_'), $rel)) -ErrorAction SilentlyContinue
            }
    }
    foreach ($p in @("$env:ProgramData\Autodesk\ODIS", "$env:LOCALAPPDATA\Autodesk\ODIS")) {
        if (Test-Path $p) {
            Copy-Item -LiteralPath $p -Destination (Join-Path $logs ('odis_' + ($p -replace '[\\:]', '_'))) -Recurse -ErrorAction SilentlyContinue
        }
    }
}

Note 'done'
Get-ChildItem $dir | Select-Object Name, Length | Format-Table -AutoSize | Out-String | Note
