<#
.SYNOPSIS
    检查当前进程环境中 SmartOpsAgent 必需的配置项是否齐全。

.DESCRIPTION
    逐一检查 MySQL / Redis / LLM / 加密密钥 / 内部 token / 知识服务地址
    等关键配置。任一非可选项缺失即以退出码 1 失败，便于 CI 或启动前预检。
    本脚本只读环境变量，不修改任何文件。

    注意：本脚本检查的是"当前进程环境变量"，不会自动读取根 .env。
    如需检查 .env 文件本身，请用 handoff-kit 的 check-env.ps1。

.EXAMPLE
    # 在已加载 .env 的 shell 中运行
    .\check-config.ps1

.EXAMPLE
    # 配合 start-platform.ps1 的环境加载使用
    powershell -Command "Get-Content .env | ForEach-Object { if ($_ -match '^(\\w+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2]) } }; .\scripts\windows\check-config.ps1"
#>
$ErrorActionPreference = 'Stop'

function Get-ConfigStatus {
    param([string[]]$Names, [switch]$Optional)
    foreach ($name in $Names) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if (-not [string]::IsNullOrWhiteSpace($value)) { return 'OK' }
    }
    if ($Optional) { return 'OPTIONAL' }
    return 'MISSING'
}

$checks = [ordered]@{
    MySQL     = Get-ConfigStatus @('MYSQL_PASSWORD')
    Redis     = Get-ConfigStatus @('REDIS_PASSWORD') -Optional
    LLM       = Get-ConfigStatus @('LLM_PROVIDER')
    Encryption = Get-ConfigStatus @('SMARTOPS_API_KEY_ENCRYPTION_KEY')
    Internal  = Get-ConfigStatus @('SMARTOPS_INTERNAL_TOKEN')
    Knowledge = Get-ConfigStatus @('KNOWLEDGE_SERVICE_URL')
}

foreach ($item in $checks.GetEnumerator()) {
    '{0,-12} {1}' -f $item.Key, $item.Value
}

if ($checks.Values -contains 'MISSING') { exit 1 }
