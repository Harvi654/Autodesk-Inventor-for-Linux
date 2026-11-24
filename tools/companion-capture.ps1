# Windows PowerShell 5.1. Captures and Fusion logs stay local. Never commit them.
# Vendor files are opened only for SHA-256. Only -FusionLog on/off changes settings.
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('before', 'installed', 'started')][string]$Phase,
    [string]$Output,
    [ValidateSet('on', 'off', 'collect')][string]$FusionLog,
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2

$classes = 'software\classes'
$autodesk = 'software\autodesk'
$dotnetRoots = @('software\microsoft\.netframework', 'software\wow6432node\microsoft\.netframework')
$fusionRoots = @('software\microsoft\fusion', 'software\wow6432node\microsoft\fusion')
$machineEnvironment = 'system\currentcontrolset\control\session manager\environment'
$comFamilies = @('clsid', 'typelib', 'interface', 'appid')
$classReserved = @('applications', 'directory', 'drive', 'folder', 'installer', 'mime', 'packagedcom', 'systemfileassociations', 'wow6432node')
$product = 'nastran|nei|newpf|neprogress'
$protected = 'adsklicensing|licenses|idsdk|identity'
$secret = 'serial|licen|token|password|secret|key$'
$sidPattern = '\bS-\d+(?:-\d+){2,}\b'
$logRoot = 'C:\fusionlog'
$ordinal = [StringComparer]::Ordinal
$utf8 = [Text.UTF8Encoding]::new($false, $true)

