@echo off
setlocal
set "ACTION=start"
set "OPEN="
if /i "%~1"=="--status" set "ACTION=status"
if /i "%~1"=="--stop" set "ACTION=stop"
if /i "%~1"=="--check" set "ACTION=check"
if /i "%~1"=="--no-open" set "OPEN=-NoOpen"
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\go-web.ps1" -Action %ACTION% %OPEN%
exit /b %ERRORLEVEL%
