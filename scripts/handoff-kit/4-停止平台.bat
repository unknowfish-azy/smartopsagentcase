@echo off
chcp 936 >nul
setlocal
set "SCRIPT_DIR=%~dp0"
echo [SmartOpsAgent] Stopping services...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\stop.ps1" %*
endlocal
