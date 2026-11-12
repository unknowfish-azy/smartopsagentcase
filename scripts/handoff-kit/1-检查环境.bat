@echo off
chcp 936 >nul
setlocal
set "SCRIPT_DIR=%~dp0"
echo [SmartOpsAgent] Checking environment...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\check-env.ps1" %*
endlocal
