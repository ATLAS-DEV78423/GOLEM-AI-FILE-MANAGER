$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = 'C:\Users\Stanley\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path $python)) {
  throw "Bundled Python runtime not found at $python"
}

& $python -m PyInstaller .\golem.spec --noconfirm --clean
& $python .\scripts\write_payload_manifest.py .\dist\GOLEM
& $python -m PyInstaller .\installer.spec --noconfirm --clean

Write-Host "Windows installer artifacts are in .\dist\GOLEM\ and .\dist\GOLEM-Setup.exe."
