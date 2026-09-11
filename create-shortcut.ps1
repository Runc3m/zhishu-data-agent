$ErrorActionPreference = 'Stop'
$program = Join-Path $PSScriptRoot 'release\Zhishu\Zhishu.exe'
if (-not (Test-Path -LiteralPath $program)) { throw 'Build the Windows release first.' }
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $PSScriptRoot 'Zhishu.lnk'))
$shortcut.TargetPath = $program
$shortcut.Arguments = '--data-dir "' + (Join-Path $PSScriptRoot 'storage') + '"'
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = 'Zhishu Data Agent - open your analysis workspace'
$shortcut.Save()
