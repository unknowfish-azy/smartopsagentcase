[CmdletBinding()]
param(
    [switch]$CloseExisting
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$exe = 'D:\Trae\Trae CN\Trae CN.exe'
$profile = Join-Path $root '.runtime\trae-profile'

if (-not (Test-Path -LiteralPath $exe)) {
    throw "Trae executable not found: $exe"
}

if ($CloseExisting) {
    Get-Process -Name 'Trae CN' -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

New-Item -ItemType Directory -Path $profile -Force | Out-Null
$arguments = @(
    '--user-data-dir', $profile,
    '--disable-extension=redhat.java',
    '--disable-extension=ms-python.vscode-pylance',
    '--disable-extension=vscjava.vscode-java-pack',
    '--new-window',
    $root
)
$process = Start-Process -FilePath $exe -ArgumentList $arguments -PassThru
Write-Output "Trae started for $root (PID $($process.Id))"
Write-Output "Profile: $profile"
