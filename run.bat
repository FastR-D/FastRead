@echo off
setlocal EnableExtensions
set "ACTION=start"
set "OPTIONS="
:ARGS
if "%~1"=="" goto RUN
if /i "%~1"=="--status" (set "ACTION=status") else if /i "%~1"=="--stop" (set "ACTION=stop") else if /i "%~1"=="--restart" (set "ACTION=restart") else if /i "%~1"=="--check" (set "ACTION=check") else if /i "%~1"=="--init-admin" (set "ACTION=init-admin") else if /i "%~1"=="--no-open" (set "OPTIONS=%OPTIONS% -NoOpen") else if /i "%~1"=="--no-build" (set "OPTIONS=%OPTIONS% -NoBuild") else if /i "%~1"=="--quick" (set "OPTIONS=%OPTIONS% -NoBuild") else (echo Unknown option: %~1 & exit /b 2)
shift
goto ARGS
:RUN
where pwsh >nul 2>nul
if errorlevel 1 (echo PowerShell 7 is required. Install pwsh, then retry. & exit /b 1)
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\go-web.ps1" -Action %ACTION% %OPTIONS%
exit /b %ERRORLEVEL%
