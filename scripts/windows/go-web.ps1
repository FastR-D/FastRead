param([string]$Action = 'start', [switch]$NoOpen)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$runtimeDirectory = Join-Path $projectRoot '.runtime/go-web'
$statePath = Join-Path $runtimeDirectory 'processes.json'
New-Item -ItemType Directory -Force -Path $runtimeDirectory | Out-Null
if ($Action -in @('status', 'stop')) {
    if (!(Test-Path -LiteralPath $statePath)) { Write-Output 'FastRead is stopped.'; exit 0 }
    foreach ($entry in (Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json)) {
        $process = Get-Process -Id $entry.id -ErrorAction SilentlyContinue
        if ($process -and $process.StartTime.ToUniversalTime().ToString('O') -eq $entry.started) {
            if ($Action -eq 'stop') { & taskkill.exe /PID $process.Id /T /F | Out-Null; Write-Output "Stopped $($entry.name)" }
            else { Write-Output "$($entry.name): running ($($process.Id))" }
        } else { Write-Output "$($entry.name): stopped" }
    }
    if ($Action -eq 'stop') { Remove-Item -LiteralPath $statePath }
    exit 0
}
$go = (Get-Command go -ErrorAction Stop).Source
$pnpm = (Get-Command pnpm.cmd -ErrorAction Stop).Source
if ($Action -eq 'check') { & $go version; & $pnpm --version; Get-Command pdftotext,pdfinfo -ErrorAction Stop | Select-Object Name,Source; exit 0 }
if ($Action -ne 'start') { throw "Unknown action: $Action" }
if (Test-Path -LiteralPath $statePath) {
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    if ($state | Where-Object { Get-Process -Id $_.id -ErrorAction SilentlyContinue }) { throw 'FastRead is already running. Use run.bat --status or --stop.' }
}
Push-Location (Join-Path $projectRoot 'backend-go')
try { & $go build -o (Join-Path $runtimeDirectory 'fastread.exe') ./cmd/fastread; if ($LASTEXITCODE) { throw 'Go build failed.' } } finally { Pop-Location }
$env:FASTREAD_WEB_ROOT = Join-Path $projectRoot '.runtime/web-data'
$env:FASTREAD_COOKIE_SECURE = 'false'
$env:FASTREAD_PUBLIC_ORIGIN = 'http://127.0.0.1:3015'
$env:BACKEND_PORT = '8483'
$env:VITE_FRONTEND_PORT = '3015'
$children = @()
foreach ($service in @(@('api','serve --listen 127.0.0.1:8483'), @('worker','worker --concurrency 2'))) {
    $process = Start-Process -FilePath (Join-Path $runtimeDirectory 'fastread.exe') -ArgumentList $service[1] -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeDirectory "$($service[0]).log") -RedirectStandardError (Join-Path $runtimeDirectory "$($service[0]).error.log") -PassThru
    $children += @{ name=$service[0]; id=$process.Id; started=$process.StartTime.ToUniversalTime().ToString('O') }
}
$frontendRunner = Join-Path $runtimeDirectory 'frontend.cmd'
Set-Content -LiteralPath $frontendRunner -Value "@echo off`r`ncall `"$pnpm`" dev --host 127.0.0.1 --port 3015" -Encoding utf8
$process = Start-Process -FilePath $env:ComSpec -ArgumentList @('/d','/c',"`"$frontendRunner`"") -WorkingDirectory (Join-Path $projectRoot 'fastread-frontend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeDirectory 'frontend.log') -RedirectStandardError (Join-Path $runtimeDirectory 'frontend.error.log') -PassThru
$children += @{ name='frontend'; id=$process.Id; started=$process.StartTime.ToUniversalTime().ToString('O') }
$children | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
Write-Output 'FastRead: http://127.0.0.1:3015/ | logs: .runtime/go-web'
if (!$NoOpen) { Start-Process 'http://127.0.0.1:3015/' }
