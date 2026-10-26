param([switch]$Cpu, [switch]$WaitOnError)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
function Invoke-Python([string[]]$Arguments) {
    & $script:studioPython @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python command failed (exit $LASTEXITCODE)." }
}
try {
    Write-Host 'Setting up VFX Pass Studio. Internet and several GB of free space are required.'
    $venvPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    if (!(Test-Path -LiteralPath $venvPython)) {
        $studioPython = Join-Path $PSScriptRoot 'runtime/python.exe'
        if (!(Test-Path -LiteralPath $studioPython)) {
            $studioPython = (& py -3.11 -c 'import sys; print(sys.executable)')
            if ($LASTEXITCODE -ne 0 -or !$studioPython) { throw 'Install Python 3.11 or use the Windows installer.' }
        }
        Invoke-Python @('-m', 'venv', '.venv')
    }
    $studioPython = $venvPython
    Invoke-Python @('-m', 'pip', 'install', '--upgrade', 'pip')
    $torchIndex = if ($Cpu) { 'https://download.pytorch.org/whl/cpu' } else { 'https://download.pytorch.org/whl/cu128' }
    Invoke-Python @('-m', 'pip', 'install', 'torch==2.8.0', 'torchvision==0.23.0', '--index-url', $torchIndex)
    Invoke-Python @('-m', 'pip', 'install', '-r', 'requirements.txt')
    & (Join-Path $PSScriptRoot 'packaging/install_prerequisites.ps1')
    Invoke-Python @('packaging/verify_runtime.py')
    '0.4.1' | Set-Content -LiteralPath '.venv/studio-ready.txt'
    Write-Host 'Ready. Model weights download when first used.'
    exit 0
} catch {
    Write-Host "Setup failed: $($_.Exception.Message)" -ForegroundColor Red
    if ($WaitOnError) { Read-Host 'Press Enter to close. Use Repair runtime to retry' | Out-Null }
    exit 1
}
