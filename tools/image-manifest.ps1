# File list of an install image: SHA-256, size and relative path of every
# file, one per line, sorted by path (ordinal). The same format as
# tools/image-manifest.py, so an image made on Windows can be compared with
# one made under Wine (`image-manifest.py compare`).
#
# Usage (Windows PowerShell 5.1 or PowerShell 7):
#   powershell -ExecutionPolicy Bypass -File image-manifest.ps1 `
#       -Path "$env:USERPROFILE\Downloads\Autodesk\Inventor Professional 2027 - (EN)" `
#       -Out C:\cap\image-windows.tsv
#
# The output holds only paths inside the image, sizes and hashes; it stays
# local all the same (never committed).
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Out
)
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path -LiteralPath $Path).ProviderPath.TrimEnd('\')
$files = Get-ChildItem -LiteralPath $root -Recurse -File -Force
$lines = New-Object System.Collections.Generic.List[string]
$i = 0
foreach ($f in $files) {
    $i++
    Write-Progress -Activity 'Hashing' -Status $f.Name -PercentComplete ($i * 100 / [Math]::Max(1, $files.Count))
    $rel = $f.FullName.Substring($root.Length + 1).Replace('\', '/')
    $hash = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $lines.Add("$hash`t$($f.Length)`t$rel")
}
$arr = $lines.ToArray()
# Sort by the path column, ordinal, like Python's sorted().
$keys = $arr | ForEach-Object { $_.Split("`t", 3)[2] }
[Array]::Sort([string[]]$keys, $arr, [StringComparer]::Ordinal)

$dir = Split-Path -Parent $Out
if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
# UTF-8 without BOM, LF line ends.
[IO.File]::WriteAllText($Out, (($arr -join "`n") + "`n"), (New-Object Text.UTF8Encoding($false)))
$total = ($files | Measure-Object -Property Length -Sum).Sum
Write-Output ("{0} files, {1:N1} GB -> {2}" -f $files.Count, ($total / 1GB), $Out)
