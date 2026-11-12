@echo off
chcp 936 >nul
setlocal
set "SCRIPT_DIR=%~dp0"
echo [SmartOpsAgent] Starting all services...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\start.ps1" %*
if errorlevel 1 (
  echo.
  echo [SmartOpsAgent] Some services failed. Check .runtime\logs\ for details.
  pause
)
endlocal
