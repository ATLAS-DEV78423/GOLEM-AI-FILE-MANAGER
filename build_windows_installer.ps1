$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

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

$venv = Join-Path $root '.venv-build'
$python = Join-Path $venv 'Scripts\python.exe'

if (-not (Test-Path $python)) {
  $systemPython = Find-Python
  if (-not $systemPython) {
    throw "Python 3.11+ is required to build GOLEM. Install from https://python.org (ensuring 'Add Python to PATH' is checked) and retry."
  }
  Write-Host "Creating build venv at $venv using $systemPython"
  & $systemPython -m venv $venv
  & $python -m pip install --upgrade pip
  & $python -m pip install -r requirements.txt
  if (Test-Path (Join-Path $root 'requirements-build.txt')) {
    & $python -m pip install -r requirements-build.txt
  }
}

& $python -m PyInstaller .\golem.spec --noconfirm --clean
& $python .\scripts\write_payload_manifest.py .\dist\GOLEM
& $python -m PyInstaller .\installer.spec --noconfirm --clean

Write-Host "Windows installer artifacts are in .\dist\GOLEM\ and .\dist\GOLEM-Setup.exe."
