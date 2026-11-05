param(
    [string]$HostAddress = '127.0.0.1',
    [int]$Port = 8002,
    [int]$TimeoutSeconds = 40,
    # 开发态热重载：父进程常驻，knowledge/ 下 .py 改动后自动换 worker。
    # 需要换版本或换配置时用默认（不带 reload）的稳定启动。
    [switch]$Reload
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$logs = Join-Path $root '.runtime\logs'
[System.IO.Directory]::CreateDirectory($logs) | Out-Null

# 只结束"确实属于 knowledge.server"的进程，避免误杀占用 8002 的其它程序。
# --reload 模式下真正监听端口的是 worker 子进程，命令行里可能没有模块名，
# 因此向上追溯最多 4 层父进程，返回最顶层的 knowledge 启动进程（0 表示不属于我们）。
# 必须杀最顶层：只杀 worker 会让 reloader 父进程立刻重新拉起一个 worker 抢端口。
function Get-KnowledgeRoot([int]$OwnerId) {
    $rootId = 0
    $current = $OwnerId
    for ($depth = 0; $depth -lt 4 -and $current -gt 0; $depth++) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$current" -ErrorAction SilentlyContinue
        if (!$process) { break }
        if ($process.Name -match '^python' -and $process.CommandLine -match 'knowledge\.server') { $rootId = $current }
        $current = [int]$process.ParentProcessId
    }
    return $rootId
}

function Stop-ProcessTree([int]$OwnerId) {
    Get-CimInstance Win32_Process -Filter "ParentProcessId=$OwnerId" -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-ProcessTree -OwnerId $_.ProcessId }
    Stop-Process -Id $OwnerId -Force -ErrorAction SilentlyContinue
    Wait-Process -Id $OwnerId -Timeout 10 -ErrorAction SilentlyContinue
}

$listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique)
foreach ($ownerId in $listeners) {
    $rootId = Get-KnowledgeRoot $ownerId
    if ($rootId -gt 0) {
        Write-Output "Stopping knowledge service PID $rootId"
        Stop-ProcessTree $rootId
    }
    else {
        throw "Port $Port is owned by another application; refusing to stop it"
    }
}

for ($i = 0; $i -lt 20; $i++) {
    if (!(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 500
}

$arguments = @('-m', 'uvicorn', 'knowledge.server:app', '--host', $HostAddress, '--port', $Port)
if ($Reload) { $arguments += @('--reload', '--reload-dir', 'knowledge') }
$process = Start-Process -FilePath 'python' -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logs "knowledge-$stamp.out.log") `
    -RedirectStandardError (Join-Path $logs "knowledge-$stamp.err.log")
Write-Output "Knowledge launched: PID $($process.Id), logs .runtime/logs/knowledge-$stamp.*.log"

# /api/ready 才代表索引真的可检索；进程活着但未加载索引时以非零退出。
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 1
    if ($process.HasExited) { break }
    try {
        $ready = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/ready" -TimeoutSec 3
        if ($ready.status -eq 'READY') {
            Write-Output "Knowledge ready: $($ready.chunks) chunks"
            exit 0
        }
    }
    catch { }
}

# 失败时清理残留进程并输出日志尾部，避免半死进程继续占着端口。
if (!$process.HasExited) { Stop-ProcessTree $process.Id }
Get-Content -LiteralPath (Join-Path $logs "knowledge-$stamp.err.log") -Tail 20 -ErrorAction SilentlyContinue
throw "Knowledge failed to become ready within $TimeoutSeconds s"
