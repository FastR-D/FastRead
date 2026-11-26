@echo off
call "%~dp0..\..\run.bat" --stop %*
exit /b %ERRORLEVEL%
