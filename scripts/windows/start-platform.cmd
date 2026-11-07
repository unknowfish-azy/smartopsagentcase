@echo off
REM SmartOpsAgent 全栈一键启动（双击即可）
REM 用法: start-platform.cmd [start^|stop^|status^|restart] [--skip-mock-ssh]
setlocal
set SCRIPT=%~dp0start-platform.ps1
set ACTION=%~1
set EXTRA=%~2

if /I "%ACTION%"=="stop" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Stop
    goto :eof
)
if /I "%ACTION%"=="status" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Status
    goto :eof
)
if /I "%ACTION%"=="restart" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Restart
    goto :eof
)

if /I "%EXTRA%"=="--skip-mock-ssh" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -SkipMockSsh
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
)
