param([string]$InnoCompiler)
$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $studioRoot
$buildRoot = Join-Path $studioRoot 'build'
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
$pythonArchive = Join-Path $buildRoot 'python-3.11.9.nupkg'
if (!(Test-Path -LiteralPath $pythonArchive)) {
    Invoke-WebRequest 'https://www.nuget.org/api/v2/package/python/3.11.9' -OutFile $pythonArchive
}
$expected = '9283876D58C017E0E846F95B490DA3BCA0FC0A6EE1134B2870677CFB7EEC3C67'
if ((Get-FileHash -LiteralPath $pythonArchive -Algorithm SHA256).Hash -ne $expected) { throw 'Python runtime checksum mismatch.' }
$systemPython = Join-Path $studioRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $systemPython)) { $systemPython = (Get-Command python).Source }
& $systemPython packaging/stage_release.py
if ($LASTEXITCODE -ne 0) { throw 'Release staging failed.' }
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
& $compiler /nologo /target:winexe /reference:System.Windows.Forms.dll '/win32icon:ui\assets\vfx-pass-studio.ico' '/out:build\stage\VFX Pass Studio.exe' 'packaging\Launcher.cs'
if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed.' }
if (!$InnoCompiler) {
    $InnoCompiler = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
    if (!$InnoCompiler) { $InnoCompiler = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6/ISCC.exe' }
}
if (!(Test-Path -LiteralPath $InnoCompiler)) { throw 'Install Inno Setup or pass -InnoCompiler with the path to ISCC.exe.' }
& $InnoCompiler "/DSourceDir=$studioRoot" packaging/studio.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
Get-FileHash dist/VFX-Pass-Studio-Setup-0.4.0.exe -Algorithm SHA256
