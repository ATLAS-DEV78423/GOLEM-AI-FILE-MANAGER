# Run deep test suite for GOLEM
# Usage: Open PowerShell in repo root and run: `./scripts/run_deep_tests.ps1`

$ErrorActionPreference = 'Stop'
Write-Host "Setting up virtualenv (venv)"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
Write-Host "Upgrading pip"
python -m pip install --upgrade pip
Write-Host "Installing dev requirements"
python -m pip install -r requirements-dev.txt || Write-Host "Failed to install requirements-dev.txt; install manually"

Write-Host "Running mypy"
python -m mypy golem

Write-Host "Running pytest"
python -m pytest -q

Write-Host "Running ruff (if installed)"
try {
    python -m ruff check .
} catch {
    Write-Host "ruff not available as python -m; try 'ruff' on PATH or install via pipx/pip"
}

Write-Host "Formatting check: black (if available)"
try {
    python -m black --version > $null
    python -m black . --check
} catch {
    Write-Host "black not available via python -m; try 'black' on PATH or install via pip"
}

Write-Host "Attempting to build sdist and wheel (if 'build' installed)"
try {
    python -m build --sdist --wheel --outdir dist
} catch {
    Write-Host "'build' module not available via python -m; install 'build' and retry"
}

Write-Host "Deep tests complete. Review output for failures."
Write-Host "If all green, package artifacts live in ./dist (if build succeeded)."

# Deactivate venv
deactivate
