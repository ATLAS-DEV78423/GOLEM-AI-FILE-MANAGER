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

  return '2.1.0'
}

function Find-Python {
  $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $cmd = Get-Command py.exe -ErrorAction SilentlyContinue
  if ($cmd) {
    $probe = & $cmd.Source -3.11 -c "import sys; print(sys.executable)" 2>$null
    if ($probe -and (Test-Path $probe)) { return $probe }
  }
  return $null
}

Write-Host "=== GOLEM Windows Build ===" -ForegroundColor Cyan

$venv = Join-Path $root '.venv-build'
$python = Join-Path $venv 'Scripts\python.exe'

$systemPython = Find-Python
if (-not $systemPython) {
  throw "Python 3.11+ is required to build GOLEM. Install from https://python.org and retry."
}

if (-not (Test-Path $python)) {
  Write-Host "Creating build venv at $venv using $systemPython" -ForegroundColor Yellow
  & $systemPython -m venv $venv
} else {
  Write-Host "Build venv exists at $venv; updating dependencies..." -ForegroundColor Yellow
}

& $python -m pip install --upgrade pip
& $python -m pip install -r requirements-build.txt
& $python -m pip install -e .
& $python -m pip install proxy_tools  # ensure pywebview dependency is present

Write-Host "Step 1/4: Building GOLEM application bundle..." -ForegroundColor Cyan
& $python -m PyInstaller .\golem.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build for GOLEM failed." }

Write-Host "Step 2/4: Generating payload manifest..." -ForegroundColor Cyan
# Set PYTHONPATH so write_payload_manifest can import golem.constants
$env:PYTHONPATH = (Get-Location).Path
& $python .\scripts\write_payload_manifest.py .\dist\GOLEM

Write-Host "Step 3/4: Building installer..." -ForegroundColor Cyan
& $python -m PyInstaller .\installer.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build for installer failed." }

# Rename installer to a clean name
if (Test-Path ".\dist\GOLEM-Setup.exe") {
  $version = Get-GolemVersion
  if ($version -match '^v(.+)$') {
    $version = $Matches[1]
  }
  $finalName = "GOLEM-Setup-$version.exe"
  Move-Item ".\dist\GOLEM-Setup.exe" ".\dist\$finalName" -Force
  Write-Host "Step 4/4: Renamed installer to $finalName" -ForegroundColor Cyan
}

Write-Host "`n=== Build complete ===" -ForegroundColor Green
Write-Host "Application bundle: .\dist\GOLEM\"
Write-Host "Installer: .\dist\$finalName"
