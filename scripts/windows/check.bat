@echo off
call "%~dp0..\..\run.bat" --check %*
exit /b %ERRORLEVEL%
