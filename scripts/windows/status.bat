@echo off
call "%~dp0..\..\run.bat" --status %*
exit /b %ERRORLEVEL%
