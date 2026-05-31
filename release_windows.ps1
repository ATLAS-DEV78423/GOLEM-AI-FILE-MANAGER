$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Get-GolemVersion {
  $version = $env:GOLEM_VERSION
  if ($version) { return $version }

  $match = Select-String -Path .\golem\constants.py -Pattern 'APP_VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
  if ($match -and $match.Matches.Count -gt 0) {
    return $match.Matches[0].Groups[1].Value
  }

  return '2.0.0'
}

function Get-Signtool {
  $tool = Get-Command signtool.exe -ErrorAction SilentlyContinue
  if ($tool) { return $tool.Source }
  throw "signtool.exe was not found. Install the Windows SDK or set it on PATH."
}

function Sign-Artifact {
  param(
    [Parameter(Mandatory=$true)][string]$PathToFile
  )

  if (-not (Test-Path $PathToFile)) {
    throw "Cannot sign missing file: $PathToFile"
  }

  if ($env:GOLEM_SKIP_SIGNING -eq '1') {
    Write-Host "Skipping signing for $PathToFile"
    return
  }

  $signtool = Get-Signtool
  $timestamp = $env:GOLEM_SIGN_TIMESTAMP_URL
  if (-not $timestamp) {
    $timestamp = 'http://timestamp.digicert.com'
  }

  $args = @('sign', '/fd', 'SHA256', '/td', 'SHA256', '/tr', $timestamp)
  if ($env:GOLEM_SIGN_PFX_PATH) {
    if (-not (Test-Path $env:GOLEM_SIGN_PFX_PATH)) {
      throw "GOLEM_SIGN_PFX_PATH does not exist: $env:GOLEM_SIGN_PFX_PATH"
    }
    $args += '/f', $env:GOLEM_SIGN_PFX_PATH
    if (-not $env:GOLEM_SIGN_PFX_PASSWORD) {
      throw "GOLEM_SIGN_PFX_PASSWORD is required when using GOLEM_SIGN_PFX_PATH."
    }
    $args += '/p', $env:GOLEM_SIGN_PFX_PASSWORD
  }
  elseif ($env:GOLEM_SIGN_CERT_SHA1) {
    $args += '/sha1', $env:GOLEM_SIGN_CERT_SHA1
  }
  else {
    throw "Set GOLEM_SIGN_PFX_PATH/GOLEM_SIGN_PFX_PASSWORD or GOLEM_SIGN_CERT_SHA1 to enable Windows signing."
  }

  $args += $PathToFile
  & $signtool @args
}

$version = Get-GolemVersion
Write-Host "Building Windows installers for version $version"

& .\build_windows_installer.ps1

$dist = Join-Path $root 'dist'
$appExe = Join-Path $dist 'GOLEM\GOLEM.exe'
$installerExe = Join-Path $dist 'GOLEM-Setup.exe'

Sign-Artifact -PathToFile $appExe
Sign-Artifact -PathToFile $installerExe

$releaseDir = Join-Path $dist 'releases\windows'
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

$versionedApp = Join-Path $releaseDir "GOLEM-$version-windows.exe"
$versionedInstaller = Join-Path $releaseDir "GOLEM-$version-windows-installer.exe"
Copy-Item -LiteralPath $appExe -Destination $versionedApp -Force
Copy-Item -LiteralPath $installerExe -Destination $versionedInstaller -Force

Write-Host "Windows release artifacts:"
Write-Host "  $versionedApp"
Write-Host "  $versionedInstaller"
