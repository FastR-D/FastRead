@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

cd /d "%~dp0"
title BiliNote Demo Starter

set "APP_PORT=3015"
set "HEALTH_PATH=/api/sys_health"
set "REBUILD=0"
set "NO_PAUSE=0"
set "NO_OPEN=0"

:READ_ARGS
if "%~1"=="" goto ARGS_DONE
if /i "%~1"=="--rebuild" set "REBUILD=1"
if /i "%~1"=="--no-pause" set "NO_PAUSE=1"
if /i "%~1"=="--no-open" set "NO_OPEN=1"
shift
goto READ_ARGS

:ARGS_DONE

if not exist ".env" (
  echo [init] .env not found. Creating default demo config...
  > ".env" echo ENV=production
  >> ".env" echo APP_PORT=3015
  >> ".env" echo BACKEND_HOST=0.0.0.0
  >> ".env" echo BACKEND_PORT=8483
  >> ".env" echo VITE_API_BASE_URL=/api
  >> ".env" echo VITE_SCREENSHOT_BASE_URL=/static/screenshots
  >> ".env" echo VITE_FRONTEND_PORT=3015
  >> ".env" echo STATIC=/static
  >> ".env" echo OUT_DIR=./static/screenshots
  >> ".env" echo NOTE_OUTPUT_DIR=note_results
  >> ".env" echo IMAGE_BASE_URL=/static/screenshots
  >> ".env" echo DATA_DIR=data
  >> ".env" echo FFMPEG_BIN_PATH=
  >> ".env" echo TRANSCRIBER_TYPE=bcut
  >> ".env" echo WHISPER_MODEL_SIZE=tiny
  >> ".env" echo GROQ_TRANSCRIBER_MODEL=whisper-large-v3-turbo
)

for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
  set "ENV_KEY=%%A"
  set "ENV_VALUE=%%B"
  if /i "!ENV_KEY!"=="APP_PORT" set "APP_PORT=!ENV_VALUE!"
)

for /f "tokens=1 delims=# " %%A in ("!APP_PORT!") do set "APP_PORT=%%A"
set "DEMO_URL=http://127.0.0.1:%APP_PORT%/"
set "HEALTH_URL=http://127.0.0.1:%APP_PORT%%HEALTH_PATH%"

echo.
echo ========================================
echo   BiliNote Demo Starter
echo ========================================
echo.
echo Project dir: %CD%
echo Demo URL: %DEMO_URL%
echo.

where docker >nul 2>nul
if errorlevel 1 (
  echo [error] Docker was not found.
  echo Please install and start Docker Desktop, then double-click this file again.
  goto FAIL
)

docker compose version >nul 2>nul
if errorlevel 1 (
  echo [error] "docker compose" is not available.
  echo Please upgrade Docker Desktop and try again.
  goto FAIL
)

docker info >nul 2>nul
if errorlevel 1 (
  echo [wait] Docker Desktop is not ready. Trying to open it...
  if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
    start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
  ) else if exist "%LocalAppData%\Docker\Docker Desktop.exe" (
    start "" "%LocalAppData%\Docker\Docker Desktop.exe"
  )

  for /l %%I in (1,1,90) do (
    docker info >nul 2>nul
    if not errorlevel 1 goto DOCKER_READY
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 2" >nul
  )

  echo [error] Docker Engine is not ready.
  echo Please make sure Docker Desktop is fully started and this user can use Docker.
  goto FAIL
)

:DOCKER_READY
if "%REBUILD%"=="1" (
  echo [start] Rebuilding and starting demo services. This may take several minutes...
  docker compose up -d --build
) else (
  echo [start] Starting demo services...
  docker compose up -d
)
if errorlevel 1 (
  echo.
  echo [error] Docker Compose failed to start.
  echo Please send the error text above to the developer.
  goto FAIL
)

echo [start] Refreshing reverse proxy...
docker compose restart nginx >nul
if errorlevel 1 (
  echo.
  echo [error] Nginx proxy failed to restart.
  echo Please send the error text above to the developer.
  goto FAIL
)

echo.
echo [wait] Waiting for service health check...
for /l %%I in (1,1,90) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri '%HEALTH_URL%' -UseBasicParsing -TimeoutSec 3; if ($r.StatusCode -eq 200) { exit 0 } } catch { }; exit 1" >nul 2>nul
  if not errorlevel 1 goto READY
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 2" >nul
)

echo.
echo [error] Services started, but health check did not pass.
echo Health URL: %HEALTH_URL%
echo.
docker compose ps
echo.
echo Recent logs:
docker compose logs --tail=80
goto FAIL

:READY
echo.
echo [done] Demo is ready.
if "%NO_OPEN%"=="0" (
  echo Opening browser: %DEMO_URL%
) else (
  echo Browser opening skipped. Demo URL: %DEMO_URL%
)
echo.
if "%NO_OPEN%"=="0" start "" "%DEMO_URL%"
echo You can close this window. Services will keep running.
echo To stop services, run this command in this folder: docker compose down
echo.
if "%NO_PAUSE%"=="0" pause
exit /b 0

:FAIL
echo.
echo Startup did not complete.
echo.
if "%NO_PAUSE%"=="0" pause
exit /b 1
