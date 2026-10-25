$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
$ffmpegBin = Join-Path $studioRoot 'tools/ffmpeg/bin'
if (!(Test-Path -LiteralPath (Join-Path $ffmpegBin 'ffmpeg.exe')) -or !(Test-Path -LiteralPath (Join-Path $ffmpegBin 'ffprobe.exe'))) {
    $downloadRoot = Join-Path $studioRoot 'cache/downloads'
    New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null
    $archive = Join-Path $downloadRoot 'ffmpeg-release-essentials.zip'
    $url = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
    Write-Host 'Downloading FFmpeg from gyan.dev...'
    $checksum = ((Invoke-WebRequest ($url + '.sha256') -UseBasicParsing).Content.Trim() -split '\s+')[0]
    if ($checksum -notmatch '^[0-9a-fA-F]{64}$') { throw 'Invalid FFmpeg checksum response.' }
    Invoke-WebRequest $url -OutFile $archive -UseBasicParsing
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $checksum) { throw 'FFmpeg checksum mismatch. Retry setup.' }
    $expanded = Join-Path $downloadRoot 'ffmpeg-expanded'
    Expand-Archive -LiteralPath $archive -DestinationPath $expanded -Force
    $bundle = Get-ChildItem -LiteralPath $expanded -Directory | Select-Object -First 1
    if (!$bundle -or !(Test-Path -LiteralPath (Join-Path $bundle.FullName 'bin/ffprobe.exe'))) { throw 'FFmpeg archive is missing ffprobe.' }
    New-Item -ItemType Directory -Force -Path (Join-Path $studioRoot 'tools/ffmpeg') | Out-Null
    Copy-Item -Path (Join-Path $bundle.FullName '*') -Destination (Join-Path $studioRoot 'tools/ffmpeg') -Recurse -Force
}
$webviewPaths = @(
    'HKCU:/Software/Microsoft/EdgeUpdate/Clients/{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'HKLM:/SOFTWARE/WOW6432Node/Microsoft/EdgeUpdate/Clients/{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'HKLM:/SOFTWARE/Microsoft/EdgeUpdate/Clients/{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
)
$hasWebview = $false
foreach ($path in $webviewPaths) { if (Get-ItemPropertyValue -LiteralPath $path -Name pv -ErrorAction SilentlyContinue) { $hasWebview = $true } }
if (!$hasWebview) {
    $downloadRoot = Join-Path $studioRoot 'cache/downloads'
    New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null
    $webviewInstaller = Join-Path $downloadRoot 'MicrosoftEdgeWebview2Setup.exe'
    Invoke-WebRequest 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $webviewInstaller -UseBasicParsing
    $signature = Get-AuthenticodeSignature -LiteralPath $webviewInstaller
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') { throw 'WebView2 signature verification failed.' }
    $process = Start-Process -FilePath $webviewInstaller -ArgumentList '/silent', '/install' -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "WebView2 installation failed ($($process.ExitCode))." }
}
