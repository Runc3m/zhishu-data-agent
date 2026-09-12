param([int]$Port = 8100, [switch]$Rebuild)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment.' }
}
& $venvPython -c "import importlib.util, sys; sys.exit(0 if all(importlib.util.find_spec(m) for m in 'fastapi uvicorn pandas duckdb sqlalchemy sqlglot httpx socksio cryptography multipart psycopg pymysql'.split()) else 1)"
if ($LASTEXITCODE -ne 0) {
    & $venvPython -m pip install -r requirements.lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
if ($Rebuild -or -not (Test-Path -LiteralPath 'frontend\dist\index.html')) {
    $pnpmCommand = Get-Command pnpm -ErrorAction SilentlyContinue
    Push-Location frontend
    try {
        if ($pnpmCommand) {
            pnpm install --frozen-lockfile
            if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
            pnpm build
        } else {
            throw 'Install Node.js 22+ and pnpm, then run this script again.'
        }
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
}
Write-Host "Data Agent: http://127.0.0.1:$Port  (Ctrl+C to stop)" -ForegroundColor Green
& $venvPython -m uvicorn backend.app:app --host 127.0.0.1 --port $Port
