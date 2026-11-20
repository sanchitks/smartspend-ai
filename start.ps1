# Starts the SmartSpend API (http://localhost:8000) and website (http://localhost:5173) in two windows.
# First run installs dependencies. Usage:  powershell -ExecutionPolicy Bypass -File start.ps1

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

if (-not (Test-Path (Join-Path $backend ".venv"))) {
    Write-Host "Creating the Python environment (needs uv: https://docs.astral.sh/uv/)..."
    Push-Location $backend
    uv venv --python 3.13 .venv
    uv pip install --python .venv\Scripts\python.exe -r requirements.txt
    Pop-Location
}
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Host "Installing website dependencies..."
    Push-Location $frontend
    npm install
    Pop-Location
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location -LiteralPath '$backend'; .\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location -LiteralPath '$frontend'; npm run dev"
Write-Host "API:     http://localhost:8000/docs"
Write-Host "Website: http://localhost:5173"
