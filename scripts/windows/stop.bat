@echo off
setlocal EnableExtensions
chcp 65001 >nul

cd /d "%~dp0..\.."
title FastRead Stop

echo.
echo ========================================
echo   FastRead Stop
echo ========================================
echo.

where docker >nul 2>nul
if errorlevel 1 (
  echo [error] Docker was not found.
  pause
  exit /b 1
)

docker compose down
if errorlevel 1 (
  echo [error] Failed to stop services.
  pause
  exit /b 1
)

echo.
echo [done] FastRead services stopped.
pause
exit /b 0
