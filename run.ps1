# Windows quick start:  right-click > Run with PowerShell   (or:  powershell -ExecutionPolicy Bypass -File run.ps1)
param([switch]$Mock)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  Write-Host "ffmpeg not found. Install it once with:  winget install Gyan.FFmpeg   (then reopen PowerShell)" -ForegroundColor Yellow
}
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python -m pip install -q -r requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host "Created .env — add your GNANI_API_KEY, then re-run." -ForegroundColor Yellow }
if ($Mock) { $env:PROVIDER_MODE = "mock" }
Write-Host "Kural running at http://localhost:8080  (admin: /admin, API docs: /docs)" -ForegroundColor Green
.\.venv\Scripts\python -m uvicorn app.main:app --port 8080
