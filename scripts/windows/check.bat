@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

cd /d "%~dp0..\.."
title FastRead Requirements Check

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
echo   FastRead Requirements Check
echo ========================================
echo.

echo [check] Windows version
ver
echo.

echo [check] Docker command
where docker >nul 2>nul
if errorlevel 1 (
  echo [fail] Docker was not found.
  echo Install Docker Desktop:
  echo   https://www.docker.com/products/docker-desktop/
  start "" "https://www.docker.com/products/docker-desktop/"
  goto SUMMARY_FAIL
) else (
  for /f "tokens=*" %%V in ('docker --version 2^>nul') do echo [ok] %%V
)

echo.
echo [check] Docker Compose
docker compose version >nul 2>nul
if errorlevel 1 (
  echo [fail] docker compose is not available. Update Docker Desktop.
  goto SUMMARY_FAIL
) else (
  for /f "tokens=*" %%V in ('docker compose version 2^>nul') do echo [ok] %%V
)

echo.
echo [check] Docker Desktop engine
docker info >nul 2>nul
if errorlevel 1 (
  echo [fail] Docker Desktop is installed but not running.
  echo Open Docker Desktop, wait until it finishes starting, then run scripts\windows\start.bat.
  goto SUMMARY_FAIL
) else (
  echo [ok] Docker engine is running.
)

echo.
echo [check] App port %APP_PORT%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$port=%APP_PORT%; $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue; if ($listeners) { Write-Output \"[warn] Port $port is already in use. If FastRead is not already running, edit .env and change APP_PORT.\"; exit 2 } else { Write-Output \"[ok] Port $port is free.\" }"
echo.

echo [check] Free disk space
powershell -NoProfile -ExecutionPolicy Bypass -Command "$drive=(Get-Location).Drive.Name; $free=(Get-PSDrive -Name $drive).Free; $gb=[math]::Round($free/1GB,1); if ($free -lt 8GB) { Write-Output \"[warn] Only $gb GB free on drive $drive. First Docker build may fail.\"; exit 2 } else { Write-Output \"[ok] $gb GB free on drive $drive.\" }"
echo.

echo [check] Required project files
if not exist "docker-compose.yml" (
  echo [fail] docker-compose.yml is missing.
  goto SUMMARY_FAIL
)
if not exist "backend\Dockerfile" (
  echo [fail] backend\Dockerfile is missing.
  goto SUMMARY_FAIL
)
if not exist "fastread-frontend\Dockerfile" (
  echo [fail] fastread-frontend\Dockerfile is missing.
  goto SUMMARY_FAIL
)
echo [ok] Project files look complete.

echo.
echo [done] Basic requirements look good.
echo Next step: double click scripts\windows\start.bat
pause
exit /b 0

:SUMMARY_FAIL
echo.
echo Requirements check failed.
echo Fix the item above, then run scripts\windows\check.bat again.
pause
exit /b 1
