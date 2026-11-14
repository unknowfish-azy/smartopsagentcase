<#
.SYNOPSIS
    本地运行环境体检：端口、进程内存、Docker 容器、磁盘与可用内存。

.DESCRIPTION
    显示各服务端口监听情况与占用进程、knowledge 服务 HTTP 就绪状态、
    相关进程（java/node/mysqld/redis/ollama）内存占用、Docker 容器状态、
    系统可用内存与磁盘空间。只读，不修改任何状态。
    加 -Clean 会顺带清理 .runtime 里的旧构建快照与已退出的容器。

.PARAMETER Clean
    顺带清理 .runtime\backend 旧 jar 快照、mini 安装包缓存、已退出容器。

.EXAMPLE
    .\status-local.ps1

.EXAMPLE
    .\status-local.ps1 -Clean
#>
param([switch]$Clean)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. (Join-Path $PSScriptRoot 'service-readiness.ps1')

function Show-Port([int]$Port) {
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if (!$listeners.Count) { return "端口 $Port`: 未监听" }
    foreach ($listener in $listeners) {
        $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
        "端口 $Port / $($listener.LocalAddress)`: $($process.ProcessName) (PID $($listener.OwningProcess)) $([int]($process.WorkingSet64 / 1MB)) MB"
    }
    if (@($listeners.OwningProcess | Sort-Object -Unique).Count -gt 1) {
        "警告：端口 $Port 有多个进程监听，具体绑定可能遮蔽通配地址。"
    }
}

'== 服务端口 =='
Show-Port 8080
Show-Port 5173
Show-Port 3306
Show-Port 6379
Show-Port 11434
Show-Port 8001
Show-Port 8002
'== Knowledge HTTP readiness =='
if (Test-ServiceReadiness -Uri 'http://127.0.0.1:8002/api/ready' -ExpectedService 'smartops-knowledge-service' -RequireIndex) {
    'Knowledge: READY（实际请求端点的索引非空）'
} else {
    'Knowledge: NOT_READY（检查索引、旧版本及重复监听；端口存活不代表就绪）'
}

'== 相关进程内存 =='
Get-Process java, node, mysqld, redis-server, ollama -ErrorAction SilentlyContinue |
    Sort-Object WorkingSet64 -Descending |
    Select-Object @{n = '进程'; e = { $_.ProcessName } }, Id, @{n = '内存MB'; e = { [int]($_.WorkingSet64 / 1MB) } } |
    Format-Table -AutoSize

'== Docker 容器 =='
docker ps -a --format '{{.Names}}  {{.Status}}' 2>$null

$os = Get-CimInstance Win32_OperatingSystem
'== 内存 =='
'可用 {0:N0} MB / 总 {1:N0} MB' -f ($os.FreePhysicalMemory / 1024), ($os.TotalVisibleMemorySize / 1024)

'== 磁盘 =='
Get-PSDrive -PSProvider FileSystem |
    Where-Object { $_.Used -gt 0 } |
    Select-Object Name, @{n = '可用GB'; e = { [math]::Round($_.Free / 1GB, 1) } } |
    Format-Table -AutoSize

if ($Clean) {
    $backendDir = Join-Path $root '.runtime\backend'
    if (Test-Path -LiteralPath $backendDir) {
        # 每次重启都会拷一份 jar 留作回滚，只保留最新一份即可。
        $stale = Get-ChildItem -LiteralPath $backendDir -Filter '*.jar' |
            Sort-Object LastWriteTime -Descending | Select-Object -Skip 1
        $freed = ($stale | Measure-Object Length -Sum).Sum
        $stale | Remove-Item -Force
        '== 清理 =='
        '旧构建快照：{0:N1} MB' -f ($freed / 1MB)
    }
    $downloads = Join-Path $root '.runtime\mini\downloads'
    if (Test-Path -LiteralPath $downloads) {
        Get-ChildItem -LiteralPath $downloads -File | Remove-Item -Force
        'mini 安装包缓存：已清空'
    }
    docker container prune -f 2>$null | Out-Null
    '已退出容器：已清理'
}
