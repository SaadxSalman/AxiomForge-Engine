# scripts/dev.ps1 — one-command local stack for Windows (PowerShell).
#
#   powershell -File scripts/dev.ps1
#
# Starts the FastAPI backend (:8000) and the Next.js dashboard (:3000) as two
# background processes.  Works fully offline — Postgres/Neo4j/Weaviate/Redis
# are optional; retrieval degrades gracefully when they are absent.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "== AxiomForge-Engine dev stack ==" -ForegroundColor Cyan

# Load .env into this session (single source of configuration).
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$") {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim('"'), "Process")
        }
    }
    Write-Host "Loaded .env" -ForegroundColor Green
} else {
    Write-Warning ".env not found — using built-in defaults"
}

# API base used by the dashboard client.
$env:NEXT_PUBLIC_API_URL = $env:NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"

# --- backend ---------------------------------------------------------------
$server = Start-Process -PassThru python `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000" `
    -WorkingDirectory (Join-Path $root "apps\server") `
    -WindowStyle Minimized
Write-Host "API  → http://127.0.0.1:8000/docs  (pid $($server.Id))" -ForegroundColor Yellow

# --- frontend ---------------------------------------------------------------
$web = Start-Process -PassThru npm `
    -ArgumentList "run", "dev" `
    -WorkingDirectory (Join-Path $root "apps\web") `
    -WindowStyle Minimized
Write-Host "Web  → http://localhost:3000       (pid $($web.Id))" -ForegroundColor Yellow

Write-Host "`nBoth services are running. Press Ctrl+C to stop." -ForegroundColor Cyan
try { Wait-Process -Id $server.Id -ErrorAction SilentlyContinue } finally {
    Stop-Process -Id $web.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
}
