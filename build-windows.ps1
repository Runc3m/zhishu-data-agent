$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run start.ps1 once to install dependencies first.' }
if (-not (Test-Path -LiteralPath 'frontend\dist\index.html')) { throw 'Build the frontend first.' }
& $python -m pip install -r requirements-build.txt -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
# Only application assets are included. Never include storage, credentials or logs.
$webAssets = (Join-Path $PSScriptRoot 'frontend\dist') + ':frontend/dist'
& $python -m PyInstaller --noconfirm --onedir --windowed --name Zhishu --distpath release --workpath build --specpath build `
    --add-data $webAssets --hidden-import sqlalchemy.dialects.postgresql.psycopg `
    --hidden-import sqlalchemy.dialects.mysql.pymysql --hidden-import socksio `
    --collect-all sqlglot --collect-all psycopg --collect-all psycopg_binary `
    --exclude-module pytest --exclude-module IPython --exclude-module matplotlib launcher.py
if ($LASTEXITCODE -ne 0) { throw 'Windows build failed.' }
Copy-Item -LiteralPath 'WINDOWS-README.txt' -Destination 'release\Zhishu\README.txt'
$forbidden = Get-ChildItem -LiteralPath 'release\Zhishu' -Recurse -Force | Where-Object { $_.Name -in @('storage', 'local.key', 'app.sqlite3', '.env', 'launcher.log') -or $_.Extension -eq '.duckdb' }
if ($forbidden) { throw 'Refusing to package private runtime data.' }
Compress-Archive -LiteralPath 'release\Zhishu' -DestinationPath 'release\Zhishu-Windows-x64.zip' -Force
Write-Host 'Ready: release\Zhishu-Windows-x64.zip (share the ZIP, not the source storage folder)'
