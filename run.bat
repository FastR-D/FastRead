@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

cd /d "%~dp0"
title FastRead

set "MODE=start"
set "NO_OPEN=0"
set "BACKEND_PORT=8483"
set "FRONTEND_PORT=3015"
set "PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"

:READ_ARGS
if "%~1"=="" goto ARGS_DONE
if /i "%~1"=="--help" set "MODE=help"
if /i "%~1"=="-h" set "MODE=help"
if /i "%~1"=="--check" set "MODE=check"
if /i "%~1"=="--status" set "MODE=status"
if /i "%~1"=="--stop" set "MODE=stop"
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
  >> ".env" echo ONLINE_VERIFY_SEARCH_PROVIDER=brave
  >> ".env" echo ONLINE_VERIFY_SEARCH_FALLBACK_PROVIDERS=bing_academic,bing_cn,baidu
)

for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
  set "ENV_KEY=%%A"
  set "ENV_VALUE=%%B"
  for /f "tokens=1 delims=# " %%K in ("!ENV_KEY!") do set "ENV_KEY=%%K"
  for /f "tokens=1 delims=#" %%V in ("!ENV_VALUE!") do set "ENV_VALUE=%%V"
  if /i "!ENV_KEY!"=="APP_PORT" set "FRONTEND_PORT=!ENV_VALUE!"
  if /i "!ENV_KEY!"=="VITE_FRONTEND_PORT" set "FRONTEND_PORT=!ENV_VALUE!"
  if /i "!ENV_KEY!"=="BACKEND_PORT" set "BACKEND_PORT=!ENV_VALUE!"
  if /i "!ENV_KEY!"=="PIP_INDEX" set "PIP_INDEX=!ENV_VALUE!"
)

for /f "tokens=1 delims= " %%A in ("!BACKEND_PORT!") do set "BACKEND_PORT=%%A"
for /f "tokens=1 delims= " %%A in ("!FRONTEND_PORT!") do set "FRONTEND_PORT=%%A"

set "BACKEND_PY=%CD%\backend\.venv\Scripts\python.exe"
set "FRONTEND_DIR=%CD%\fastread-frontend"
set "APP_URL=http://127.0.0.1:%FRONTEND_PORT%/"
set "CHECK_URL=http://127.0.0.1:%BACKEND_PORT%/api/sys_check"
set "HEALTH_URL=http://127.0.0.1:%BACKEND_PORT%/api/sys_health"
set "FRONTEND_API_BASE=/api"
set "PNPM_CMD=corepack pnpm"

if /i "%MODE%"=="help" goto HELP
if /i "%MODE%"=="check" goto CHECK
if /i "%MODE%"=="status" goto STATUS
if /i "%MODE%"=="stop" goto STOP
goto START

:HEADER
echo.
echo ========================================
echo   FastRead Local Entry
echo ========================================
echo.
exit /b 0

:HELP
call :HEADER
echo Usage:
echo   run.bat             Start local backend and frontend
echo   run.bat --no-open   Start without opening browser
echo   run.bat --check     Check local requirements
echo   run.bat --status    Check local service status
echo   run.bat --stop      Stop local backend/frontend by port
echo.
echo Docker is not part of the default startup path.
exit /b 0

:CHECK
call :HEADER
echo [check] Python
where python >nul 2>nul
if errorlevel 1 (
  echo [fail] python was not found. Install Python 3.11+ and enable PATH.
  goto FAIL
) else (
  for /f "tokens=*" %%V in ('python --version 2^>nul') do echo [ok] %%V
)

echo.
echo [check] Node.js and pnpm
where node >nul 2>nul
if errorlevel 1 (
  echo [fail] node was not found. Install Node.js 20+.
  goto FAIL
) else (
  for /f "tokens=*" %%V in ('node --version 2^>nul') do echo [ok] node %%V
)
where corepack >nul 2>nul
if errorlevel 1 (
  echo [fail] corepack was not found. Install Node.js 20+ with Corepack.
  goto FAIL
)
call %PNPM_CMD% --version >nul 2>nul
if errorlevel 1 (
  echo [fail] corepack could not run pnpm.
  echo Run:
  echo   corepack enable
  echo   corepack prepare pnpm@9.15.0 --activate
  goto FAIL
)
echo [ok] pnpm is available through Corepack.

echo.
echo [check] Backend virtualenv
if not exist "%BACKEND_PY%" (
  echo [fail] backend virtualenv not found: %BACKEND_PY%
  echo Create it:
  echo   cd backend
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  goto FAIL
) else (
  echo [ok] backend\.venv exists.
)

echo.
echo [check] Frontend dependencies
if not exist "%FRONTEND_DIR%\node_modules" (
  echo [fail] frontend dependencies not found: %FRONTEND_DIR%\node_modules
  echo Install them:
  echo   cd fastread-frontend
  echo   corepack enable
  echo   %PNPM_CMD% install
  goto FAIL
) else (
  echo [ok] frontend node_modules exists.
)

