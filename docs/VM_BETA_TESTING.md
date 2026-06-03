GOLEM VM Beta Testing Guide

Purpose
-------
This document describes steps to validate GOLEM in a clean VM for beta testing.

Prerequisites (VM)
- Windows 10/11 or a recent Linux distro.
- Python 3.11+ installed (3.12 recommended).
- 4 GB RAM (8 GB recommended), 2 CPU cores, 10 GB disk free.

1) Create VM snapshot
- Create a snapshot before installing anything. Use this as a rollback.

2) Clone the repo inside the VM

```powershell
git clone <repo-url> golem
cd golem
```

3) Create and activate a virtualenv

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows PowerShell
# or
source .venv/bin/activate        # Linux/macOS
```

4) Install runtime requirements

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt   # optional: for tests and linters
```

5) Run automated checks

```powershell
# Type checks
python -m mypy golem
# Tests
python -m pytest -q
# Formatting (optional)
python -m black .
# Linting (optional)
python -m ruff check .
```

6) Build distributables (optional)

```powershell
python -m pip install build
python -m build --sdist --wheel --outdir dist
```

7) Run the app interactively
- Start from a fresh profile: `python main.py` or run via the installed wheel/executable.
- Exercise these flows:
  - Onboarding: open wizard, set watched folder and vault, test provider, accept terms.
  - Search popup: open via hotkey, type queries, open files, reveal in Explorer.
  - Background watching: drop a small text file into watched folder and confirm indexing.
  - Tray icon: check tray actions (minimize, restore, quit).

8) Visual & UX checks
- Look for consistent spacing, fonts, and button hover/focus behaviors.
- Verify animations are smooth; if VM is slow, toggle reduced-motion in `golem/ui_theme.py` via `MOTION.reduced_motion = True`.

9) Capture issues
- For regressions, create minimal reproducer and attach logs from `golem.log` if present.

Checklist (pass/fail)
- [ ] Mypy passes
- [ ] Pytest passes
- [ ] App launches and main flows work
- [ ] Onboarding completes
- [ ] Search returns results
- [ ] File watching triggers indexing
- [ ] Installer artifacts created (optional)

If you'd like, I can also draft a smoke-test automation harness that runs the UI flows with a headless tool and captures screenshots — say if you want reproducible visual regression tests.