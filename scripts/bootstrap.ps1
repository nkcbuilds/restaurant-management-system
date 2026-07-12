# RestaurantOS — Windows bootstrap script.
#
# Run this from PowerShell on a fresh checkout to install everything:
#
#     .\scripts\bootstrap.ps1
#
# It is the Windows equivalent of `make setup`. It is idempotent: running
# it twice will not reinstall from scratch.
#
# After bootstrap.ps1, run the test suite:
#
#     .\scripts\test.ps1

$ErrorActionPreference = "Stop"

# Resolve repo root regardless of where the script is invoked from.
$RepoRoot = Resolve-Path "$PSScriptRoot\.."
Set-Location $RepoRoot

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }

# ---- Sanity checks -----------------------------------------------------

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python is not on PATH. Install Python 3.10+ and retry."
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw "npm is not on PATH. Install Node.js 20+ and retry."
}

$pyVersion = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$pyMajor, $pyMinor = $pyVersion.Split(".")
if ([int]$pyMajor -lt 3 -or ([int]$pyMajor -eq 3 -and [int]$pyMinor -lt 10)) {
  throw "Python 3.10+ is required (found $pyVersion)."
}
Ok "Python $pyVersion"

# ---- Frontend ----------------------------------------------------------

Step "Installing frontend dependencies (npm)"
& npm ci --legacy-peer-deps
if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }

# ---- Backend virtualenv ------------------------------------------------

$venv = Join-Path $RepoRoot "backend\.venv"
$venvPy = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
  Step "Creating virtualenv at $venv"
  & python -m venv $venv
  if ($LASTEXITCODE -ne 0) { throw "venv creation failed." }
} else {
  Ok "Reusing existing virtualenv at $venv"
}

if (-not (Test-Path $venvPy)) {
  throw "Virtualenv python not found at $venvPy"
}

Step "Installing backend dependencies"
& $venvPy -m pip install --upgrade pip | Out-Null
& $venvPy -m pip install -r backend/requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed." }

# ---- Done --------------------------------------------------------------

Write-Host ""
Write-Host "Bootstrap complete." -ForegroundColor Green
Write-Host ""
Write-Host "Next:"
Write-Host "  npm run typecheck && npm run lint && npm test    # frontend gates"
Write-Host "  backend\.venv\Scripts\python.exe -m pytest -q    # backend tests"
Write-Host "  npm run build                                  # production build"
Write-Host "  npm run dev  +  backend\.venv\Scripts\python.exe backend\run.py"
