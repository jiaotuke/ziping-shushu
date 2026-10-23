$ErrorActionPreference = 'Stop'
$zipingProject = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$env:PIP_CACHE_DIR = "$zipingProject\.cache\pip"
$env:PYINSTALLER_CONFIG_DIR = "$zipingProject\.cache\pyinstaller"
$env:TEMP = "$zipingProject\.cache\packaging-tmp"
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:PYINSTALLER_CONFIG_DIR,$env:TEMP | Out-Null
Set-Location -LiteralPath $zipingProject
$zipingBuildOutput = Join-Path "$zipingProject\.tmp" ('windows-release-' + [Guid]::NewGuid().ToString('N'))
& "$zipingProject\.tools\windows-build\Scripts\python.exe" -m PyInstaller --noconfirm --distpath $zipingBuildOutput --workpath "$zipingProject\.tmp\windows-build" "$zipingProject\packaging\windows.spec" *> "$zipingProject\.tmp\windows-build.log"
if ($LASTEXITCODE -ne 0) { throw 'Windows build failed; see .tmp/windows-build.log.' }
$zipingApplication = Join-Path $zipingBuildOutput 'ZipingShushu-Windows'
Set-Content -LiteralPath "$zipingProject\.tmp\windows-release-location.txt" -Value $zipingApplication -Encoding utf8
Write-Output "Windows EXE: $zipingApplication\ZipingShushu.exe"
