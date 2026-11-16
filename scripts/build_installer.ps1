[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$vendorName = 'ViGEmBus_1.22.0_x64_x86_arm64.exe'
$vendorUrl = 'https://github.com/nefarius/ViGEmBus/releases/download/v1.22.0/ViGEmBus_1.22.0_x64_x86_arm64.exe'
$vendorSha256 = '89220A7865076B342892F98865F3499FB7C4CFD673159E89D352C360FD014C6A'
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)

function Stop-Build([string]$Message) {
    throw "VPadConnect installer build failed: $Message"
}

function Find-InnoCompiler {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
        (Join-Path $projectRoot 'build\tools\Inno Setup 6\ISCC.exe')
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
    $candidates = @($candidates)

    if ($candidates.Count -gt 0) {
        return $candidates[0]
    }
    return $null
}

Push-Location $projectRoot
try {
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $python) {
        Stop-Build 'Python 3.12 was not found on PATH.'
    }

    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'splash.png') -PathType Leaf)) {
        Stop-Build 'The root splash.png artwork required by the one-file build was not found.'
    }

    $pythonVersion = (& $python.Source --version 2>&1 | Out-String).Trim()
    if ($pythonVersion -notmatch '^Python 3\.12\.') {
        Stop-Build "Python 3.12 is required; found '$pythonVersion'."
    }

    & $python.Source -m PyInstaller --version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Stop-Build 'PyInstaller is unavailable in the selected Python 3.12 environment.'
    }

    $innoCompiler = Find-InnoCompiler
    if (-not $innoCompiler) {
        Stop-Build 'Inno Setup 6 (ISCC.exe) was not found. Install Inno Setup 6 and rerun this script.'
    }

    $versionText = Get-Content -LiteralPath 'core\version.py' -Raw
    $versionMatch = [regex]::Match(
        $versionText,
        '(?m)^VERSION\s*=\s*"(?<version>[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?)"'
    )
    if (-not $versionMatch.Success) {
        Stop-Build 'Could not read an application version from core/version.py.'
    }
    $appVersion = $versionMatch.Groups['version'].Value
    if ($appVersion -match '^(?<major>[0-9]+)\.(?<minor>[0-9]+)\.(?<patch>[0-9]+)-beta\.(?<beta>[0-9]+)$') {
        $appFileVersion = "$($Matches.major).$($Matches.minor).$($Matches.patch).$($Matches.beta)"
    } elseif ($appVersion -match '^(?<major>[0-9]+)\.(?<minor>[0-9]+)\.(?<patch>[0-9]+)$') {
        $appFileVersion = "$($Matches.major).$($Matches.minor).$($Matches.patch).0"
    } else {
        Stop-Build "Cannot encode '$appVersion' in Windows file version metadata."
    }

    $buildDir = Join-Path $projectRoot 'build'
    $vendorDir = Join-Path $buildDir 'vendor'
    $defaultDir = Join-Path $buildDir 'installer-support'
    $stagingDir = Join-Path $buildDir 'installer-output'
    $distDir = Join-Path $projectRoot 'dist'
    $vendorPath = Join-Path $vendorDir $vendorName
    $markerPath = Join-Path $defaultDir 'vpadconnect.installed'
    $defaultsPath = Join-Path $defaultDir 'settings.conf'

    New-Item -ItemType Directory -Path $vendorDir, $defaultDir, $stagingDir, $distDir -Force | Out-Null

    # Build against the committed default settings, not the local runtime file,
    # which may contain personal controller preferences.
    $defaultSettings = & git show 'HEAD:config/settings.conf'
    if ($LASTEXITCODE -ne 0 -or -not $defaultSettings) {
        Stop-Build 'Could not read the tracked config/settings.conf default from HEAD.'
    }
    [System.IO.File]::WriteAllText($defaultsPath, (($defaultSettings -join "`n") + "`n"), $utf8NoBom)
    [System.IO.File]::WriteAllText($markerPath, "installer-managed`n", $utf8NoBom)

    if (Test-Path -LiteralPath $vendorPath -PathType Leaf) {
        $existingHash = (Get-FileHash -LiteralPath $vendorPath -Algorithm SHA256).Hash
    } else {
        $existingHash = ''
    }

    if ($existingHash -ne $vendorSha256) {
        $downloadPath = "$vendorPath.download"
        Remove-Item -LiteralPath $downloadPath -Force -ErrorAction SilentlyContinue
        Write-Host 'Downloading the official ViGEmBus 1.22.0 installer...'
        try {
            Invoke-WebRequest -Uri $vendorUrl -OutFile $downloadPath -UseBasicParsing
        } catch {
            Remove-Item -LiteralPath $downloadPath -Force -ErrorAction SilentlyContinue
            Stop-Build "Official ViGEmBus download failed: $($_.Exception.Message)"
        }
        $downloadHash = (Get-FileHash -LiteralPath $downloadPath -Algorithm SHA256).Hash
        if ($downloadHash -ne $vendorSha256) {
            Remove-Item -LiteralPath $downloadPath -Force -ErrorAction SilentlyContinue
            Stop-Build "Downloaded ViGEmBus SHA-256 mismatch (got $downloadHash)."
        }
        Move-Item -LiteralPath $downloadPath -Destination $vendorPath -Force
    }

    $verifiedVendorHash = (Get-FileHash -LiteralPath $vendorPath -Algorithm SHA256).Hash
    if ($verifiedVendorHash -ne $vendorSha256) {
        Stop-Build "ViGEmBus payload SHA-256 mismatch (got $verifiedVendorHash)."
    }

    $freshPyInstallerOutput = Join-Path $buildDir 'pyinstaller-dist'
    $pyInstallerWork = Join-Path $buildDir 'pyinstaller-onefile'
    New-Item -ItemType Directory -Path $freshPyInstallerOutput -Force | Out-Null
    $oldPyInstallerExe = Join-Path $freshPyInstallerOutput 'VPadConnect.exe'
    Remove-Item -LiteralPath $oldPyInstallerExe -Force -ErrorAction SilentlyContinue

    $env:VPADCONNECT_DEFAULT_SETTINGS = $defaultsPath
    try {
        Write-Host 'Building the VPadConnect one-file executable with PyInstaller...'
        & $python.Source -m PyInstaller --clean --noconfirm `
            --distpath $freshPyInstallerOutput `
            --workpath $pyInstallerWork `
            'VPadConnect_onefile.spec'
        if ($LASTEXITCODE -ne 0) {
            Stop-Build "PyInstaller exited with code $LASTEXITCODE."
        }
    } finally {
        Remove-Item Env:\VPADCONNECT_DEFAULT_SETTINGS -ErrorAction SilentlyContinue
    }

    if (-not (Test-Path -LiteralPath $oldPyInstallerExe -PathType Leaf)) {
        Stop-Build 'PyInstaller did not produce build\pyinstaller-dist\VPadConnect.exe.'
    }
    Copy-Item -LiteralPath $oldPyInstallerExe -Destination (Join-Path $distDir 'VPadConnect.exe') -Force

    $stagedInstaller = Join-Path $stagingDir 'VPadConnect-Setup.exe'
    Remove-Item -LiteralPath $stagedInstaller -Force -ErrorAction SilentlyContinue
    Write-Host "Compiling the Inno Setup installer with $innoCompiler..."
    & $innoCompiler "/DProductVersion=$appVersion" "/DProductFileVersion=$appFileVersion" "/O$stagingDir" 'installer\VPadConnect.iss'
    if ($LASTEXITCODE -ne 0) {
        Stop-Build "Inno Setup compiler exited with code $LASTEXITCODE."
    }
    if (-not (Test-Path -LiteralPath $stagedInstaller -PathType Leaf)) {
        Stop-Build 'Inno Setup completed without producing VPadConnect-Setup.exe.'
    }

    $stagedSize = (Get-Item -LiteralPath $stagedInstaller).Length
    if ($stagedSize -lt 10MB) {
        Stop-Build "The staged installer is unexpectedly small ($stagedSize bytes); refusing to publish it."
    }
    Copy-Item -LiteralPath $stagedInstaller -Destination (Join-Path $distDir 'VPadConnect-Setup.exe') -Force

    $installerPath = Join-Path $distDir 'VPadConnect-Setup.exe'
    $installerHash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
    [System.IO.File]::WriteAllText(
        (Join-Path $distDir 'SHA256SUMS.txt'),
        "$installerHash  VPadConnect-Setup.exe`n",
        [System.Text.Encoding]::ASCII
    )

    Write-Host ''
    Write-Host 'Installer build completed.'
    Write-Host "Application: $((Get-Item -LiteralPath (Join-Path $distDir 'VPadConnect.exe')).Length) bytes"
    Write-Host "Installer:   $installerPath ($stagedSize bytes)"
    Write-Host "SHA-256:     $installerHash"
    Write-Host "ViGEmBus:    $verifiedVendorHash (verified)"
} finally {
    Pop-Location
}
