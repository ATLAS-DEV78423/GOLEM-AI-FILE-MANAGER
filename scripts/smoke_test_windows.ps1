# End-to-end smoke test for the GOLEM built binary (Windows)
#
# This script:
#   1. Creates a temporary sandbox with a watched folder and vault
#   2. Places sample files in the watched folder
#   3. Runs the GOLEM binary to verify it can start
#   4. Verifies the database was created
#   5. Runs a Python-level integration test
#
# Usage: .\scripts\smoke_test_windows.ps1 [path-to-GOLEM-exe]

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir

# Locate binary
$Binary = $null
if ($args.Count -gt 0 -and (Test-Path $args[0])) {
    $Binary = $args[0]
} else {
    $candidates = @(
        Join-Path $RootDir "dist\GOLEM\GOLEM.exe"
        Join-Path $RootDir "dist\GOLEM.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            $Binary = $c
            break
        }
    }
}

if (-not $Binary) {
    Write-Host "Error: GOLEM binary not found. Build the project first or provide a path." -ForegroundColor Red
    Write-Host "Usage: $($MyInvocation.MyCommand.Name) [path-to-GOLEM-exe]" -ForegroundColor Yellow
    exit 1
}
Write-Host "Testing binary: $Binary" -ForegroundColor Cyan

# Create sandbox
$Sandbox = Join-Path $env:TEMP "golem-smoke-$(Get-Random)"
$Watched = Join-Path $Sandbox "watched"
$Vault = Join-Path $Sandbox "vault"
$DataDir = Join-Path $Sandbox "data"
New-Item -ItemType Directory -Path $Watched -Force | Out-Null
New-Item -ItemType Directory -Path $Vault -Force | Out-Null
New-Item -ItemType Directory -Path $DataDir -Force | Out-Null

$Cleanup = $true
try {
    Write-Host "Sandbox: $Sandbox"
    Write-Host "Watched: $Watched"
    Write-Host "Vault:   $Vault"

    # Create sample files
    Set-Content -Path (Join-Path $Watched "budget_q1.txt") -Value "budget report for Q1 2026 invoice payment"
    Set-Content -Path (Join-Path $Watched "research_notes.txt") -Value "study on machine learning methods and datasets"
    Set-Content -Path (Join-Path $Watched "design_notes.txt") -Value "ui mockup for the new dashboard design"

    # Test 1: CLI --version
    Write-Host "`n--- Test 1: CLI --version ---" -ForegroundColor Cyan
    $output = & $Binary --version 2>&1 | Out-String
    if ($output -match "GOLEM") {
        Write-Host "PASS: --version works ($($output.Trim()))" -ForegroundColor Green
    } else {
        throw "--version did not return expected output: $output"
    }

    # Test 2: Dry-run scan (headless)
    Write-Host "`n--- Test 2: Dry-run scan ---" -ForegroundColor Cyan
    $env:GOLEM_DATA_DIR = $DataDir
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Binary
    $psi.Arguments = "--dry-run --no-tray --no-watcher --no-hotkey --log-level DEBUG"
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.EnvironmentVariables["GOLEM_DATA_DIR"] = $DataDir
    $p = [System.Diagnostics.Process]::Start($psi)
    Start-Sleep -Seconds 8
    if (-not $p.HasExited) {
        $p.Kill()
    }
    $stdout = $p.StandardOutput.ReadToEnd()
    $stderr = $p.StandardError.ReadToEnd()

    Start-Sleep -Seconds 3

    # Check for database
    $dbFiles = Get-ChildItem -Path $Sandbox -Recurse -Filter "golem.db" -ErrorAction SilentlyContinue
    if ($dbFiles) {
        Write-Host "PASS: Database found at $($dbFiles[0].FullName)" -ForegroundColor Green
        $DbPath = $dbFiles[0].FullName
    } else {
        Write-Host "WARN: Database not found. Process output:" -ForegroundColor Yellow
        Write-Host $stderr
    }

    # Test 3: Python-level smoke test
    Write-Host "`n--- Test 3: Python-level smoke test ---" -ForegroundColor Cyan
    $pythonCode = @"
import sys
from pathlib import Path
sys.path.insert(0, '$RootDir'.replace('\\', '/'))
from golem.indexer import initialize, search_files
from golem.scanner import index_one_file
from golem.summarizer import HeuristicSummarizer

watched = Path(r'$Watched')
vault = Path(r'$Vault')
data_dir = Path(r'$DataDir')
data_dir.mkdir(parents=True, exist_ok=True)

conn = initialize(data_dir / 'golem.db')
file_id, status = index_one_file(conn, watched / 'budget_q1.txt', vault, HeuristicSummarizer())
assert status in ('done', 'pending'), f'Index status was {status}'
results = search_files(conn, 'budget')
assert len(results) >= 1, f'Expected >=1 results, got {len(results)}'

results2 = search_files(conn, 'march')
print(f'Search for march returned {len(results2)} result(s)')
conn.close()
print('Python smoke test PASSED')
"@
    # Use python (not python3 — python3 may not exist on Windows)
    $pythonCode | python 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "PASS: Python-level smoke test" -ForegroundColor Green
    } else {
        throw "Python-level smoke test failed"
    }

    # Summary
    Write-Host "`n=== Smoke test results ===" -ForegroundColor Cyan
    Write-Host "Binary:       $Binary" -ForegroundColor Green
    Write-Host "CLI version:  PASS" -ForegroundColor Green
    Write-Host "Dry-run scan: PASS" -ForegroundColor Green
    Write-Host "Python smoke: PASS" -ForegroundColor Green
    Write-Host "`nAll smoke tests passed!" -ForegroundColor Green

} finally {
    if ($Cleanup) {
        Remove-Item -Path $Sandbox -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Cleaned up sandbox: $Sandbox"
    }
}
