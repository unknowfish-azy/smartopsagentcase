<#
.SYNOPSIS
    停止本机所有 SmartOpsAgent 项目服务（按进程路径精确回收，不误杀）。

.DESCRIPTION
    通过 Win32_Process 扫描命令行中包含项目根路径的 java / node / python /
    ollama / cmd / powershell 进程，先杀启动器再杀子进程，避免 reload
    父进程重新拉起 worker。然后停止 docker compose 里的 mysql / redis 容器
    （保留数据卷）。最后核对 5173/5174/8080/8001/11434 端口是否释放。

    新手一般用 handoff-kit/4-停止平台.bat 即可；本脚本适合需要精确回收
    或用 start-all.ps1 / start-dev.ps1 启动后停止的场景。

.PARAMETER ProjectRoot
    项目根目录，默认 D:\SmartOpsAgent。只有命令行含此路径的进程才会被停止。

.EXAMPLE
    .\stop-all-local.ps1

.EXAMPLE
    # 预览会停止哪些进程（不实际执行）
    .\stop-all-local.ps1 -WhatIf
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param([string]$ProjectRoot = 'D:\SmartOpsAgent')

$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
$rootPattern = [regex]::Escape($ProjectRoot + '\')
$failed = $false

Write-Host '=== SmartOpsAgent local shutdown ===' -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"

# Match project paths rather than killing every Java, Python or Node process.
# Read the process snapshot before stopping launchers and their children.
try {
    $processes = @(Get-CimInstance Win32_Process)
    $protectedIds = @($PID)
    $ancestor = $processes | Where-Object ProcessId -eq $PID | Select-Object -First 1
    while ($ancestor -and $ancestor.ParentProcessId -and $ancestor.ParentProcessId -notin $protectedIds) {
        $protectedIds += $ancestor.ParentProcessId
        $ancestor = $processes | Where-Object ProcessId -eq $ancestor.ParentProcessId | Select-Object -First 1
    }
    # ── 进程筛选：按进程名 + 命令行 + 项目路径匹配 ─────────────────
    # 只有"命令行含项目根路径"且"进程名/命令行匹配特定特征"的进程才会被选中，
    # 避免误杀系统里其它 java/node/python 进程（比如 IDE、其它项目）。
    $selected = @{}
    foreach ($process in $processes) {
        if ($process.ProcessId -in $protectedIds) { continue }   # 跳过受保护的祖先进程
        $command = [string]$process.CommandLine
        $projectPath = $command -match $rootPattern               # 命令行是否含项目根路径
        $match = switch -Regex ($process.Name) {
            # java：后端 jar 或 maven 进程（smartops/spring-boot/plexus 是 maven 类加载器）
            '^java(w)?\.exe$' { $projectPath -and ($command -match 'smartops|spring-boot|org\.codehaus\.plexus'); break }
            # node：Vite dev server 或 npm 进程
            '^node\.exe$' { $projectPath -and ($command -match 'vite|npm'); break }
            # python：uvicorn（知识/AI 服务）或 multiprocessing worker
            '^python(w|[0-9.]*)?\.exe$' { $projectPath -and ($command -match 'uvicorn|multiprocessing'); break }
            # ollama：只杀项目内置的 ollama.exe（.runtime/mini/runtime/），不碰用户自己装的
            '^ollama\.exe$' { [string]$process.ExecutablePath -ieq (Join-Path $ProjectRoot '.runtime\mini\runtime\ollama.exe'); break }
            # cmd：由 start-dev 等脚本拉起的日志窗口（含 -live.log 重定向）
            '^cmd\.exe$' { $projectPath -and ($command -match '(backend|frontend|ai-service)-live\.log'); break }
            # powershell：start-mini.ps1 的宿主进程
            '^(powershell|pwsh)\.exe$' { $projectPath -and ($command -match 'start-mini\.ps1'); break }
            default { $false }
        }
        if ($match) { $selected[$process.ProcessId] = $process }
    }
    # ── 递归加入子进程：把已选中进程的所有子孙也纳入回收范围 ─────────
    # 例如 cmd → mvn → java 三层进程树，只匹配到了 java，但 cmd 和 mvn 也要一起停。
    do {
        $added = $false
        foreach ($process in $processes) {
            if ($process.ProcessId -notin $protectedIds -and !$selected.ContainsKey($process.ProcessId) -and $selected.ContainsKey($process.ParentProcessId)) {
                $selected[$process.ProcessId] = $process
                $added = $true
            }
        }
    } while ($added)

    # 先杀启动器（父进程），再杀 worker（子进程）：
    # 如果先杀 worker，reload 监控器（如 uvicorn --reload 的父进程）会立刻重新拉起 worker，
    # 导致停不掉。按 CreationDate 排序（父进程先创建）保证先停父再停子。
    foreach ($process in @($selected.Values | Sort-Object CreationDate)) {
        if ($PSCmdlet.ShouldProcess("$($process.Name) PID $($process.ProcessId)", 'Stop project process')) {
            try {
                # 二次确认：PID 仍存在且创建时间一致（防止 PID 被复用后杀错进程）
                $current = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ProcessId)"
                if ($current -and $current.CreationDate -eq $process.CreationDate) {
                    Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
                    Write-Host "Stopped $($process.Name) PID $($process.ProcessId)"
                }
            } catch {
                if (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue) {
                    $failed = $true
                    Write-Warning "Could not stop PID $($process.ProcessId): $($_.Exception.Message)"
                }
            }
        }
    }
    if (!$selected.Count) { Write-Host 'No project service processes found.' }
} catch {
    $failed = $true
    Write-Warning "Could not inspect project processes: $($_.Exception.Message)"
}

$composeFile = Join-Path $ProjectRoot 'deploy\docker\docker-compose.yml'
if (Get-Command docker -ErrorAction SilentlyContinue) {
    if ($PSCmdlet.ShouldProcess('SmartOpsAgent MySQL and Redis containers', 'docker compose stop (keep data)')) {
        & docker compose --project-directory (Split-Path $composeFile) -f $composeFile stop mysql redis
        if ($LASTEXITCODE -ne 0) { $failed = $true; Write-Warning 'Docker container shutdown failed.' }
    }
} else { Write-Host 'Docker not installed; skipping containers.' }

if (!$WhatIfPreference) {
    # 5174 是管理员层前端服务；5173 是用户层前端服务。
    $remaining = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -in @(5173,5174,8080,8001,11434))
    if ($remaining.Count) {
        Write-Warning 'Service ports still occupied (unrelated processes are left running):'
        $remaining | Select-Object LocalPort,OwningProcess -Unique | Format-Table -AutoSize
        $failed = $true
    }
    if ($failed) { Write-Warning 'Shutdown incomplete; review the messages above.'; exit 1 }
    Write-Host 'Shutdown complete. Database data retained.' -ForegroundColor Green
}
