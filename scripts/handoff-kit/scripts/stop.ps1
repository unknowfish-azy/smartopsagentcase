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

# 停止顺序：前端 → AI 服务 → 知识服务 → 后端（与启动相反）。
# 先停依赖方（前端）再停被依赖方（后端），避免请求打到已关闭的后端报错。
# MySQL 是系统服务，不在这里停止；Redis 默认也不停止（可能是共享实例），加 -All 才停。
$targets = @(
    @{ Name = 'frontend';   Port = 5173 },
    @{ Name = 'admin';      Port = 5174 },
    @{ Name = 'ai-service'; Port = 8001 },
    @{ Name = 'knowledge';  Port = 8002 },
    @{ Name = 'backend';    Port = 8080 }
)
foreach ($t in $targets) { Stop-ServiceProcess -Name $t.Name -Port $t.Port }

# Redis：默认保留（可能是系统服务或被其它项目共用），-All 时才停
if ($All) {
    Stop-ServiceProcess -Name 'redis' -Port 6379
} elseif (Test-Port 6379) {
    Write-Blank
    Write-Host '[--] Redis 仍在运行（系统服务/共享实例，未停止）' -ForegroundColor DarkGray
}
# MySQL：始终不停止（系统服务，停掉会影响其它应用）
if (Test-Port 3306) {
    Write-Host '[--] MySQL 仍在运行（系统服务，未停止）' -ForegroundColor DarkGray
}

# 清掉残留 pid 文件（避免下次启动读到失效 PID）
Get-ChildItem -Path $script:PidDir -Filter '*.pid' -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

# 最终核对：应用端口应全部释放，仍在监听说明可能被别的程序占用
Write-Blank
$left = @()
foreach ($p in 5173, 5174, 8001, 8002, 8080) { if (Test-Port $p) { $left += $p } }
if ($left.Count -eq 0) { Write-Ok '应用服务已全部停止' }
else { Write-Warn ('仍有端口在监听：' + ($left -join ', ') + '（可能被别的程序占用）') }

Write-Blank
Write-Host '按任意键关闭...' -ForegroundColor DarkGray
if (-not $env:SMARTOPS_NO_PAUSE) { $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown') }
