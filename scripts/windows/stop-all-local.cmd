@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0SmartOpsAgent-关闭全部后台功能.ps1"
if errorlevel 1 echo Some services could not be stopped. Review the output above.
pause