function Test-Under([string]$Key, [string]$Root) {
    return $Key -eq $Root -or $Key.StartsWith("$Root\", [StringComparison]::Ordinal)
}

function Convert-Field([string]$Text) {
    return [regex]::Replace($Text, '[%|\x00-\x1f\x7f]', {
        param($Hit)
        '%' + ([int][char]$Hit.Value).ToString('X2')
    })
}

function Protect-Text([string]$Text) {
    $Text = $Text -replace $sidPattern, '<sid>'
    foreach ($rule in $maskRules) {
        $Text = $Text -replace $rule.Pattern, $rule.Replacement
    }
    return $Text
}

function New-MaskRules([string[]]$Profiles, [string[]]$Users, [string[]]$Machines) {
    foreach ($person in ($Profiles | Where-Object { $_ } | Sort-Object Length -Descending)) {
        $expression = (($person.TrimEnd('\', '/') -split '[\\/]+') |
            ForEach-Object { [regex]::Escape($_) }) -join '[\\/]+'
        @{ Pattern = '(?<![\w])' + $expression + '(?=$|[\\/\s"''|;,>])'; Replacement = '<profile>' }
    }
    $names = @{}
    foreach ($person in $Users) { if ($person) { $names[$person] = '<user>' } }
    foreach ($machine in $Machines) { if ($machine) { $names[$machine] = '<machine>' } }
    foreach ($person in ($names.Keys | Sort-Object Length -Descending)) {
        @{ Pattern = '(?<![\w<])' + [regex]::Escape($person) + '(?![\w>])'; Replacement = $names[$person] }
    }
}

function Convert-ListField([string[]]$Items) {
    $safeItems = foreach ($item in $Items) {
        if ($item -match $protected) { '<masked>' }
        else { (Convert-Field (Protect-Text $item)).Replace(';', '%3B') }
    }
    return ($safeItems -join ' ; ')
}

function Format-RegValue($Value, [bool]$IsPath) {
    if ($Value.Name -match $secret -or $null -eq $Value.Data) { return '<masked>' }
    $data = $Value.Data
    if ($data -is [byte[]]) {
        foreach ($encoding in @([Text.Encoding]::UTF8, [Text.Encoding]::Unicode, [Text.Encoding]::BigEndianUnicode)) {
            $decoded = $encoding.GetString($data)
            if ($decoded -match $protected -or (Protect-Text $decoded) -cne $decoded) {
                return '<masked>'
            }
        }
        return [BitConverter]::ToString($data).Replace('-', '').ToLowerInvariant()
    }
    if ($IsPath -and $data -is [string]) {
        return Convert-ListField @($data.Split(';') | ForEach-Object { $_.Trim() })
    }
    if ($data -is [string[]]) { return Convert-ListField $data }
    if ($data -is [string] -and $data -match $protected) { return '<masked>' }
    if ($Value.Type -eq 'REG_DWORD' -and $data -is [int]) {
        $data = [BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$data), 0)
    }
    if ($Value.Type -eq 'REG_QWORD' -and $data -is [long]) {
        $data = [BitConverter]::ToUInt64([BitConverter]::GetBytes([long]$data), 0)
    }
    return Convert-Field (Protect-Text ([string]$data))
}

function Get-RegType($Kind) {
    switch ([string]$Kind) {
        'None' { 'REG_NONE' }
        'String' { 'REG_SZ' }
        'ExpandString' { 'REG_EXPAND_SZ' }
        'Binary' { 'REG_BINARY' }
        'DWord' { 'REG_DWORD' }
        'MultiString' { 'REG_MULTI_SZ' }
        'QWord' { 'REG_QWORD' }
        default { 'REG_0' }
    }
}

function Read-RegKey($Key, [string]$Name, [switch]$OnlyPath) {
    $values = @(foreach ($valueName in $Key.GetValueNames()) {
        if ($OnlyPath -and $valueName -ne 'Path') { continue }
        $kind = Get-RegType ($Key.GetValueKind($valueName))
        $data = $null
        if ($valueName -notmatch $secret) {
            $data = $Key.GetValue($valueName, $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        }
        [pscustomobject]@{ Name = $valueName.ToLowerInvariant(); Type = $kind; Data = $data }
    })
    if (!$OnlyPath -or $values.Count) {
        [pscustomobject]@{ Key = $Name; Values = $values }
    }
}

function Read-RegSubtree($Key, [string]$Name) {
    if ($Name -match $protected) { return }
    Read-RegKey $Key $Name
    foreach ($childName in $Key.GetSubKeyNames()) {
        if ($childName -match $protected) { continue }
        $child = $Key.OpenSubKey($childName)
        if ($null -eq $child) { continue }
        try { Read-RegSubtree $child ($Name + '\' + $childName.ToLowerInvariant()) }
        finally { $child.Dispose() }
    }
}

function Test-ClassMatch($Key, [string]$Group) {
    if ($Key.Key -match $product) { return $true }
    $inproc = $Group -match '\\clsid\\' -and $Key.Key -eq ($Group + '\inprocserver32')
    foreach ($value in $Key.Values) {
        if ($value.Name -match $product) { return $true }
        if ($value.Data -isnot [string] -and $value.Data -isnot [string[]]) { continue }
        foreach ($text in @($value.Data)) {
            if ($text -match $protected) { continue }
            if ($text -match $product) { return $true }
            if ($inproc -and $value.Name -eq '' -and
                $text.Trim('"', ' ') -match '(?:^|[\\/])mscoree\.dll$|(?:^|[\\/])inventor(?: nastran)? 2027[\\/]') {
                return $true
            }
        }
    }
    return $false
}

function Read-MatchedClass($Key, [string]$Group) {
    $keys = @(Read-RegSubtree $Key $Group)
    foreach ($record in $keys) {
        if (Test-ClassMatch $record $Group) { $keys; return }
    }
}

function Read-ClassRoots($Root, [string]$Name) {
    foreach ($childName in $Root.GetSubKeyNames()) {
        if ($childName -match $protected) { continue }
        $keyName = $Name + '\' + $childName.ToLowerInvariant()
        if ($childName -eq 'wow6432node' -and $Name -eq $classes) {
            $wow = $Root.OpenSubKey($childName)
            if ($null -ne $wow) {
                try { Read-ClassRoots $wow $keyName }
                finally { $wow.Dispose() }
            }
            continue
        }
        if ($childName.StartsWith('.') -or $childName -in $classReserved) { continue }
        $child = $Root.OpenSubKey($childName)
        if ($null -eq $child) { continue }
        try {
            if ($childName -notin $comFamilies) {
                $children = $child.GetSubKeyNames()
                if ($childName.Contains('.') -or $childName -match $product -or
                    'CLSID' -in $children -or 'CurVer' -in $children) {
                    Read-MatchedClass $child $keyName
                }
                continue
            }
            foreach ($entry in $child.GetSubKeyNames()) {
                if ($entry -match $protected) { continue }
                $leaf = $child.OpenSubKey($entry)
                if ($null -eq $leaf) { continue }
                try { Read-MatchedClass $leaf ($keyName + '\' + $entry.ToLowerInvariant()) }
                finally { $leaf.Dispose() }
            }
        } finally { $child.Dispose() }
    }
}

function Read-Autodesk($Key, [string]$Name, [bool]$UserHive) {
    if ($Name -match $protected) { return }
    $inventor = $autodesk + '\inventor\registryversion31.0'
    if ($Name -match 'nastran' -or ($UserHive -and (Test-Under $Name $inventor) -and
            $Name -match '\\addins(?:\\|$)')) {
        Read-RegSubtree $Key $Name
        return
    }
    foreach ($childName in $Key.GetSubKeyNames()) {
        if ($childName -match $protected) { continue }
        $child = $Key.OpenSubKey($childName)
        if ($null -eq $child) { continue }
        try { Read-Autodesk $child ($Name + '\' + $childName.ToLowerInvariant()) $UserHive }
        finally { $child.Dispose() }
    }
}

function Read-At($Root, [string]$Path, [string]$Mode) {
    $key = $Root.OpenSubKey($Path)
    if ($null -eq $key) { return }
    try {
        switch ($Mode) {
            'path' { Read-RegKey $key $Path -OnlyPath }
            'classes' { Read-ClassRoots $key $Path }
            'user-autodesk' { Read-Autodesk $key $Path $true }
            'machine-autodesk' { Read-Autodesk $key $Path $false }
            'tree' { Read-RegSubtree $key $Path }
            default { Read-RegKey $key $Path }
        }
    } finally { $key.Dispose() }
}

function Convert-RegRows([string]$Hive, $Keys) {
    foreach ($record in $Keys) {
        $key = Convert-Field (Protect-Text $record.Key)
        if (!$record.Values.Count) { "REG $Hive\$key |  | KEY | " }
        foreach ($value in $record.Values) {
            $name = Convert-Field (Protect-Text $value.Name)
            $data = Format-RegValue $value ($record.Key -eq 'environment' -or $record.Key -eq $machineEnvironment)
            "REG $Hive\$key | $name | $($value.Type) | $data"
        }
    }
}

function Test-RegularFolder([string]$Folder) {
    $current = [IO.DirectoryInfo]::new($Folder)
    while ($null -ne $current) {
        if (!$current.Exists -or ($current.Attributes -band [IO.FileAttributes]::ReparsePoint)) { return $false }
        $current = $current.Parent
    }
    return $true
}

function Get-LocalEntries([string]$Folder, [switch]$Directories) {
    foreach ($entry in [IO.DirectoryInfo]::new($Folder).EnumerateFileSystemInfos()) {
        if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $entry.Name -match $protected) { continue }
        if ($entry -is [IO.DirectoryInfo]) {
            if ($Directories) { $entry }
            Get-LocalEntries $entry.FullName -Directories:$Directories
        } else { $entry }
    }
}

function Get-CapturePath([string]$FullName) {
    $relative = $FullName.Substring([IO.Path]::GetPathRoot($FullName).Length).Replace('\', '/').ToLowerInvariant()
    return Convert-Field (Protect-Text $relative)
}

function Get-HashedRows([string[]]$Folders) {
    foreach ($folder in $Folders) {
        if ($folder -match $protected -or !(Test-RegularFolder $folder)) { continue }
        foreach ($entry in Get-LocalEntries $folder) {
            $stream = [IO.File]::OpenRead($entry.FullName)
            $sha = [Security.Cryptography.SHA256]::Create()
            try {
                $size = $stream.Length
                $hash = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
                "FILE $(Get-CapturePath $entry.FullName) | $size | $hash"
            } finally { $sha.Dispose(); $stream.Dispose() }
        }
    }
}

function Get-GacRows([string[]]$Folders) {
    foreach ($folder in $Folders) {
        if (!(Test-RegularFolder $folder)) { continue }
        foreach ($assembly in [IO.DirectoryInfo]::new($folder).EnumerateFileSystemInfos()) {
            if (($assembly.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
                $assembly.Name -match $protected -or $assembly.Name -notmatch 'nei|newpf|nastran') { continue }
            "FILE $(Get-CapturePath $assembly.FullName) | - | -"
            if ($assembly -is [IO.DirectoryInfo]) {
                foreach ($entry in Get-LocalEntries $assembly.FullName -Directories) {
                    "FILE $(Get-CapturePath $entry.FullName) | - | -"
                }
            }
        }
    }
}

function Get-FusionRows {
    if (!(Test-RegularFolder $logRoot)) { return }
    $pattern = '(?i)^(?:LOG:\s*)?(Calling assembly|DisplayName|Bind result)\s*[:=]\s*(.*)$'
    foreach ($entry in Get-LocalEntries $logRoot) {
        if ($entry.Extension -ne '.htm') { continue }
        $name = $entry.FullName.Substring($logRoot.Length + 1).Replace('\', '/').ToLowerInvariant()
        $name = Convert-Field (Protect-Text $name)
        "FUSION $name | file | "
        foreach ($line in [IO.File]::ReadLines($entry.FullName)) {
            $plain = [Net.WebUtility]::HtmlDecode(($line -replace '<[^>]*>', '')).Trim()
            if ($plain -notmatch $pattern) { continue }
            $label = $Matches[1].ToLowerInvariant()
            $text = $Matches[2].Trim()
            if ($text -match $protected) { $text = '<masked>' }
            "FUSION $name | $label | $(Convert-Field (Protect-Text $text))"
        }
    }
}

function Set-FusionCapture($Machine, [string]$Mode) {
    if ($Mode -eq 'on') {
        if ([IO.Directory]::Exists($logRoot) -and !(Test-RegularFolder $logRoot)) {
            throw 'The Fusion log directory must be a regular local directory.'
        }
        [void][IO.Directory]::CreateDirectory($logRoot)
        $key = $Machine.CreateSubKey($fusionRoots[0])
        try {
            $key.SetValue('LogFailures', 1, [Microsoft.Win32.RegistryValueKind]::DWord)
            $key.SetValue('LogPath', "$logRoot\", [Microsoft.Win32.RegistryValueKind]::String)
        } finally { $key.Dispose() }
    } else {
        $key = $Machine.OpenSubKey($fusionRoots[0], $true)
        if ($null -ne $key) {
            try {
                $key.DeleteValue('LogFailures', $false)
                $key.DeleteValue('LogPath', $false)
            } finally { $key.Dispose() }
        }
    }
    Write-Output "Fusion failure logging $Mode."
}

# Dry-run intentionally exits before opening a hive or inspecting a folder.
if ($DryRun) {
    if ($FusionLog -in @('on', 'off')) {
        "Would turn Fusion failure logging $FusionLog in HKLM\SOFTWARE\Microsoft\Fusion (LogFailures and LogPath)."
        if ($FusionLog -eq 'on') { 'Would use C:\fusionlog\.' }
        return
    }
    @(
        'REG HKLM and HKCU\Software\Classes, selected COM and ProgID subtrees including WOW6432Node'
        'REG HKLM and HKCU\Software\Autodesk, Nastran and per-user Inventor 2027 Addins'
        'REG machine and user Environment Path'
        'REG native and WOW64 .NETFramework, Policy\v4.0 and Fusion'
        'FILE ProgramData and AppData Autodesk\Inventor 2027\Addins'
        'FILE Program Files\Autodesk\Inventor Nastran 2027'
        'FILE both GAC_MSIL roots, selected assembly names only'
    )
    if ($FusionLog -eq 'collect') { 'FUSION C:\fusionlog\*.htm, selected diagnostic fields only' }
    return
}

if (!$Phase -and $FusionLog -notin @('on', 'off')) {
    throw 'Give -Phase before, installed or started.'
}
$registryView = if ([Environment]::Is64BitOperatingSystem) { 'Registry64' } else { 'Default' }
$machineHive = [Microsoft.Win32.RegistryKey]::OpenBaseKey('LocalMachine', $registryView)
try {
    if ($FusionLog -in @('on', 'off')) {
        Set-FusionCapture $machineHive $FusionLog
        return
    }
    if (!$Output) { $Output = "companion-capture-$Phase.txt" }
    $outputPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Output)
    if ([IO.File]::Exists($outputPath)) { throw 'The output file already exists. Use a new path.' }

    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    try {
        $account = ($identity.Name -split '\\')[-1]
    } finally { $identity.Dispose() }
    $profileRoots = @($env:USERPROFILE)
    if ($env:USERPROFILE) {
        $profileRoots += $env:USERPROFILE.Substring([IO.Path]::GetPathRoot($env:USERPROFILE).Length)
    }
    $maskRules = @(New-MaskRules $profileRoots @($env:USERNAME, $account) @($env:COMPUTERNAME))
    $userHive = [Microsoft.Win32.RegistryKey]::OpenBaseKey('CurrentUser', $registryView)
    try {
        $rows = [Collections.Generic.SortedSet[string]]::new($ordinal)
        foreach ($row in Convert-RegRows 'HKLM' @(
            Read-At $machineHive $classes 'classes'
            Read-At $machineHive $autodesk 'machine-autodesk'
            Read-At $machineHive $machineEnvironment 'path'
            foreach ($root in $dotnetRoots) {
                Read-At $machineHive $root 'key'
                Read-At $machineHive ($root + '\policy\v4.0') 'tree'
            }
            foreach ($root in $fusionRoots) { Read-At $machineHive $root 'tree' }
        )) { [void]$rows.Add($row) }
        foreach ($row in Convert-RegRows 'HKCU' @(
            Read-At $userHive $classes 'classes'
            Read-At $userHive $autodesk 'user-autodesk'
            Read-At $userHive 'environment' 'path'
        )) { [void]$rows.Add($row) }
    } finally { $userHive.Dispose() }

    $programFiles = if ($env:ProgramW6432) { $env:ProgramW6432 } else { $env:ProgramFiles }
    $folders = @(
        (Join-Path $env:ProgramData 'Autodesk\Inventor 2027\Addins')
        (Join-Path $env:APPDATA 'Autodesk\Inventor 2027\Addins')
        (Join-Path $programFiles 'Autodesk\Inventor Nastran 2027')
    )
    foreach ($row in Get-HashedRows $folders) { [void]$rows.Add($row) }
    foreach ($row in Get-GacRows @(
        (Join-Path $env:windir 'assembly\GAC_MSIL')
        (Join-Path $env:windir 'Microsoft.NET\assembly\GAC_MSIL')
    )) { [void]$rows.Add($row) }
    if ($FusionLog -eq 'collect') {
        foreach ($row in Get-FusionRows) { [void]$rows.Add($row) }
    }

    $file = [IO.File]::Open($outputPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try {
        $writer = [IO.StreamWriter]::new($file, $utf8)
        try {
            $writer.NewLine = [string][char]10
            foreach ($row in $rows) { $writer.WriteLine($row) }
        } finally { $writer.Dispose() }
    } finally { $file.Dispose() }
    Write-Output "$Phase capture: $($rows.Count) items written."
} finally { $machineHive.Dispose() }
