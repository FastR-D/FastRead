@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

cd /d "%~dp0"
title ReelMind Local Starter

set "BACKEND_PORT=8483"
set "FRONTEND_PORT=3015"
set "PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"
set "NO_OPEN=0"

:READ_ARGS
if "%~1"=="" goto ARGS_DONE
if /i "%~1"=="--no-open" set "NO_OPEN=1"
shift
goto READ_ARGS

:ARGS_DONE

if not exist ".env" (
  echo [init] .env not found. Creating local default config...
  > ".env" echo ENV=development
  >> ".env" echo APP_PORT=3015
  >> ".env" echo BACKEND_HOST=127.0.0.1
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
  >> ".env" echo ONLINE_VERIFY_SEARCH_PROVIDER=bing_academic
  >> ".env" echo ONLINE_VERIFY_SEARCH_FALLBACK_PROVIDERS=baidu_xueshu,baidu,bing_cn,brave
)

for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
  set "ENV_KEY=%%A"
  set "ENV_VALUE=%%B"
  for /f "tokens=1 delims=# " %%K in ("!ENV_KEY!") do set "ENV_KEY=%%K"
  for /f "tokens=1 delims=#" %%V in ("!ENV_VALUE!") do set "ENV_VALUE=%%V"
  if /i "!ENV_KEY!"=="BACKEND_PORT" set "BACKEND_PORT=!ENV_VALUE!"
  if /i "!ENV_KEY!"=="VITE_FRONTEND_PORT" set "FRONTEND_PORT=!ENV_VALUE!"
  if /i "!ENV_KEY!"=="PIP_INDEX" set "PIP_INDEX=!ENV_VALUE!"
)

for /f "tokens=1 delims= " %%A in ("!BACKEND_PORT!") do set "BACKEND_PORT=%%A"
for /f "tokens=1 delims= " %%A in ("!FRONTEND_PORT!") do set "FRONTEND_PORT=%%A"

set "BACKEND_PY=%CD%\backend\.venv\Scripts\python.exe"
set "FRONTEND_DIR=%CD%\reel-mind-frontend"
set "APP_URL=http://127.0.0.1:%FRONTEND_PORT%/"
set "HEALTH_URL=http://127.0.0.1:%BACKEND_PORT%/api/sys_health"
set "FRONTEND_API_BASE=/api"

echo.
echo ========================================
echo   ReelMind Local Starter
echo ========================================
echo.
echo Docker is not required.
echo Backend:  %HEALTH_URL%
echo Frontend: %APP_URL%
echo.

if not exist "%BACKEND_PY%" (
  echo [error] backend virtualenv not found: %BACKEND_PY%
  echo Create it first:
  echo   cd backend
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  goto FAIL
)

if not exist "%FRONTEND_DIR%\node_modules" (
  echo [error] frontend dependencies not found: %FRONTEND_DIR%\node_modules
  echo Install them first:
  echo   cd reel-mind-frontend
  echo   npm install
  goto FAIL
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [error] npm was not found. Please install Node.js 20+.
  goto FAIL
)

echo [check] Backend runtime dependencies...
"%BACKEND_PY%" -c "import uvicorn, fastapi, dotenv, sqlalchemy, pydantic, httpx, bs4, openai, gmssl, kombu, PIL, blinker" >nul 2>nul
if errorlevel 1 (
  echo [init] Installing minimal backend runtime dependencies...
  "%BACKEND_PY%" -m pip install -i "%PIP_INDEX%" --timeout 180 fastapi==0.115.12 uvicorn==0.34.0 httptools==0.6.4 watchfiles==1.0.4 python-dotenv==1.1.0 SQLAlchemy==2.0.41 pydantic==2.11.2 httpx==0.28.1 beautifulsoup4==4.13.4 openai==1.70.0 python-multipart==0.0.20 requests==2.32.3 yt-dlp==2025.1.26 ffmpeg-python==0.2.0 imageio-ffmpeg==0.6.0 gmssl==3.2.2 kombu==5.5.2 pillow==11.0.0 blinker==1.9.0
  if errorlevel 1 (
    echo [error] Failed to install backend dependencies.
    goto FAIL
  )
)

echo [start] Backend window...
start "ReelMind Backend" powershell -NoExit -ExecutionPolicy Bypass -Command "$env:PYTHONUTF8='1'; Set-Location '%CD%\backend'; .\.venv\Scripts\python.exe main.py"

echo [wait] Backend health check...
for /l %%I in (1,1,60) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri '%HEALTH_URL%' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } } catch { }; exit 1" >nul 2>nul
  if not errorlevel 1 goto BACKEND_READY
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 1" >nul
)

echo [error] Backend did not become healthy.
goto FAIL

:BACKEND_READY
echo [ok] Backend is ready.
echo [start] Frontend window...
start "ReelMind Frontend" powershell -NoExit -ExecutionPolicy Bypass -Command "$env:VITE_API_BASE_URL='%FRONTEND_API_BASE%'; $env:VITE_SCREENSHOT_BASE_URL='/static/screenshots'; $env:VITE_FRONTEND_PORT='%FRONTEND_PORT%'; $env:BACKEND_PORT='%BACKEND_PORT%'; $env:VITE_ENV_DIR='%FRONTEND_DIR%'; Set-Location '%FRONTEND_DIR%'; npm run dev -- --host 0.0.0.0 --port %FRONTEND_PORT%"

echo [wait] Frontend dev server...
for /l %%I in (1,1,60) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri '%APP_URL%' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } } catch { }; exit 1" >nul 2>nul
  if not errorlevel 1 goto READY
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 1" >nul
)

echo [error] Frontend did not become ready.
goto FAIL

:READY
echo.
echo [done] ReelMind local dev is ready.
echo Open: %APP_URL%
echo.
if "%NO_OPEN%"=="0" start "" "%APP_URL%"
exit /b 0

:FAIL
echo.
echo Startup did not complete.
echo.
pause
exit /b 1
