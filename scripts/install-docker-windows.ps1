#requires -RunAsAdministrator

$ErrorActionPreference = "Stop"

function Test-FeatureEnabled {
    param([Parameter(Mandatory = $true)][string]$Name)

    $feature = Get-WindowsOptionalFeature -Online -FeatureName $Name
    return $feature.State -eq "Enabled"
}

$wslEnabled = Test-FeatureEnabled -Name "Microsoft-Windows-Subsystem-Linux"
$vmPlatformEnabled = Test-FeatureEnabled -Name "VirtualMachinePlatform"

if (-not $wslEnabled) {
    Enable-WindowsOptionalFeature `
        -Online `
        -FeatureName "Microsoft-Windows-Subsystem-Linux" `
        -All `
        -NoRestart
}

if (-not $vmPlatformEnabled) {
    Enable-WindowsOptionalFeature `
        -Online `
        -FeatureName "VirtualMachinePlatform" `
        -All `
        -NoRestart
}

if (-not $wslEnabled -or -not $vmPlatformEnabled) {
    Write-Host ""
    Write-Host "WSL and Virtual Machine Platform were enabled." -ForegroundColor Green
    Write-Host "Restart Windows, then run this same script again as Administrator." -ForegroundColor Yellow
    exit 3010
}

wsl.exe --update
if ($LASTEXITCODE -ne 0) {
    throw "wsl --update failed with exit code $LASTEXITCODE"
}

wsl.exe --set-default-version 2
if ($LASTEXITCODE -ne 0) {
    throw "Could not set WSL 2 as the default version."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$installer = Join-Path $projectRoot "DockerDesktopInstaller.exe"

if (-not (Test-Path -LiteralPath $installer)) {
    Write-Host "Downloading Docker Desktop from the official Docker endpoint..."
    Invoke-WebRequest `
        -UseBasicParsing `
        -Uri "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe" `
        -OutFile $installer
}

Write-Host "Installing Docker Desktop..."
$installProcess = Start-Process `
    -FilePath $installer `
    -ArgumentList @(
        "install",
        "--accept-license",
        "--backend=wsl-2",
        "--no-windows-containers"
    ) `
    -Wait `
    -PassThru

if ($installProcess.ExitCode -notin @(0, 3010)) {
    throw "Docker Desktop installer failed with exit code $($installProcess.ExitCode)"
}

$dockerBin = "C:\Program Files\Docker\Docker\resources\bin"
if (Test-Path -LiteralPath $dockerBin) {
    $env:Path = "$dockerBin;$env:Path"
}

Write-Host ""
Write-Host "Docker Desktop installation completed." -ForegroundColor Green
Write-Host "Start Docker Desktop and wait for the engine to become ready." -ForegroundColor Yellow
Write-Host "Then run: docker version; docker compose version"

