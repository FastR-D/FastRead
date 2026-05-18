@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

cd /d "%~dp0..\.."
title ReelMind Docker Starter

set "APP_PORT=3015"
set "REBUILD=1"
set "NO_OPEN=0"

:READ_ARGS
if "%~1"=="" goto ARGS_DONE
if /i "%~1"=="--rebuild" set "REBUILD=1"
if /i "%~1"=="--quick" set "REBUILD=0"
if /i "%~1"=="--no-build" set "REBUILD=0"
if /i "%~1"=="--no-open" set "NO_OPEN=1"
if /i "%~1"=="--help" goto HELP
shift
goto READ_ARGS

:ARGS_DONE

if not exist ".env" (
  echo [init] .env not found. Creating safe Docker defaults...
  > ".env" echo # Runtime
  >> ".env" echo ENV=production
  >> ".env" echo APP_PORT=3015
  >> ".env" echo BACKEND_HOST=0.0.0.0
  >> ".env" echo BACKEND_PORT=8483
  >> ".env" echo.
  >> ".env" echo # Frontend
  >> ".env" echo VITE_API_BASE_URL=/api
  >> ".env" echo VITE_SCREENSHOT_BASE_URL=/static/screenshots
  >> ".env" echo VITE_FRONTEND_PORT=3015
  >> ".env" echo.
  >> ".env" echo # Backend paths
  >> ".env" echo STATIC=/static
  >> ".env" echo OUT_DIR=./static/screenshots
  >> ".env" echo NOTE_OUTPUT_DIR=note_results
  >> ".env" echo IMAGE_BASE_URL=/static/screenshots
  >> ".env" echo DATA_DIR=data
  >> ".env" echo PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
  >> ".env" echo.
  >> ".env" echo # FFmpeg is installed inside Docker images.
  >> ".env" echo FFMPEG_BIN_PATH=
  >> ".env" echo.
  >> ".env" echo # Transcriber
  >> ".env" echo TRANSCRIBER_TYPE=bcut
  >> ".env" echo WHISPER_MODEL_SIZE=tiny
  >> ".env" echo GROQ_TRANSCRIBER_MODEL=whisper-large-v3-turbo
  >> ".env" echo.
  >> ".env" echo # Online verification search
  >> ".env" echo ONLINE_VERIFY_SEARCH_PROVIDER=bing_academic
  >> ".env" echo ONLINE_VERIFY_SEARCH_FALLBACK_PROVIDERS=baidu_xueshu,baidu,bing_cn,brave
  >> ".env" echo BRAVE_SEARCH_API_KEY=your_brave_search_api_key
  >> ".env" echo BRAVE_SEARCH_COUNTRY=CN
  >> ".env" echo BRAVE_SEARCH_LANG=zh-hans
  >> ".env" echo BRAVE_SEARCH_UI_LANG=zh-CN
)

for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
  set "ENV_KEY=%%A"
  set "ENV_VALUE=%%B"
  for /f "tokens=* delims= " %%K in ("!ENV_KEY!") do set "ENV_KEY=%%K"
  if not "!ENV_KEY!"=="" if not "!ENV_KEY:~0,1!"=="#" (
    for /f "tokens=1 delims=#" %%V in ("!ENV_VALUE!") do set "ENV_VALUE=%%V"
    if /i "!ENV_KEY!"=="APP_PORT" set "APP_PORT=!ENV_VALUE!"
  )
)
for /f "tokens=1 delims= " %%A in ("!APP_PORT!") do set "APP_PORT=%%A"

set "APP_URL=http://127.0.0.1:%APP_PORT%/"
set "HEALTH_URL=http://127.0.0.1:%APP_PORT%/api/sys_health"

echo.
echo ========================================
echo   ReelMind Docker Starter
echo ========================================
echo.
echo Default mode rebuilds images for reliability.
echo Faster restart: scripts\windows\start.bat --quick
echo.

where docker >nul 2>nul
if errorlevel 1 (
  echo [error] Docker was not found.
  echo Install Docker Desktop first:
  echo   https://www.docker.com/products/docker-desktop/
  start "" "https://www.docker.com/products/docker-desktop/"
  goto FAIL
)

docker compose version >nul 2>nul
if errorlevel 1 (
  echo [error] docker compose is not available.
  echo Update Docker Desktop, then run this file again.
  goto FAIL
)

docker info >nul 2>nul
if errorlevel 1 (
  echo [wait] Docker Desktop is not running. Trying to start it...
  if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
    start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
  ) else if exist "%LocalAppData%\Docker\Docker Desktop.exe" (
    start "" "%LocalAppData%\Docker\Docker Desktop.exe"
  )

  for /l %%I in (1,1,90) do (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 2" >nul
    docker info >nul 2>nul
    if not errorlevel 1 goto DOCKER_READY
  )

  echo [error] Docker Desktop did not become ready.
  echo Open Docker Desktop manually, wait until it says running, then run this file again.
  goto FAIL
)

:DOCKER_READY
echo [ok] Docker is ready.

if "%REBUILD%"=="1" (
  echo [start] Building and starting services...
  echo This may take several minutes on first startup.
  docker compose up -d --build
) else (
  echo [start] Starting services without rebuild...
  docker compose up -d
)
if errorlevel 1 (
  echo [error] Docker Compose startup failed.
  echo Common causes: port %APP_PORT% is occupied, Docker Desktop is still starting, or image download failed.
  docker compose ps
  goto FAIL
)

for /l %%I in (1,1,90) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri '%HEALTH_URL%' -UseBasicParsing -TimeoutSec 3; if ($r.StatusCode -eq 200) { exit 0 } } catch { }; exit 1" >nul 2>nul
  if not errorlevel 1 goto READY
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 2" >nul
)

echo [error] Docker services did not become healthy.
docker compose ps
echo.
echo Last backend logs:
docker compose logs --tail=80 backend
goto FAIL

:READY
echo.
echo [done] Docker services are ready: %APP_URL%
echo.
echo Useful commands:
echo   scripts\windows\status.bat   Check service status
echo   scripts\windows\stop.bat     Stop services
echo   scripts\windows\start.bat --quick   Fast restart
echo.
if "%NO_OPEN%"=="0" start "" "%APP_URL%"
exit /b 0

:HELP
echo ReelMind Docker Starter
echo.
echo Usage:
echo   scripts\windows\start.bat              Build and start services
echo   scripts\windows\start.bat --quick      Start without rebuilding images
echo   scripts\windows\start.bat --no-open    Do not open browser after startup
echo   scripts\windows\start.bat --rebuild    Explicitly rebuild images
exit /b 0

:FAIL
echo Startup did not complete.
pause
exit /b 1
