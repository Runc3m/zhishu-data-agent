param([string]$OutputDirectory = 'release')
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
Set-Location -LiteralPath $PSScriptRoot
$version = (Get-Content -LiteralPath 'VERSION' -Raw).Trim()
$output = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot $OutputDirectory))
if (-not $output.StartsWith($PSScriptRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Output must be inside the project.' }
$appDirectory = Join-Path $output 'Zhishu'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run start.ps1 once to install dependencies first.' }
if (-not (Test-Path -LiteralPath 'frontend\dist\index.html')) { throw 'Build the frontend first.' }
& $python -m pip install -r requirements-build.txt -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
# Only application assets are included. Never include storage, credentials or logs.
$webAssets = (Join-Path $PSScriptRoot 'frontend\dist') + ':frontend/dist'
$versionAsset = (Join-Path $PSScriptRoot 'VERSION') + ':.'
$localeAssets = (Join-Path $PSScriptRoot 'backend\locales') + ':backend/locales'
& $python -m PyInstaller --noconfirm --onedir --windowed --name Zhishu --distpath $output --workpath build --specpath build `
    --add-data $webAssets --add-data $versionAsset --add-data $localeAssets --hidden-import sqlalchemy.dialects.postgresql.psycopg `
    --hidden-import sqlalchemy.dialects.mysql.pymysql --hidden-import socksio `
    --collect-all sqlglot --collect-all psycopg --collect-all psycopg_binary `
    --exclude-module pytest --exclude-module IPython --exclude-module matplotlib launcher.py
if ($LASTEXITCODE -ne 0) { throw 'Windows build failed.' }
Copy-Item -LiteralPath 'WINDOWS-README.txt' -Destination (Join-Path $appDirectory 'README.txt')
Copy-Item -LiteralPath 'VERSION', 'LICENSE', 'THIRD_PARTY_NOTICES.md' -Destination $appDirectory
& .\scripts\collect-licenses.ps1 -Destination (Join-Path $appDirectory 'licenses')
$forbidden = Get-ChildItem -LiteralPath $appDirectory -Recurse -Force | Where-Object { $_.Name -in @('storage', 'local.key', 'app.sqlite3', '.env', 'launcher.log') -or $_.Extension -eq '.duckdb' }
if ($forbidden) { throw 'Refusing to package private runtime data.' }
$archive = Join-Path $output "Zhishu-v$version-windows-x64.zip"
Compress-Archive -LiteralPath $appDirectory -DestinationPath $archive -Force
$digest = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower()
Set-Content -LiteralPath "$archive.sha256" -Encoding ascii -Value "$digest  $([IO.Path]::GetFileName($archive))"
Write-Host "Ready: $archive"
