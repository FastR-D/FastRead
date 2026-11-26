param(
    [ValidateSet('start','stop','restart','status','check','init-admin')][string]$Action = 'start',
    [switch]$NoOpen,
    [switch]$NoBuild
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$envFile = if ($env:FASTREAD_ENV_FILE) { $env:FASTREAD_ENV_FILE } else { Join-Path $projectRoot '.env' }
if (Test-Path -LiteralPath $envFile) {
    foreach ($line in Get-Content -LiteralPath $envFile) {
        if ($line -match '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            $key = $Matches[1]; $value = $Matches[2].Trim()
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) { $value = $value.Substring(1, $value.Length - 2) }
            [Environment]::SetEnvironmentVariable($key, $value, 'Process')
        }
    }
}
$runtimeDirectory = if ($env:FASTREAD_RUNTIME_DIR) { $env:FASTREAD_RUNTIME_DIR } else { Join-Path $projectRoot '.runtime/go-web' }
New-Item -ItemType Directory -Force -Path $runtimeDirectory | Out-Null
$statePath = Join-Path $runtimeDirectory 'processes.json'
$binary = Join-Path $runtimeDirectory 'fastread.exe'
$port = if ($env:FASTREAD_PORT) { [int]$env:FASTREAD_PORT } else { 3015 }
if ($port -lt 1 -or $port -gt 65535) { throw 'Invalid FASTREAD_PORT' }
$listenHost = if ($env:FASTREAD_HOST) { $env:FASTREAD_HOST } else { '127.0.0.1' }
if (!$env:FASTREAD_WEB_ROOT) { $env:FASTREAD_WEB_ROOT = Join-Path $projectRoot '.runtime/web-data' }
if (!$env:FASTREAD_COOKIE_SECURE) { $env:FASTREAD_COOKIE_SECURE = 'false' }
if (!$env:FASTREAD_PUBLIC_ORIGIN) { $env:FASTREAD_PUBLIC_ORIGIN = "http://127.0.0.1:$port" }
$url = $env:FASTREAD_PUBLIC_ORIGIN.TrimEnd('/')
$lock = [IO.File]::Open((Join-Path $runtimeDirectory 'launcher.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
function Get-OwnedProcess($entry) {
    $process = Get-Process -Id $entry.id -ErrorAction SilentlyContinue
    if ($process -and $process.StartTime.ToUniversalTime().ToString('O') -eq $entry.started -and $process.Path -eq $binary) { return $process }
}
function Stop-Services {
    if (!(Test-Path -LiteralPath $statePath)) { return }
    foreach ($entry in @(Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json)) {
        $process = Get-OwnedProcess $entry
        if ($process) { & taskkill.exe /PID $process.Id /T /F | Out-Null; if ($LASTEXITCODE) { throw "Could not stop $($entry.name)" }; Write-Output "Stopped $($entry.name)" }
    }
    Remove-Item -LiteralPath $statePath
}
try {
    if ($Action -eq 'stop') { Stop-Services; exit 0 }
    if ($Action -eq 'status') {
        $running = 0
        if (Test-Path -LiteralPath $statePath) {
            foreach ($entry in @(Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json)) {
                if (Get-OwnedProcess $entry) { Write-Output "$($entry.name): running"; $running++ } else { Write-Output "$($entry.name): stopped" }
            }
        } else { Write-Output 'FastRead is stopped.' }
        if ($running -ne 2) { exit 1 }
        Invoke-RestMethod "$url/api/health" -TimeoutSec 3 | ConvertTo-Json
        Write-Output "$url/"; exit 0
    }
    $go = (Get-Command go -ErrorAction Stop).Source
    $pnpm = (Get-Command pnpm.cmd -ErrorAction Stop).Source
    Get-Command node,pdftotext,pdfinfo -ErrorAction Stop | Out-Null
    if ($Action -eq 'check') { & $go version; & $pnpm --version; Write-Output 'Dependencies ready'; exit 0 }
    if ($Action -eq 'restart') { Stop-Services }
    if (Test-Path -LiteralPath $statePath) {
        if (@(Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json) | Where-Object { Get-OwnedProcess $_ }) { Write-Output 'FastRead is already running. Use run.bat --restart or --status.'; exit 0 }
    }
    if (!$NoBuild -or !(Test-Path -LiteralPath $binary)) {
        Push-Location (Join-Path $projectRoot 'backend-go')
        try { & $go build -trimpath -o $binary ./cmd/fastread; if ($LASTEXITCODE) { throw 'Go build failed.' } } finally { Pop-Location }
    }
    if ($Action -eq 'init-admin') {
        $email = if ($env:FASTREAD_ADMIN_EMAIL) { $env:FASTREAD_ADMIN_EMAIL } else { 'admin@fastread.local' }
        try {
            if (!$env:FASTREAD_INITIAL_PASSWORD) { $env:FASTREAD_INITIAL_PASSWORD = Read-Host 'Administrator password (at least 12 characters)' -MaskInput }
            & $binary user-create --email $email --name '管理员' --admin
            if ($LASTEXITCODE) { throw 'Administrator creation failed.' }
        } finally { Remove-Item Env:FASTREAD_INITIAL_PASSWORD -ErrorAction SilentlyContinue }
        exit 0
    }
    $frontend = Join-Path $projectRoot 'fastread-frontend'
    if (!$NoBuild -or !(Test-Path (Join-Path $frontend 'dist/index.html'))) {
        Push-Location $frontend
        try {
            if (!(Test-Path node_modules)) { & $pnpm install --frozen-lockfile; if ($LASTEXITCODE) { throw 'Dependency installation failed.' } }
            & $pnpm build; if ($LASTEXITCODE) { throw 'Frontend build failed.' }
        } finally { Pop-Location }
    }
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw "Port $port is occupied. No process was stopped." }
    $children = @()
    try {
        $concurrency = if ($env:FASTREAD_WORKER_CONCURRENCY) { $env:FASTREAD_WORKER_CONCURRENCY } else { '2' }
        foreach ($service in @(@('server', "serve --listen ${listenHost}:$port --frontend `"$(Join-Path $frontend 'dist')`""), @('worker', "worker --concurrency $concurrency"))) {
            $process = Start-Process -FilePath $binary -ArgumentList $service[1] -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeDirectory "$($service[0]).log") -RedirectStandardError (Join-Path $runtimeDirectory "$($service[0]).error.log") -PassThru
            $children += @{ name=$service[0]; id=$process.Id; started=$process.StartTime.ToUniversalTime().ToString('O') }
            ConvertTo-Json -InputObject @($children) | Set-Content -LiteralPath $statePath -Encoding utf8
        }
        $ready = $false
        for ($i=0; $i -lt 60; $i++) {
            if (@($children | Where-Object { Get-OwnedProcess $_ }).Count -ne 2) { throw 'A service exited during startup.' }
            try { $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 1; if ($health.status -eq 'healthy') { $ready=$true; break } } catch { }
            Start-Sleep -Milliseconds 500
        }
        if (!$ready) { throw 'Health check timed out.' }
    } catch { Stop-Services; throw }
    Write-Output "FastRead: $url/ | Data: $env:FASTREAD_WEB_ROOT | Logs: $runtimeDirectory"
    if (!$NoOpen) { Start-Process "$url/" }
} finally { $lock.Dispose() }
