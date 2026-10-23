@echo off
set "S=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\CoolBriefing_TestFolders.bat"
> "%S%" echo @echo off
>> "%S%" echo start "" /min powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0fetch_test_versions.ps1" -Dest "%~dp0." -Quiet
echo.
echo [OK] Auto-check is ON. New test versions will appear as folders when Windows starts.
echo      Folder: %~dp0
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fetch_test_versions.ps1" -Dest "%~dp0."
