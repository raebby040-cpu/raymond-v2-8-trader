$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

Write-Host "========================================"
Write-Host " Raymond v2.8 MT5 Execution Bridge"
Write-Host " DEMO ONLY"
Write-Host "========================================"

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Python virtual environment not found."
    Write-Host "Run:"
    Write-Host "python -m venv .venv"
    Write-Host ".\.venv\Scripts\pip.exe install -r requirements.txt"
    exit 1
}

if (-not (Test-Path ".\.env")) {
    Write-Host "WARNING: .env file not found."
    Write-Host "Create a local .env file from .env.example."
    exit 1
}

Write-Host "Checking MT5 bridge dependencies..."

& ".\.venv\Scripts\python.exe" -c "import MetaTrader5; print('MetaTrader5 package: OK')"

if ($LASTEXITCODE -ne 0) {
    Write-Host "MetaTrader5 package is unavailable."
    exit 1
}

Write-Host ""
Write-Host "Starting Raymond MT5 bridge..."
Write-Host "Port: 8100"
Write-Host "REAL accounts: BLOCKED"
Write-Host ""

& ".\.venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8100
