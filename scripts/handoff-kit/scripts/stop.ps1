<#
  一键停止：按 pid 文件回收进程，再按端口兜底。
  用法：4-停止平台.bat        停止应用（MySQL 系统服务不动）
        4-停止平台.bat -All    连托管启动的 Redis 一起停
#>
param([switch]$All)

. (Join-Path $PSScriptRoot '_common.ps1')

Write-Head 'SmartOpsAgent 停止'
Write-Host "包目录：$script:Root"
Write-Blank

$targets = @(
    @{ Name = 'frontend';   Port = 5173 },
    @{ Name = 'admin';      Port = 5174 },
    @{ Name = 'ai-service'; Port = 8001 },
    @{ Name = 'knowledge';  Port = 8002 },
    @{ Name = 'backend';    Port = 8080 }
)
foreach ($t in $targets) { Stop-ServiceProcess -Name $t.Name -Port $t.Port }

if ($All) {
    Stop-ServiceProcess -Name 'redis' -Port 6379
} elseif (Test-Port 6379) {
    Write-Blank
    Write-Host '[--] Redis 仍在运行（系统服务/共享实例，未停止）' -ForegroundColor DarkGray
}
if (Test-Port 3306) {
    Write-Host '[--] MySQL 仍在运行（系统服务，未停止）' -ForegroundColor DarkGray
}

# 清掉残留 pid 文件
Get-ChildItem -Path $script:PidDir -Filter '*.pid' -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Blank
$left = @()
foreach ($p in 5173, 5174, 8001, 8002, 8080) { if (Test-Port $p) { $left += $p } }
if ($left.Count -eq 0) { Write-Ok '应用服务已全部停止' }
else { Write-Warn ('仍有端口在监听：' + ($left -join ', ') + '（可能被别的程序占用）') }

Write-Blank
Write-Host '按任意键关闭...' -ForegroundColor DarkGray
if (-not $env:SMARTOPS_NO_PAUSE) { $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown') }
