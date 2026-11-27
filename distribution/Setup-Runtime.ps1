[CmdletBinding()]
param(
    [switch]$Repair
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$OfficialVcRedistHelp = 'https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist/'
$LockMarkerName = '.physis-ai-runtime-lock.sha256'

function Write-Phase {
    param([string]$Message)
    Write-Host "[PHYSIS runtime] $Message"
}

function Get-Sha256Hex {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-AppRootChildPath {
    param(
        [string]$Path,
        [string]$AppRoot,
        [string]$Description
    )

    $root = [System.IO.Path]::GetFullPath($AppRoot).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    $full = [System.IO.Path]::GetFullPath($Path)
    $prefix = $root + [System.IO.Path]::DirectorySeparatorChar
    if ($full.Equals($root, [StringComparison]::OrdinalIgnoreCase) -or -not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$Description must remain below the app directory. Refusing $full"
    }
    return $full
}

function Acquire-SetupFileLock {
    param([string]$Path)

    if (Test-Path -LiteralPath $Path) {
        $existing = Get-Item -LiteralPath $Path -Force
        if ($existing.PSIsContainer -or (($existing.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw 'The app-local runtime setup lock path is not a normal file.'
        }
    }
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        try {
            return [System.IO.File]::Open($Path, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
        }
        catch [System.IO.IOException] {
            if ($attempt -eq 60) {
                throw 'Another runtime setup is still running. Wait for it to finish, then run setup again.'
            }
            Start-Sleep -Seconds 2
        }
    }
}

function Test-Sha256Text {
    param([string]$Value)
    return ($Value -match '^[0-9a-fA-F]{64}$')
}

function Normalize-PackageName {
    param([string]$Name)
    return ([regex]::Replace($Name, '[-_.]+', '-')).ToLowerInvariant()
}

function Assert-SafeArchiveEntry {
    param([string]$Name)

    $normalized = $Name.Replace('\', '/')
    if ($normalized.StartsWith('/') -or $normalized -match '^[A-Za-z]:' -or $normalized.Contains(':')) {
        throw "Unsafe archive member path: $Name"
    }
    foreach ($part in $normalized.Split('/')) {
        if ($part -eq '..') {
            throw "Unsafe archive member path: $Name"
        }
    }
}

function Get-ZipMemberText {
    param(
        [System.IO.Compression.ZipArchive]$Archive,
        [string]$MemberName
    )

    $entry = $Archive.GetEntry($MemberName)
    if ($null -eq $entry) {
        throw "The archive is missing $MemberName."
    }
    $stream = $entry.Open()
    try {
        $reader = [System.IO.StreamReader]::new($stream, [System.Text.Encoding]::UTF8, $true)
        try {
            return $reader.ReadToEnd()
        }
        finally {
            $reader.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}

function Get-WheelMetadataEntry {
    param(
        [System.IO.Compression.ZipArchive]$Archive,
        [string]$Suffix
    )

    $metadataEntries = @($Archive.Entries | Where-Object { $_.FullName -match ('^[^/]+\.dist-info/' + [regex]::Escape($Suffix) + '$') })
    if ($metadataEntries.Count -ne 1) {
        throw "Expected exactly one .dist-info/$Suffix entry in wheel; found $($metadataEntries.Count)."
    }
    return $metadataEntries[0].FullName
}

function Read-WheelMemberText {
    param(
        [System.IO.Compression.ZipArchive]$Archive,
        [string]$MemberName
    )

    $entry = $Archive.GetEntry($MemberName)
    if ($null -eq $entry) {
        throw "The wheel is missing $MemberName."
    }
    $stream = $entry.Open()
    try {
        $reader = [System.IO.StreamReader]::new($stream, [System.Text.Encoding]::UTF8, $true)
        try {
            return $reader.ReadToEnd()
        }
        finally {
            $reader.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}

function Invoke-Download {
    param(
        [string]$Uri,
        [string]$Destination,
        [string]$Description
    )

    $headers = @{ 'User-Agent' = 'PHYSIS-AI-0.4.1-runtime-setup' }
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Invoke-WebRequest -Uri $Uri -OutFile $Destination -Headers $headers -TimeoutSec 900 -MaximumRedirection 5 -UseBasicParsing
            return
        }
        catch {
            if (Test-Path -LiteralPath $Destination) {
                Remove-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue
            }
            if ($attempt -eq 3) {
                throw "Could not download $Description from its official source. $($_.Exception.Message)"
            }
            Start-Sleep -Seconds (2 * $attempt)
        }
    }
}

function Assert-HttpsHost {
    param(
        [string]$UriText,
        [string]$ExpectedHost,
        [string]$Description
    )

    $uri = [Uri]$UriText
    if ($uri.Scheme -ne 'https' -or $uri.Host -ne $ExpectedHost) {
        throw "$Description must come from https://$ExpectedHost/. Refusing $UriText"
    }
    return $uri
}

function Assert-RuntimePythonCompatibility {
    param(
        [string]$RequiresPython,
        [Version]$RuntimeVersion
    )

    if ([string]::IsNullOrWhiteSpace($RequiresPython)) {
        return
    }
    foreach ($rawSpec in $RequiresPython.Split(',')) {
        $spec = $rawSpec.Trim()
        if ($spec -match '^(>=|<=|==|!=|>|<|~=)\s*([0-9]+(?:\.[0-9]+){0,2})$') {
            $operator = $Matches[1]
            $versionText = $Matches[2]
            $parts = @($versionText.Split('.'))
            $specifiedPartCount = $parts.Count
            while ($parts.Count -lt 3) { $parts += '0' }
            $required = [Version]::new([int]$parts[0], [int]$parts[1], [int]$parts[2])
            $valid = switch ($operator) {
                '>=' { $RuntimeVersion -ge $required; break }
                '<=' { $RuntimeVersion -le $required; break }
                '>'  { $RuntimeVersion -gt $required; break }
                '<'  { $RuntimeVersion -lt $required; break }
                '==' { $RuntimeVersion -eq $required; break }
                '!=' { $RuntimeVersion -ne $required; break }
                '~=' {
                    if ($specifiedPartCount -le 2) {
                        ($RuntimeVersion -ge $required) -and ($RuntimeVersion.Major -eq $required.Major)
                    }
                    else {
                        ($RuntimeVersion -ge $required) -and ($RuntimeVersion.Major -eq $required.Major) -and ($RuntimeVersion.Minor -eq $required.Minor)
                    }
                    break
                }
            }
            if (-not $valid) {
                throw "Python $RuntimeVersion does not satisfy Requires-Python '$RequiresPython'."
            }
        }
        elseif ($spec -ne '') {
            throw "Unsupported Requires-Python specifier '$spec'; refusing to assume compatibility."
        }
    }
}

function Test-WheelArchive {
    param(
        [string]$WheelPath,
        [object]$WheelLock,
        [Version]$RuntimeVersion
    )

    $archive = [System.IO.Compression.ZipFile]::OpenRead($WheelPath)
    try {
        foreach ($entry in $archive.Entries) {
            Assert-SafeArchiveEntry -Name $entry.FullName
            $schemeMatch = [regex]::Match($entry.FullName, '^[^/]+\.data/([^/]+)(?:/|$)')
            if ($schemeMatch.Success -and @('purelib', 'platlib', 'scripts', 'headers', 'data') -notcontains $schemeMatch.Groups[1].Value) {
                throw "The locked wheel $($WheelLock.filename) uses an unsupported .data scheme: $($schemeMatch.Groups[1].Value)"
            }
        }

        $metadataPath = Get-WheelMetadataEntry -Archive $archive -Suffix 'METADATA'
        $wheelMetadataPath = Get-WheelMetadataEntry -Archive $archive -Suffix 'WHEEL'
        $metadata = Read-WheelMemberText -Archive $archive -MemberName $metadataPath
        $wheelMetadata = Read-WheelMemberText -Archive $archive -MemberName $wheelMetadataPath

        $nameMatch = [regex]::Match($metadata, '(?im)^Name:\s*(.+?)\s*$')
        $versionMatch = [regex]::Match($metadata, '(?im)^Version:\s*(.+?)\s*$')
        if (-not $nameMatch.Success -or (Normalize-PackageName $nameMatch.Groups[1].Value) -ne (Normalize-PackageName $WheelLock.name)) {
            throw "Wheel metadata name does not match $($WheelLock.name)."
        }
        if (-not $versionMatch.Success -or $versionMatch.Groups[1].Value.Trim() -ne [string]$WheelLock.version) {
            throw "Wheel metadata version does not match $($WheelLock.name) $($WheelLock.version)."
        }

        $tags = @([regex]::Matches($wheelMetadata, '(?im)^Tag:\s*(.+?)\s*$') | ForEach-Object { $_.Groups[1].Value.Trim() })
        if ($tags -notcontains [string]$WheelLock.tag) {
            throw "Wheel tags [$($tags -join ', ')] do not include the locked compatible tag $($WheelLock.tag)."
        }
        $requiresPythonMatch = [regex]::Match($metadata, '(?im)^Requires-Python:\s*(.+?)\s*$')
        if ($requiresPythonMatch.Success) {
            Assert-RuntimePythonCompatibility -RequiresPython $requiresPythonMatch.Groups[1].Value.Trim() -RuntimeVersion $RuntimeVersion
        }
    }
    finally {
        $archive.Dispose()
    }
}

function Install-WheelArchive {
    param(
        [string]$WheelPath,
        [string]$SitePackagesPath,
        [string]$RuntimeRoot
    )

    $archive = [System.IO.Compression.ZipFile]::OpenRead($WheelPath)
    try {
        foreach ($entry in $archive.Entries) {
            Assert-SafeArchiveEntry -Name $entry.FullName
            $relativeName = $entry.FullName.Replace('/', '\')
            $targetRoot = $SitePackagesPath
            $dataScheme = [regex]::Match($entry.FullName, '^[^/]+\.data/([^/]+)/(.*)$')
            if ($dataScheme.Success) {
                $relativeName = $dataScheme.Groups[2].Value.Replace('/', '\')
                switch ($dataScheme.Groups[1].Value) {
                    'purelib' { $targetRoot = $SitePackagesPath; break }
                    'platlib' { $targetRoot = $SitePackagesPath; break }
                    'scripts' { $targetRoot = Join-Path $RuntimeRoot 'Scripts'; break }
                    'headers' { $targetRoot = Join-Path $RuntimeRoot 'include'; break }
                    'data' { $targetRoot = $RuntimeRoot; break }
                    default { throw "Unsupported wheel .data scheme: $($dataScheme.Groups[1].Value)" }
                }
            }
            elseif ($entry.FullName -match '^[^/]+\.data/') {
                continue
            }
            if ([string]::IsNullOrWhiteSpace($relativeName)) {
                continue
            }
            $destination = [System.IO.Path]::GetFullPath((Join-Path $targetRoot $relativeName))
            $targetPrefix = [System.IO.Path]::GetFullPath($targetRoot).TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
            if (-not $destination.StartsWith($targetPrefix, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Wheel member resolves outside its install target: $($entry.FullName)"
            }
            if ($entry.FullName.EndsWith('/')) {
                [System.IO.Directory]::CreateDirectory($destination) | Out-Null
                continue
            }
            $parent = [System.IO.Path]::GetDirectoryName($destination)
            [System.IO.Directory]::CreateDirectory($parent) | Out-Null
            $inputStream = $entry.Open()
            $outputStream = [System.IO.File]::Open($destination, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
            try {
                $inputStream.CopyTo($outputStream)
            }
            finally {
                $outputStream.Dispose()
                $inputStream.Dispose()
            }
        }
    }
    finally {
        $archive.Dispose()
    }
}

function Write-NativeDllSitecustomize {
    param(
        [string]$SitePackagesPath,
        [object[]]$DllDirectories
    )

    $siteRelative = 'runtime/Lib/site-packages'
    $dllNames = @()
    foreach ($dllPath in $DllDirectories) {
        $relative = ([string]$dllPath).Replace('\', '/')
        if (-not $relative.StartsWith($siteRelative + '/', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Native DLL directory must be inside ${siteRelative}: $dllPath"
        }
        $tail = $relative.Substring(($siteRelative + '/').Length)
        if ($tail -notmatch '^[A-Za-z0-9_.-]+(?:[/\\][A-Za-z0-9_.-]+)*$') {
            throw "Unsafe native DLL directory in runtime lock: $dllPath"
        }
        $dllNames += "    '$($tail.Replace('/', '\'))'"
    }

    $quotedNames = ($dllNames -join ",`r`n")
    $pythonText = @"
import os as _os
from pathlib import Path as _Path

_site = _Path(__file__).resolve().parent
_physis_dll_handles = []
for _relative in (
$quotedNames
):
    _directory = _site / _relative
    if _directory.is_dir():
        _physis_dll_handles.append(_os.add_dll_directory(str(_directory)))
"@
    $pythonPath = Join-Path $SitePackagesPath 'sitecustomize.py'
    [System.IO.File]::WriteAllText($pythonPath, $pythonText, [System.Text.UTF8Encoding]::new($false))
}

function Invoke-RuntimeSelfCheck {
    param(
        [string]$PythonPath,
        [string]$ExpectedVersion,
        [string]$AppRoot
    )

    $code = @"
import importlib
import struct
import sys

expected = tuple(int(part) for part in "$ExpectedVersion".split("."))
if sys.version_info[:3] != expected:
    raise RuntimeError(f"Expected CPython {expected}, got {sys.version.split()[0]}")
if struct.calcsize("P") != 8:
    raise RuntimeError("The installed Python runtime is not 64-bit")

for module in (
    "fastapi", "httpx", "numpy", "pydantic", "dotenv", "scipy", "uvicorn",
    "pypdf", "sympy", "annotated_doc", "annotated_types", "anyio", "certifi",
    "click", "h11", "httpcore", "idna", "mpmath", "opentelemetry",
    "pydantic_core", "starlette", "typing_extensions", "typing_inspection",
):
    importlib.import_module(module)

import numpy as np
from scipy.linalg import solve
matrix = np.array([[3.0, 1.0], [1.0, 2.0]], dtype=np.float64)
vector = np.array([9.0, 8.0], dtype=np.float64)
if not np.allclose(solve(matrix, vector), np.array([2.0, 3.0])):
    raise RuntimeError("NumPy/SciPy numerical self-check returned an unexpected result")
print("CPython, locked imports, NumPy and SciPy passed")
"@
    $checkScript = Join-Path $AppRoot ('.runtime-self-check-' + [Guid]::NewGuid().ToString('N') + '.py')
    $checkScript = Assert-AppRootChildPath -Path $checkScript -AppRoot $AppRoot -Description 'Runtime self-check script'
    [System.IO.File]::WriteAllText($checkScript, $code, [System.Text.UTF8Encoding]::new($false))
    try {
        $checkOutput = (& $PythonPath $checkScript 2>&1 | Out-String).Trim()
        $checkExitCode = $LASTEXITCODE
        if ($checkExitCode -ne 0) {
            throw "Runtime import/numerical verification failed with exit code $checkExitCode. $checkOutput"
        }
        if (-not [string]::IsNullOrWhiteSpace($checkOutput)) { Write-Host $checkOutput }
    }
    finally {
        if (Test-Path -LiteralPath $checkScript) {
            $safeCheckScript = Assert-AppRootChildPath -Path $checkScript -AppRoot $AppRoot -Description 'Runtime self-check cleanup'
            Remove-Item -LiteralPath $safeCheckScript -Force
        }
    }
}

function Show-VcRuntimeGuidance {
    Write-Host ''
    Write-Host 'A native Python dependency could not load. The delivered Python ZIP includes its app-local Visual C++ runtime files.' -ForegroundColor Yellow
    Write-Host 'If this Windows installation is missing a system Universal C Runtime component, follow Microsoft''s official x64 Visual C++ Redistributable instructions:' -ForegroundColor Yellow
    Write-Host $OfficialVcRedistHelp -ForegroundColor Yellow
    Write-Host 'After installing the prerequisite, run Setup-Runtime.cmd again.' -ForegroundColor Yellow
}

$setupLockStream = $null
try {
    if (-not [Environment]::Is64BitOperatingSystem -or [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString() -ne 'X64') {
        throw 'This runtime bootstrap requires 64-bit Windows.'
    }
    if ($PSVersionTable.PSVersion.Major -lt 5) {
        throw 'PowerShell 5.1 or newer is required.'
    }
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    }
    catch {
        # PowerShell 7 uses the operating system TLS defaults.
    }

    $appRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
    $setupLockPath = Assert-AppRootChildPath -Path (Join-Path $appRoot '.runtime-setup.lock') -AppRoot $appRoot -Description 'Runtime setup lock'
    $setupLockStream = Acquire-SetupFileLock -Path $setupLockPath
    $lockPath = Join-Path $appRoot 'runtime-lock.json'
    if (-not (Test-Path -LiteralPath $lockPath -PathType Leaf)) {
        throw "runtime-lock.json is missing next to Setup-Runtime.ps1: $appRoot"
    }
    $lockDigest = (Get-Sha256Hex -Path $lockPath)
    $lock = [System.IO.File]::ReadAllText($lockPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    if ([int]$lock.schema_version -ne 1 -or [string]$lock.product.version -ne '0.4.1') {
        throw 'The runtime lock schema or product version is not supported by this setup script.'
    }
    if ([string]$lock.installation.runtime_directory -ne 'runtime') {
        throw 'The runtime lock must install into the app-local ./runtime directory.'
    }
    if ([string]$lock.runtime.architecture -ne 'win-amd64' -or [string]$lock.runtime.format -ne 'embeddable-zip') {
        throw 'The runtime lock does not describe the supported x64 CPython embeddable archive.'
    }
    if ([string]$lock.runtime.version -notmatch '^3\.\d+\.\d+$') {
        throw 'The runtime lock contains an invalid CPython version.'
    }
    $runtimeVersion = [Version]$lock.runtime.version
    $pythonStem = 'python' + $runtimeVersion.Major + $runtimeVersion.Minor
    $pythonDllName = $pythonStem + '.dll'
    $pythonZipName = $pythonStem + '.zip'
    $pythonPathName = $pythonStem + '._pth'
    $nativeWheelTag = 'cp' + $runtimeVersion.Major + $runtimeVersion.Minor + '-cp' + $runtimeVersion.Major + $runtimeVersion.Minor + '-win_amd64'
    if ([string]$lock.runtime.filename -ne ('python-' + $lock.runtime.version + '-embed-amd64.zip')) {
        throw 'The CPython archive filename does not match its locked version.'
    }
    if ([string]$lock.installation.python_path_file -ne ('runtime/' + $pythonPathName)) {
        throw 'The Python path file in the runtime lock does not match the interpreter version.'
    }
    if (-not (Test-Sha256Text ([string]$lock.runtime.sha256))) {
        throw 'The Python runtime SHA-256 in runtime-lock.json is invalid.'
    }

    $runtimeTarget = Join-Path $appRoot 'runtime'
    $runtimePython = Join-Path $runtimeTarget 'python.exe'
    $runtimeMarker = Join-Path $runtimeTarget $LockMarkerName
    if (Test-Path -LiteralPath $runtimeTarget) {
        $runtimeItem = Get-Item -LiteralPath $runtimeTarget -Force
        if (-not $runtimeItem.PSIsContainer -or (($runtimeItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw 'The ./runtime target exists as a file or reparse point; it was left untouched.'
        }
        if (-not (Test-Path -LiteralPath $runtimeMarker -PathType Leaf)) {
            throw 'An unmanaged ./runtime directory already exists. It was left untouched; move it aside before setup.'
        }
        $installedLockDigest = (Get-Content -LiteralPath $runtimeMarker -Raw -ErrorAction Stop).Trim()
        if (-not (Test-Sha256Text $installedLockDigest)) {
            throw 'The existing ./runtime setup marker is invalid; it was left untouched.'
        }
        if ($installedLockDigest -eq $lockDigest -and (Test-Path -LiteralPath $runtimePython -PathType Leaf) -and -not $Repair) {
            Write-Phase 'Checking the existing app-local runtime.'
            try {
                Invoke-RuntimeSelfCheck -PythonPath $runtimePython -ExpectedVersion ([string]$lock.runtime.version) -AppRoot $appRoot
                Write-Phase 'This exact runtime is already installed and verified.'
                exit 0
            }
            catch {
                $selfCheckFailure = $_.Exception.Message
                Write-Phase 'The existing app-local runtime needs repair; the original will remain in place until a replacement passes verification.'
            }
        }
    }

    foreach ($wheel in $lock.wheels) {
        if (-not (Test-Sha256Text ([string]$wheel.sha256))) {
            throw "Invalid SHA-256 in lock for $($wheel.name)."
        }
        if ([string]$wheel.install_target -ne 'runtime/Lib/site-packages') {
            throw "Unsupported install target in lock for $($wheel.name)."
        }
        if (([string]$wheel.tag -ne 'py3-none-any') -and ([string]$wheel.tag -ne $nativeWheelTag)) {
            throw "Unsupported Python wheel tag for $($wheel.name): $($wheel.tag)"
        }
    }

    $stageName = '.runtime-stage-' + [Guid]::NewGuid().ToString('N')
    $stageRoot = Join-Path $appRoot $stageName
    $stageRuntime = Join-Path $stageRoot 'runtime'
    $downloadRoot = Join-Path $stageRoot 'downloads'
    $backupName = '.runtime-backup-' + [Guid]::NewGuid().ToString('N')
    $runtimeBackup = Join-Path $appRoot $backupName
    $stageRoot = Assert-AppRootChildPath -Path $stageRoot -AppRoot $appRoot -Description 'Runtime staging directory'
    $stageRuntime = Assert-AppRootChildPath -Path $stageRuntime -AppRoot $appRoot -Description 'Staged runtime'
    $downloadRoot = Assert-AppRootChildPath -Path $downloadRoot -AppRoot $appRoot -Description 'Runtime downloads directory'
    $runtimeBackup = Assert-AppRootChildPath -Path $runtimeBackup -AppRoot $appRoot -Description 'Runtime backup directory'
    $runtimeTarget = Assert-AppRootChildPath -Path $runtimeTarget -AppRoot $appRoot -Description 'Runtime target'
    $backupMoved = $false
    $replacementMoved = $false
    [System.IO.Directory]::CreateDirectory($stageRuntime) | Out-Null
    [System.IO.Directory]::CreateDirectory($downloadRoot) | Out-Null

    try {
        $runtimeUri = Assert-HttpsHost -UriText ([string]$lock.runtime.url) -ExpectedHost 'www.python.org' -Description 'CPython runtime archive'
        if (-not $runtimeUri.AbsolutePath.EndsWith('/' + [string]$lock.runtime.filename, [StringComparison]::Ordinal)) {
            throw 'The Python archive URL does not match the locked filename.'
        }
        $runtimeArchive = Join-Path $downloadRoot ([string]$lock.runtime.filename)
        Write-Phase "Downloading official CPython $($lock.runtime.version) x64 embeddable archive."
        Invoke-Download -Uri $runtimeUri.AbsoluteUri -Destination $runtimeArchive -Description 'the official CPython embeddable archive'
        $runtimeHash = Get-Sha256Hex -Path $runtimeArchive
        if ($runtimeHash -ne ([string]$lock.runtime.sha256).ToLowerInvariant()) {
            throw "CPython archive SHA-256 mismatch. Expected $($lock.runtime.sha256), received $runtimeHash."
        }
        Write-Phase 'CPython archive SHA-256 matches the official Python.org SPDX lock.'

        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $runtimeZip = [System.IO.Compression.ZipFile]::OpenRead($runtimeArchive)
        try {
            foreach ($entry in $runtimeZip.Entries) {
                Assert-SafeArchiveEntry -Name $entry.FullName
            }
            [System.IO.Compression.ZipFile]::ExtractToDirectory($runtimeArchive, $stageRuntime)
        }
        finally {
            $runtimeZip.Dispose()
        }

        foreach ($requiredFile in @('python.exe', $pythonDllName, $pythonZipName, $pythonPathName)) {
            if (-not (Test-Path -LiteralPath (Join-Path $stageRuntime $requiredFile) -PathType Leaf)) {
                throw "Official CPython archive is missing $requiredFile."
            }
        }
        foreach ($runtimeDll in $lock.runtime.included_app_local_runtime_files) {
            if (-not (Test-Path -LiteralPath (Join-Path $stageRuntime ([string]$runtimeDll)) -PathType Leaf)) {
                throw "The official CPython archive is missing app-local $runtimeDll."
            }
        }

        $pthPath = Join-Path $stageRuntime $pythonPathName
        $pthLines = @([System.IO.File]::ReadAllLines($pthPath, [System.Text.Encoding]::ASCII))
        $filteredLines = @($pthLines | Where-Object { $_ -ne 'Lib/site-packages' -and $_ -ne 'Lib\site-packages' })
        $siteEnabled = $false
        for ($index = 0; $index -lt $filteredLines.Count; $index++) {
            if ($filteredLines[$index] -match '^\s*#\s*import\s+site\s*$') {
                $filteredLines[$index] = 'import site'
                $siteEnabled = $true
            }
            elseif ($filteredLines[$index] -match '^\s*import\s+site\s*$') {
                $siteEnabled = $true
            }
        }
        if (-not $siteEnabled) { $filteredLines += 'import site' }
        $filteredLines += 'Lib\site-packages'
        [System.IO.File]::WriteAllLines($pthPath, [string[]]$filteredLines, [System.Text.Encoding]::ASCII)

        $sitePackages = Join-Path $stageRuntime 'Lib\site-packages'
        [System.IO.Directory]::CreateDirectory($sitePackages) | Out-Null
        Write-Phase 'Resolving the locked wheel files through the official PyPI JSON API.'
        $wheelArchives = @()
        $counter = 0
        foreach ($wheel in $lock.wheels) {
            $counter++
            $package = [string]$wheel.name
            $version = [string]$wheel.version
            $expectedJsonUrl = "https://pypi.org/pypi/$package/$version/json"
            if ([string]$wheel.pypi_json_url -ne $expectedJsonUrl) {
                throw "PyPI JSON URL does not match $package $version in the runtime lock."
            }
            Assert-HttpsHost -UriText ([string]$wheel.pypi_json_url) -ExpectedHost 'pypi.org' -Description "PyPI metadata for $package" | Out-Null
            $metadata = Invoke-RestMethod -Uri ([string]$wheel.pypi_json_url) -Headers @{ 'User-Agent' = 'PHYSIS-AI-0.4.1-runtime-setup' } -TimeoutSec 90
            if ((Normalize-PackageName ([string]$metadata.info.name)) -ne (Normalize-PackageName $package) -or [string]$metadata.info.version -ne $version) {
                throw "Official PyPI metadata did not identify the exact locked release $package $version."
            }
            $wheelMatches = @($metadata.urls | Where-Object { $_.filename -ceq [string]$wheel.filename })
            if ($wheelMatches.Count -ne 1) {
                throw "Official PyPI does not provide exactly one locked wheel file $($wheel.filename)."
            }
            $artifact = $wheelMatches[0]
            if ([string]$artifact.packagetype -ne 'bdist_wheel' -or $artifact.yanked -eq $true) {
                throw "The locked artifact $($wheel.filename) is not an unyanked wheel."
            }
            if ([string]$artifact.digests.sha256 -ne ([string]$wheel.sha256).ToLowerInvariant()) {
                throw "PyPI JSON SHA-256 does not match the lock for $($wheel.filename)."
            }
            if ([int64]$artifact.size -le 0 -or [int64]$artifact.size -gt 300000000) {
                throw "PyPI reported an invalid or unexpectedly large wheel size for $($wheel.filename)."
            }
            Assert-RuntimePythonCompatibility -RequiresPython ([string]$artifact.requires_python) -RuntimeVersion $runtimeVersion
            $wheelUri = Assert-HttpsHost -UriText ([string]$artifact.url) -ExpectedHost 'files.pythonhosted.org' -Description "wheel $($wheel.filename)"
            $wheelPath = Join-Path $downloadRoot ([string]$wheel.filename)
            Write-Phase "Downloading wheel $counter/$($lock.wheels.Count): $package $version."
            Invoke-Download -Uri $wheelUri.AbsoluteUri -Destination $wheelPath -Description "PyPI wheel $($wheel.filename)"
            if ((Get-Item -LiteralPath $wheelPath).Length -ne [int64]$artifact.size) {
                throw "Downloaded wheel size does not match PyPI for $($wheel.filename)."
            }
            $wheelHash = Get-Sha256Hex -Path $wheelPath
            if ($wheelHash -ne ([string]$wheel.sha256).ToLowerInvariant()) {
                throw "SHA-256 mismatch for $($wheel.filename). Expected $($wheel.sha256), received $wheelHash."
            }
            Test-WheelArchive -WheelPath $wheelPath -WheelLock $wheel -RuntimeVersion $runtimeVersion
            $wheelArchives += [pscustomobject]@{ Path = $wheelPath; Lock = $wheel }
        }

        Write-Phase "Installing $($wheelArchives.Count) verified wheels into the staged runtime."
        foreach ($wheelArchive in $wheelArchives) {
            Install-WheelArchive -WheelPath $wheelArchive.Path -SitePackagesPath $sitePackages -RuntimeRoot $stageRuntime
        }
        Write-NativeDllSitecustomize -SitePackagesPath $sitePackages -DllDirectories @($lock.installation.native_dll_directories)

        $stagePython = Join-Path $stageRuntime 'python.exe'
        Write-Phase 'Checking all locked imports and exercising NumPy/SciPy native DLL loading.'
        try {
            Invoke-RuntimeSelfCheck -PythonPath $stagePython -ExpectedVersion ([string]$lock.runtime.version) -AppRoot $appRoot
        }
        catch {
            if ([string]$_.Exception.Message -match '(?i)(DLL load failed|VCRUNTIME|api-ms-win-crt|WinError 126|0xC0000135|-1073741515)') {
                Show-VcRuntimeGuidance
            }
            throw
        }

        [System.IO.File]::WriteAllText((Join-Path $stageRuntime $LockMarkerName), ($lockDigest + "`n"), [System.Text.Encoding]::ASCII)
        Remove-Item -LiteralPath (Assert-AppRootChildPath -Path $downloadRoot -AppRoot $appRoot -Description 'Runtime downloads cleanup') -Recurse -Force

        if (Test-Path -LiteralPath $runtimeTarget) {
            $oldItem = Get-Item -LiteralPath $runtimeTarget -Force
            if (($oldItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'The ./runtime target became a reparse point during setup; refusing to replace it.'
            }
            $safeTarget = Assert-AppRootChildPath -Path $runtimeTarget -AppRoot $appRoot -Description 'Runtime target'
            $safeBackup = Assert-AppRootChildPath -Path $runtimeBackup -AppRoot $appRoot -Description 'Runtime backup'
            [System.IO.Directory]::Move($safeTarget, $safeBackup)
            $backupMoved = $true
        }

        try {
            $safeStageRuntime = Assert-AppRootChildPath -Path $stageRuntime -AppRoot $appRoot -Description 'Staged runtime'
            $safeTarget = Assert-AppRootChildPath -Path $runtimeTarget -AppRoot $appRoot -Description 'Runtime target'
            [System.IO.Directory]::Move($safeStageRuntime, $safeTarget)
            $replacementMoved = $true
        }
        catch {
            if ($backupMoved -and -not (Test-Path -LiteralPath $runtimeTarget)) {
                $safeBackup = Assert-AppRootChildPath -Path $runtimeBackup -AppRoot $appRoot -Description 'Runtime backup'
                $safeTarget = Assert-AppRootChildPath -Path $runtimeTarget -AppRoot $appRoot -Description 'Runtime target'
                [System.IO.Directory]::Move($safeBackup, $safeTarget)
                $backupMoved = $false
            }
            throw
        }

        if ($backupMoved) {
            try {
                Remove-Item -LiteralPath (Assert-AppRootChildPath -Path $runtimeBackup -AppRoot $appRoot -Description 'Runtime backup cleanup') -Recurse -Force
                $backupMoved = $false
            }
            catch {
                Write-Phase "The new runtime is installed; the previous runtime backup remains in the app folder as $backupName."
            }
        }
        Write-Phase 'Runtime installation completed and passed verification.'
        Write-Host 'Next: run Start-PHYSIS.cmd.'
    }
    finally {
        if (Test-Path -LiteralPath $stageRoot) {
            try { Remove-Item -LiteralPath (Assert-AppRootChildPath -Path $stageRoot -AppRoot $appRoot -Description 'Runtime staging cleanup') -Recurse -Force } catch { }
        }
    }
}
catch {
    $failureMessage = $_.Exception.Message
    if (-not [string]::IsNullOrWhiteSpace([string]$appRoot)) {
        $failureMessage = $failureMessage.Replace([string]$appRoot, '<app folder>')
    }
    $failureLine = $_.InvocationInfo.ScriptLineNumber
    $failureContext = ([string]$_.InvocationInfo.Line).Trim()
    if ($failureLine -gt 0) {
        Write-Host "[PHYSIS runtime] Setup failed at script line ${failureLine}: $failureMessage" -ForegroundColor Red
        if (-not [string]::IsNullOrWhiteSpace($failureContext)) {
            Write-Host "Context: $failureContext" -ForegroundColor DarkYellow
        }
    }
    else {
        Write-Host "[PHYSIS runtime] Setup failed: $failureMessage" -ForegroundColor Red
    }
    exit 1
}
finally {
    if ($null -ne $setupLockStream) {
        $setupLockStream.Dispose()
    }
}
