param([Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$roots = @{
    python = (Join-Path $projectRoot '.venv\Lib\site-packages')
    frontend = (Join-Path $projectRoot 'frontend\node_modules\.pnpm')
}
foreach ($group in $roots.Keys) {
    $base = $roots[$group]
    $files = Get-ChildItem -LiteralPath $base -File -Recurse | Where-Object {
        $_.Name -match '^(LICENSE|LICENCE|COPYING|NOTICE|AUTHORS|COPYRIGHT)(\.|$)' -or
        ($_.FullName -match '[\\/]licenses[\\/]' -and $_.Extension -in @('.txt', '.md', '.rst'))
    }
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($base.Length).TrimStart('\')
        $target = Join-Path (Join-Path $destination $group) $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $target
    }
}
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$runtime = & $python -c 'import sys; print(sys.base_prefix)'
foreach ($name in @('LICENSE.txt', 'LICENSE')) {
    $file = Join-Path $runtime $name
    if (Test-Path -LiteralPath $file) { Copy-Item -LiteralPath $file -Destination (Join-Path $destination "Python-$name") }
}
$tcl = Join-Path $runtime 'tcl'
if (Test-Path -LiteralPath $tcl) {
    Get-ChildItem -LiteralPath $tcl -File -Recurse | Where-Object { $_.Name -match '^(license|copyright)' } | ForEach-Object {
        $name = $_.FullName.Substring($tcl.Length).TrimStart('\').Replace('\', '-')
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $destination "TclTk-$name")
    }
}
