@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
where pyinstaller >nul 2>nul
if errorlevel 1 (
  echo PyInstaller is not installed. Run python -m pip install -r requirements.txt first.
  exit /b 1
)
pyinstaller golem.spec
