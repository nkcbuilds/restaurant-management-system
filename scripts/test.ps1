# RestaurantOS — Windows test runner.
#
# Mirrors `make test` for users without GNU make.
#
#     .\scripts\test.ps1

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path "$PSScriptRoot\.."
Set-Location $RepoRoot

$venvPy = Join-Path $RepoRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
  throw "Virtualenv not found. Run .\scripts\bootstrap.ps1 first."
}

function Run($cmd, $args) {
  Write-Host "==> $cmd $($args -join ' ')" -ForegroundColor Cyan
  & $cmd @args
  if ($LASTEXITCODE -ne 0) { throw "Step failed: $cmd" }
}

Run "npm"  @("run", "typecheck")
Run "npm"  @("run", "lint")
Run "npm"  @("run", "format:check")
Run "npm"  @("test")
Run $venvPy @("-m", "pytest", "-q")

Write-Host ""
Write-Host "All checks green." -ForegroundColor Green
