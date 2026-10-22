@echo off
cd /d "%~dp0"
python --version >nul 2>nul
if errorlevel 1 (
  py -3 scripts\test_copy_run.py %*
) else (
  python scripts\test_copy_run.py %*
)
if errorlevel 1 pause