echo.
echo [check] Ports %BACKEND_PORT% and %FRONTEND_PORT%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ports=@(%BACKEND_PORT%,%FRONTEND_PORT%); foreach($port in $ports){ $listeners=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue; if($listeners){ Write-Output \"[warn] Port $port is already in use. If FastRead is not running, use run.bat --stop or change .env.\" } else { Write-Output \"[ok] Port $port is free.\" } }"

echo.
echo [check] Required project files
if not exist "backend\main.py" (
  echo [fail] backend\main.py is missing.
  goto FAIL
)
if not exist "fastread-frontend\package.json" (
  echo [fail] fastread-frontend\package.json is missing.
  goto FAIL
)
echo [ok] Project files look complete.
echo.
echo [done] Local requirements check finished.
exit /b 0

:STATUS
call :HEADER
echo Frontend: %APP_URL%
echo Backend:  %HEALTH_URL%
echo.
echo [status] Local port owners
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ports=@(%BACKEND_PORT%,%FRONTEND_PORT%); foreach($port in $ports){ $items=Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue; if($items){ foreach($item in $items){ $proc=Get-Process -Id $item.OwningProcess -ErrorAction SilentlyContinue; Write-Host ('  port ' + $port + ' -> PID ' + $item.OwningProcess + ' ' + $proc.ProcessName) } } else { Write-Host ('  port ' + $port + ' -> not listening') } }"
echo.
echo [status] Backend health
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -Uri '%HEALTH_URL%' -UseBasicParsing -TimeoutSec 3; Write-Output $r.Content; exit 0 } catch { Write-Output '[error] backend health check failed'; exit 1 }"
echo.
echo [status] Frontend
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -Uri '%APP_URL%' -UseBasicParsing -TimeoutSec 3; Write-Output ('[ok] frontend returned HTTP ' + $r.StatusCode); exit 0 } catch { Write-Output '[error] frontend check failed'; exit 1 }"
exit /b 0

:STOP
call :HEADER
echo [stop] Stopping local processes on ports %BACKEND_PORT% and %FRONTEND_PORT%...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ports=@(%BACKEND_PORT%,%FRONTEND_PORT%); $owners=@(); foreach($port in $ports){ Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | ForEach-Object { $owners += $_.OwningProcess } }; $owners | Sort-Object -Unique | Where-Object { $_ -and $_ -ne $PID } | ForEach-Object { Write-Host ('[stop] PID ' + $_); Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
echo [done] Local FastRead processes stopped if they were running.
exit /b 0

:START
call :HEADER
echo Docker is not required.
echo Backend:  %HEALTH_URL%
echo Frontend: %APP_URL%
echo.

call :CHECK_START_REQUIREMENTS
if errorlevel 1 goto FAIL

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
start "FastRead Backend" powershell -NoExit -ExecutionPolicy Bypass -Command "$env:PYTHONUTF8='1'; Set-Location '%CD%\backend'; .\.venv\Scripts\python.exe main.py"

echo [wait] Backend health check...
for /l %%I in (1,1,60) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -Uri '%HEALTH_URL%' -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -eq 200){ exit 0 } } catch { }; exit 1" >nul 2>nul
  if not errorlevel 1 goto BACKEND_READY
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 1" >nul
)

echo [error] Backend did not become healthy.
goto FAIL

:BACKEND_READY
echo [ok] Backend is ready.
echo [start] Frontend window...
start "FastRead Frontend" powershell -NoExit -ExecutionPolicy Bypass -Command "$env:VITE_API_BASE_URL='%FRONTEND_API_BASE%'; $env:VITE_SCREENSHOT_BASE_URL='/static/screenshots'; $env:VITE_FRONTEND_PORT='%FRONTEND_PORT%'; $env:BACKEND_PORT='%BACKEND_PORT%'; $env:VITE_ENV_DIR='%FRONTEND_DIR%'; Set-Location '%FRONTEND_DIR%'; cmd /c call %PNPM_CMD% run dev -- --host 0.0.0.0 --port %FRONTEND_PORT%"

echo [wait] Frontend dev server...
for /l %%I in (1,1,60) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -Uri '%APP_URL%' -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -eq 200){ exit 0 } } catch { }; exit 1" >nul 2>nul
  if not errorlevel 1 goto READY
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 1" >nul
)

echo [error] Frontend did not become ready.
goto FAIL

:READY
echo.
echo [done] FastRead local dev is ready.
echo Open: %APP_URL%
echo.
if "%NO_OPEN%"=="0" start "" "%APP_URL%"
exit /b 0

:CHECK_START_REQUIREMENTS
if not exist "%BACKEND_PY%" (
  echo [error] backend virtualenv not found: %BACKEND_PY%
  echo Create it first:
  echo   cd backend
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules" (
  echo [error] frontend dependencies not found: %FRONTEND_DIR%\node_modules
  echo Install them first:
  echo   cd fastread-frontend
  echo   corepack enable
  echo   %PNPM_CMD% install
  exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
  echo [error] node was not found. Please install Node.js 20+.
  exit /b 1
)
where corepack >nul 2>nul
if errorlevel 1 (
  echo [error] corepack was not found. Install Node.js 20+ with Corepack.
  exit /b 1
)
call %PNPM_CMD% --version >nul 2>nul
if errorlevel 1 (
  echo [error] corepack could not run pnpm.
  echo Run:
  echo   corepack enable
  echo   corepack prepare pnpm@9.15.0 --activate
  exit /b 1
)
echo [ok] pnpm is available through Corepack.
exit /b 0

:FAIL
echo.
echo FastRead command did not complete.
echo Run "run.bat --help" for available commands.
echo.
exit /b 1
