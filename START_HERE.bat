@echo off
setlocal EnableExtensions
chcp 65001 >nul

cd /d "%~dp0"
title ReelMind One Click Start

echo.
echo ========================================
echo   ReelMind One Click Start
echo ========================================
echo.
echo This file starts the full Docker demo.
echo First startup can take several minutes.
echo If startup fails, run CHECK_REQUIREMENTS.bat.
echo.

call "%~dp0run-docker.bat" %*
exit /b %ERRORLEVEL%
