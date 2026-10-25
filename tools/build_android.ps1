$ErrorActionPreference = 'Stop'
$zipingProject = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$env:JAVA_HOME = (Get-ChildItem -LiteralPath "$zipingProject\.tools\java17" -Directory | Select-Object -First 1).FullName
$env:PATH = "$env:JAVA_HOME\bin;" + $env:PATH
$env:ANDROID_HOME = "$zipingProject\.tools\android-sdk"
$env:ANDROID_USER_HOME = "$zipingProject\.cache\android-user"
$env:GRADLE_USER_HOME = "$zipingProject\.cache\gradle"
$env:PIP_CACHE_DIR = "$zipingProject\.cache\pip"
$env:TEMP = "$zipingProject\.cache\android-build-tmp"
$env:TMP = $env:TEMP
$env:ZIPING_BUILD_PYTHON = "$zipingProject\.venv\Scripts\python.exe"
$env:JAVA_TOOL_OPTIONS = '-Duser.home="' + "$zipingProject\.cache\android-user" + '"'
New-Item -ItemType Directory -Force -Path $env:ANDROID_USER_HOME,$env:GRADLE_USER_HOME,$env:TEMP | Out-Null
& $env:ZIPING_BUILD_PYTHON "$zipingProject\tools\prepare_android_package.py"
if ($LASTEXITCODE -ne 0) { throw 'Android staging failed.' }
& $env:ZIPING_BUILD_PYTHON "$zipingProject\tools\prepare_android_signing.py"
if ($LASTEXITCODE -ne 0) { throw 'Android signing setup failed.' }
$zipingSigning = Get-Content -LiteralPath "$zipingProject\.local\android-signing\signing.json" -Raw | ConvertFrom-Json
$env:ZIPING_KEYSTORE = $zipingSigning.keystore
$env:ZIPING_KEYSTORE_PASSWORD = $zipingSigning.password
if (!(Test-Path -LiteralPath $env:ZIPING_KEYSTORE)) {
    & "$env:JAVA_HOME\bin\keytool.exe" -genkeypair -alias ziping -keyalg RSA -keysize 3072 -validity 10000 -dname 'CN=ZipingShushu' -keystore $env:ZIPING_KEYSTORE '-storepass:env' ZIPING_KEYSTORE_PASSWORD '-keypass:env' ZIPING_KEYSTORE_PASSWORD *> "$zipingProject\.tmp\android-signing.log"
    if ($LASTEXITCODE -ne 0) { throw 'Android signing key creation failed.' }
}
$zipingNativePreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& "$zipingProject\.tools\gradle\gradle-8.9\bin\gradle.bat" -p "$zipingProject\android\ziping-shushu" --no-daemon --console=plain assembleRelease *> "$zipingProject\.tmp\android-app-build.log"
$zipingBuildExit = $LASTEXITCODE
$ErrorActionPreference = $zipingNativePreference
if ($zipingBuildExit -ne 0) { throw 'Android build failed; see .tmp/android-app-build.log.' }
New-Item -ItemType Directory -Force -Path "$zipingProject\dist" | Out-Null
Copy-Item -LiteralPath "$zipingProject\android\ziping-shushu\app\build\outputs\apk\release\app-release.apk" -Destination "$zipingProject\dist\ZipingShushu-Android.apk"
Write-Output "APK: $zipingProject\dist\ZipingShushu-Android.apk"
