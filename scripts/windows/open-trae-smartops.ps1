<#
.SYNOPSIS
    用独立用户配置目录打开 Trae IDE 并加载本项目。

.DESCRIPTION
    启动 Trae CN，使用 .runtime/trae-profile 作为独立用户数据目录，
    禁用 Java / Python 扩展以避免 IDE 卡顿（项目已验证 Standard 模式
    + 手动启用扩展更稳定）。不会影响你日常使用的 Trae 配置。

    前置条件：D:\Trae\Trae CN\Trae CN.exe 存在。

.PARAMETER CloseExisting
    先关掉已有的 Trae CN 进程再打开。

.EXAMPLE
    .\open-trae-smartops.ps1
#>
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
