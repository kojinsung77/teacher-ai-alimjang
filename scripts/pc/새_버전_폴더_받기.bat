@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fetch_test_versions.ps1" -Dest "%~dp0."
