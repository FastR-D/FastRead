param(
  [string]$Bundle = "fastread-frontend/src-tauri/bin/FastReadBackend",
  [string]$RuntimeRoot = "backend",
  [int]$Port = 18483,
  [int]$TimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"
$bundlePath = (Resolve-Path -LiteralPath $Bundle).Path
$executable = Join-Path $bundlePath "FastReadBackend-x86_64-pc-windows-msvc.exe"
$runId = [guid]::NewGuid().ToString("N")
$runtimeRootPath = (Resolve-Path -LiteralPath $RuntimeRoot).Path
$runtime = Join-Path $runtimeRootPath ".runtime/sidecar-smoke-$runId"
New-Item -ItemType Directory -Force -Path $runtime | Out-Null

$env:FASTREAD_DATA_ROOT = $runtime
$env:BACKEND_HOST = "127.0.0.1"
$env:BACKEND_PORT = [string]$Port

$stdout = Join-Path $runtime "stdout.log"
$stderr = Join-Path $runtime "stderr.log"
$process = Start-Process `
  -FilePath $executable `
  -WorkingDirectory $bundlePath `
  -RedirectStandardOutput $stdout `
  -RedirectStandardError $stderr `
  -WindowStyle Hidden `
  -PassThru

$healthy = $false
$statusCode = $null
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline -and -not $process.HasExited) {
  Start-Sleep -Seconds 2
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/api/sys_health" -TimeoutSec 2
    $statusCode = $response.StatusCode
    if ($statusCode -eq 200) {
      $healthy = $true
      break
    }
  }
  catch {
    # The service may still be starting.
  }
}

if (-not $process.HasExited) {
  Stop-Process -Id $process.Id -Force
  Wait-Process -Id $process.Id -ErrorAction SilentlyContinue
}
$process.Refresh()

[pscustomobject]@{
  Healthy = $healthy
  HttpStatus = $statusCode
  ExitCode = $process.ExitCode
  ProcessId = $process.Id
  Runtime = $runtime
  Stdout = $stdout
  Stderr = $stderr
} | ConvertTo-Json -Compress

if (-not $healthy) {
  exit 1
}
