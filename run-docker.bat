@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

cd /d "%~dp0"
title ReelMind Docker Starter

set "APP_PORT=3015"
set "REBUILD=0"
set "NO_OPEN=0"

:READ_ARGS
if "%~1"=="" goto ARGS_DONE
if /i "%~1"=="--rebuild" set "REBUILD=1"
if /i "%~1"=="--no-open" set "NO_OPEN=1"
shift
goto READ_ARGS

:ARGS_DONE

for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
  set "ENV_KEY=%%A"
  set "ENV_VALUE=%%B"
  for /f "tokens=1 delims=# " %%K in ("!ENV_KEY!") do set "ENV_KEY=%%K"
  for /f "tokens=1 delims=#" %%V in ("!ENV_VALUE!") do set "ENV_VALUE=%%V"
  if /i "!ENV_KEY!"=="APP_PORT" set "APP_PORT=!ENV_VALUE!"
)
for /f "tokens=1 delims= " %%A in ("!APP_PORT!") do set "APP_PORT=%%A"

set "APP_URL=http://127.0.0.1:%APP_PORT%/"
set "HEALTH_URL=http://127.0.0.1:%APP_PORT%/api/sys_health"

echo.
echo ========================================
echo   ReelMind Docker Starter
echo ========================================
echo.
echo This is the optional Docker launcher.
echo Local launcher: run.bat
echo.

where docker >nul 2>nul
if errorlevel 1 (
  echo [error] Docker was not found.
  goto FAIL
)

docker compose version >nul 2>nul
if errorlevel 1 (
  echo [error] docker compose is not available.
  goto FAIL
)

if "%REBUILD%"=="1" (
  docker compose up -d --build
) else (
  docker compose up -d
)
if errorlevel 1 goto FAIL

for /l %%I in (1,1,90) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri '%HEALTH_URL%' -UseBasicParsing -TimeoutSec 3; if ($r.StatusCode -eq 200) { exit 0 } } catch { }; exit 1" >nul 2>nul
  if not errorlevel 1 goto READY
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 2" >nul
)

echo [error] Docker services did not become healthy.
docker compose ps
goto FAIL

:READY
echo [done] Docker services are ready: %APP_URL%
if "%NO_OPEN%"=="0" start "" "%APP_URL%"
exit /b 0

:FAIL
echo Startup did not complete.
pause
exit /b 1
