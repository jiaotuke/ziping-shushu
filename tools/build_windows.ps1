$ErrorActionPreference = 'Stop'
$zipingProject = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$env:PIP_CACHE_DIR = "$zipingProject\.cache\pip"
$env:PYINSTALLER_CONFIG_DIR = "$zipingProject\.cache\pyinstaller"
$env:TEMP = "$zipingProject\.cache\packaging-tmp"
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:PYINSTALLER_CONFIG_DIR,$env:TEMP | Out-Null
Set-Location -LiteralPath $zipingProject
& "$zipingProject\.tools\windows-build\Scripts\python.exe" -m PyInstaller --noconfirm --distpath "$zipingProject\dist" --workpath "$zipingProject\.tmp\windows-build" "$zipingProject\packaging\windows.spec" *> "$zipingProject\.tmp\windows-build.log"
if ($LASTEXITCODE -ne 0) { throw 'Windows build failed; see .tmp/windows-build.log.' }
Write-Output "Windows EXE: $zipingProject\dist\ZipingShushu-Windows\ZipingShushu.exe"
