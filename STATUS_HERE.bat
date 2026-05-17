@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

cd /d "%~dp0"
title ReelMind Status

set "APP_PORT=3015"
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    set "ENV_KEY=%%A"
    set "ENV_VALUE=%%B"
    for /f "tokens=* delims= " %%K in ("!ENV_KEY!") do set "ENV_KEY=%%K"
    if not "!ENV_KEY!"=="" if not "!ENV_KEY:~0,1!"=="#" (
      for /f "tokens=1 delims=#" %%V in ("!ENV_VALUE!") do set "ENV_VALUE=%%V"
      if /i "!ENV_KEY!"=="APP_PORT" set "APP_PORT=!ENV_VALUE!"
    )
  )
)
for /f "tokens=1 delims= " %%A in ("!APP_PORT!") do set "APP_PORT=%%A"

echo.
echo ========================================
echo   ReelMind Status
echo ========================================
echo.

where docker >nul 2>nul
if errorlevel 1 (
  echo [error] Docker was not found.
  pause
  exit /b 1
)

docker compose ps
echo.
echo Health check:
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:%APP_PORT%/api/sys_health' -UseBasicParsing -TimeoutSec 3; Write-Output $r.Content; exit 0 } catch { Write-Output '[error] health check failed'; exit 1 }"
echo.
echo App URL:
echo   http://127.0.0.1:%APP_PORT%/
echo.
pause
exit /b 0
