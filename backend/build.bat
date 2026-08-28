@echo off
setlocal

cd /d %~dp0..
set "STAGING_DIR=backend\.build-staging"
set "BUNDLE_DIR=fastread-frontend\src-tauri\bin\FastReadBackend"
set "PYTHON_EXE=python"
if defined FASTREAD_BUILD_PYTHON set "PYTHON_EXE=%FASTREAD_BUILD_PYTHON%"

"%PYTHON_EXE%" -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
  echo PyInstaller is unavailable in %PYTHON_EXE%. Install backend\requirements.txt first.
  goto :fail
)

echo Cleaning generated build directories...
if exist "backend\dist" rmdir /s /q "backend\dist"
if exist "backend\build" rmdir /s /q "backend\build"
if exist "fastread-frontend\src-tauri\bin" rmdir /s /q "fastread-frontend\src-tauri\bin"
if exist "%STAGING_DIR%" rmdir /s /q "%STAGING_DIR%"
mkdir "%STAGING_DIR%" || goto :fail
mkdir "fastread-frontend\src-tauri\bin" || goto :fail

if /I not "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
  echo Unsupported Windows architecture: %PROCESSOR_ARCHITECTURE%
  goto :fail
)
set "TARGET_TRIPLE=x86_64-pc-windows-msvc"
echo Detected target triple: %TARGET_TRIPLE%

echo Building the isolated backend bundle...
"%PYTHON_EXE%" -m PyInstaller ^
  -y ^
  --name FastReadBackend ^
  --paths backend ^
  --distpath fastread-frontend\src-tauri\bin ^
  --workpath backend\build ^
  --specpath "%STAGING_DIR%" ^
  --hidden-import uvicorn ^
  --hidden-import fastapi ^
  --hidden-import starlette ^
  --add-data "%cd%\backend\app\db\builtin_providers.json;." ^
  backend\main.py
if errorlevel 1 goto :fail

move /Y "%BUNDLE_DIR%\FastReadBackend.exe" "%BUNDLE_DIR%\FastReadBackend-%TARGET_TRIPLE%.exe" >nul
if errorlevel 1 goto :fail

echo Scanning staged and generated files for private-key or high-confidence token material...
pwsh -NoProfile -Command "$roots = @('backend/.build-staging','backend/build','backend/dist','fastread-frontend/src-tauri/bin') | Where-Object { Test-Path -LiteralPath $_ }; $textNames = @('.env','.env.example'); $textExtensions = @('.cfg','.ini','.json','.map','.md','.pem','.py','.spec','.toml','.ts','.txt','.yaml','.yml'); $pattern = '-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----|(?:sk|rk)-[A-Za-z0-9_-]{32,}|gh[pousr]_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9-]{20,}'; $bad = foreach ($file in Get-ChildItem -LiteralPath $roots -Recurse -File -ErrorAction SilentlyContinue) { if ($textNames -notcontains $file.Name -and $textExtensions -notcontains $file.Extension.ToLowerInvariant()) { continue }; $text = Get-Content -LiteralPath $file.FullName -Raw -ErrorAction SilentlyContinue; if ($null -ne $text -and $text -match $pattern) { $file.Name } }; if ($bad) { Write-Error ('Potential secret material in artifact file(s): ' + (($bad | Sort-Object -Unique) -join ', ')); exit 1 }"
if errorlevel 1 goto :fail

pwsh -NoProfile -Command "$bundle = 'fastread-frontend/src-tauri/bin/FastReadBackend'; if (Get-ChildItem -LiteralPath $bundle -Recurse -File -Filter '.env') { throw 'Packaged .env files are forbidden' }; if (-not (Get-ChildItem -LiteralPath $bundle -Recurse -File -Filter 'builtin_providers.json')) { throw 'builtin_providers.json is missing' }"
if errorlevel 1 goto :fail

echo PyInstaller bundle completed: %BUNDLE_DIR%
if exist "%STAGING_DIR%" rmdir /s /q "%STAGING_DIR%"
endlocal
exit /b 0

:fail
set "BUILD_EXIT=%errorlevel%"
if "%BUILD_EXIT%"=="0" set "BUILD_EXIT=1"
if exist "%STAGING_DIR%" rmdir /s /q "%STAGING_DIR%"
echo Backend bundle failed.
endlocal & exit /b %BUILD_EXIT%
