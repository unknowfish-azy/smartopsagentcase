@echo off
chcp 936 >nul
setlocal
set "SCRIPT_DIR=%~dp0"
echo [SmartOpsAgent] Installing dependencies (run once)...
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\setup.ps1" %*
if errorlevel 1 (
  echo.
  echo [SmartOpsAgent] Setup failed. See messages above.
  pause
)
endlocal
