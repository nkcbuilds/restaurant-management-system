# RestaurantOS end-to-end smoke (Windows PowerShell).
#
# Boots the FastAPI backend, waits for /api/health to respond, runs the
# Node smoke script, then tears the backend down. Designed to be called
# from `make e2e` (or directly from CI).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\e2e.ps1

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path "$PSScriptRoot\.."
Set-Location $RepoRoot

$ApiUrl = if ($env:API_URL) { $env:API_URL } else { "http://localhost:8000" }
# PowerShell on Windows often tries IPv6 (::1) before IPv4 (127.0.0.1),
# and uvicorn binds to 0.0.0.0 (IPv4 only) by default. Force 127.0.0.1 to
# avoid a 30s wait that ends in 'connection refused' or 'timeout'.
$probeHost = $ApiUrl -replace '^https?://', '' -replace ':.*$', ''
if ($probeHost -eq 'localhost') {
  $probeUrl = $ApiUrl -replace 'localhost', '127.0.0.1'
} else {
  $probeUrl = $ApiUrl
}
$venvPy = Join-Path $RepoRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
  throw "Virtualenv python not found at $venvPy. Run .\scripts\bootstrap.ps1 first."
}

Write-Host "==> Starting backend on $ApiUrl (logs: $logPath, $errPath)"
$logPath = Join-Path $env:TEMP "restaurantos-backend.log"
$errPath = Join-Path $env:TEMP "restaurantos-backend.err"
Remove-Item -Force $logPath -ErrorAction SilentlyContinue
Remove-Item -Force $errPath -ErrorAction SilentlyContinue

# Pass --no-reload so uvicorn does NOT spawn a child worker. The auto-
# reloader watches the DB file (despite reload_excludes) and can restart
# the worker mid-request in test runs. The e2e smoke doesn't need hot
# reload; that's only useful for interactive development.
$backend = Start-Process `
  -FilePath $venvPy `
  -ArgumentList "run.py", "--no-reload" `
  -WorkingDirectory (Join-Path $RepoRoot "backend") `
  -RedirectStandardOutput $logPath `
  -RedirectStandardError $errPath `
  -PassThru `
  -NoNewWindow

try {
  Write-Host "==> Waiting for $probeUrl/api/health"
  $up = $false
  for ($i = 1; $i -le 30; $i++) {
    try {
      $r = Invoke-WebRequest -Uri "$probeUrl/api/health" -UseBasicParsing -TimeoutSec 2
      if ($r.StatusCode -eq 200) {
        Write-Host "    backend up after ${i}s"
        $up = $true
        break
      }
    } catch {
      $err = $_.Exception.Message
      if ($i -eq 1 -or $i % 5 -eq 0) {
        Write-Host "    attempt ${i}: $err"
      }
    }
    Start-Sleep -Seconds 1
  }

  if (-not $up) {
    Write-Host "Error: backend did not become healthy within 20s" -ForegroundColor Red
    Write-Host "---- backend log (stdout) ----" -ForegroundColor Red
    Get-Content $logPath -ErrorAction SilentlyContinue | Write-Host
    Write-Host "---- backend log (stderr) ----" -ForegroundColor Red
    Get-Content $errPath -ErrorAction SilentlyContinue | Write-Host
    throw "backend startup timeout"
  }

  Write-Host "==> Running e2e smoke"
  $env:API_URL = $ApiUrl
  & node scripts/e2e-smoke.cjs
  if ($LASTEXITCODE -ne 0) {
    throw "smoke failed (exit $LASTEXITCODE)"
  }
}
finally {
  Write-Host "==> Stopping backend (pid $($backend.Id))"
  Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
  # Wait for the port to release so the next run isn't "address already
  # in use".
  Start-Sleep -Seconds 1
  # Only remove the dev DB AFTER the backend has fully exited. Deleting
  # it while uvicorn's auto-reloader is running triggers a reload
  # mid-request and the next /api call races against the new worker.
  Remove-Item -Force (Join-Path $RepoRoot "backend\restaurant.db") -ErrorAction SilentlyContinue
}
