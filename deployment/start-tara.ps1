# PowerShell local process runner for Tara Backend & Frontend
$ErrorActionPreference = "Stop"

Write-Host "Starting Tara Private Deployment Services..." -ForegroundColor Green

# 1. Start Backend in background
$BackendProcess = Start-Process -FilePath "backend\.venv\Scripts\python.exe" -ArgumentList "-m uvicorn tara_api.main:app --host 127.0.0.1 --port 8000" -PassThru -NoNewWindow

Write-Host "Backend started (PID: $($BackendProcess.Id))" -ForegroundColor Cyan

# 2. Start Frontend in background
$FrontendProcess = Start-Process -FilePath "npm" -ArgumentList "--prefix frontend start" -PassThru -NoNewWindow

Write-Host "Frontend started (PID: $($FrontendProcess.Id))" -ForegroundColor Cyan
Write-Host "Tara deployment active on http://127.0.0.1:3000 (Proxy via Tailscale HTTPS for production)" -ForegroundColor Yellow
