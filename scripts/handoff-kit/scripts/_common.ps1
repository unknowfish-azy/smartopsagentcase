<#
  SmartOpsAgent 通用函数库（PowerShell 5.1 兼容）
  被 check-env.ps1 / setup.ps1 / start.ps1 / stop.ps1 点源引用。
  所有路径都基于本文件位置推导，不写死盘符，整个目录可以拷到任意盘/任意目录。
#>

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Net.Http -ErrorAction SilentlyContinue | Out-Null

# 快速开始\scripts\_common.ps1 -> 上两级 = 包根目录
$script:Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:RuntimeDir = Join-Path $script:Root '.runtime'
$script:PidDir = Join-Path $script:RuntimeDir 'pids'
$script:LogDir = Join-Path $script:RuntimeDir 'logs'

function Initialize-Runtime {
    foreach ($d in @($script:RuntimeDir, $script:PidDir, $script:LogDir)) {
        if (-not (Test-Path -LiteralPath $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
    }
}

# 空行必须走 Console 直写：Write-Host '' 在 -File 重定向场景下不产生换行，
# 会让提示行全部粘在一起（实测过）。
function Write-Blank { [Console]::WriteLine() }

function Write-Head($msg) {
    Write-Blank
    Write-Host ('=' * 64) -ForegroundColor DarkCyan
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host ('=' * 64) -ForegroundColor DarkCyan
}
function Write-Step($msg) { Write-Host "[..] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[!!] $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "[XX] $msg" -ForegroundColor Red }

# ── 进程环境：清代理，避免 127.0.0.1 的健康检查被系统代理劫持 ──────────────
# 另一个坑：某些工具会把 http_proxy / HTTP_PROXY 两个大小写版本同时塞进环境块。
# Windows 环境变量名不区分大小写，.NET 组装子进程环境块时遇到"同名不同大小写"会抛
# "已添加项。字典中的关键字:"http_proxy"所添加的关键字:"HTTP_PROXY""，
# 表现为 Start-Process 直接失败、脚本"跑一半什么都没起来"。所以每种写法都删一遍。
function Clear-ProxyVars {
    # 先记住代理值（用户可能确实要靠代理上网），去重后再按大写形式放回去
    $vars = [Environment]::GetEnvironmentVariables('Process')
    $keep = @{}
    foreach ($k in @($vars.Keys)) {
        if ($k -match '(?i)^(https?|all|ftp|socks)_proxy$' -and $vars[$k]) {
            $keep[$k.ToUpperInvariant()] = [string]$vars[$k]
        }
    }
    $names = @('http_proxy', 'https_proxy', 'all_proxy', 'ftp_proxy', 'socks_proxy', 'no_proxy')
    foreach ($n in $names) {
        foreach ($v in @($n, $n.ToUpperInvariant())) {
            try { [Environment]::SetEnvironmentVariable($v, $null, 'Process') } catch { }
        }
    }
    foreach ($k in $keep.Keys) {
        try { [Environment]::SetEnvironmentVariable($k, $keep[$k], 'Process') } catch { }
    }
    [Environment]::SetEnvironmentVariable('NO_PROXY', '127.0.0.1,localhost,::1', 'Process')
}

function Get-DotEnvPath { Join-Path $script:Root '.env' }

function Read-DotEnv {
    $map = @{}
    $path = Get-DotEnvPath
    if (-not (Test-Path -LiteralPath $path)) { return $map }
    foreach ($line in (Get-Content -LiteralPath $path -Encoding UTF8)) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
            $name = $matches[1]
            $value = $matches[2]
            if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            $map[$name] = $value
        }
    }
    return $map
}

# 把 .env 注入当前进程（Windows 环境变量大小写不敏感，必须去重）
function Import-DotEnv {
    $path = Get-DotEnvPath
    if (-not (Test-Path -LiteralPath $path)) { Write-Warn "未找到 .env（先运行 2-安装环境.bat）"; return }
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($line in (Get-Content -LiteralPath $path -Encoding UTF8)) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
            $name = $matches[1]; $value = $matches[2]
            if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            if (-not $seen.Add($name)) { continue }
            try { [Environment]::SetEnvironmentVariable($name, $value, 'Process') } catch { }
        }
    }
    Write-Ok ".env 已载入"
}

function Set-DotEnvValue {
    param([string]$Path, [string]$Key, [string]$Value)
    $lines = @()
    if (Test-Path -LiteralPath $Path) { $lines = @(Get-Content -LiteralPath $Path -Encoding UTF8) }
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^\s*$([regex]::Escape($Key))\s*=") {
            $lines[$i] = "$Key=$Value"
            $found = $true
        }
    }
    if (-not $found) { $lines += "$Key=$Value" }
    [System.IO.File]::WriteAllLines($Path, $lines, (New-Object System.Text.UTF8Encoding($false)))
}

function New-RandomHex {
    param([int]$Bytes = 24)
    $buf = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($buf); $rng.Dispose()
    return (($buf | ForEach-Object { $_.ToString('x2') }) -join '')
}

function New-RandomBase64Key {
    param([int]$Bytes = 32)
    $buf = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($buf); $rng.Dispose()
    return [Convert]::ToBase64String($buf)
}

# ── 网络 ──────────────────────────────────────────────────────────────
function Test-Port {
    param([int]$Port, [string]$ComputerName = '127.0.0.1')
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($ComputerName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(700, $false)) { return $false }
        $client.EndConnect($async); return $true
    } catch { return $false } finally { $client.Close() }
}

function Test-Health {
    param([string]$Url, [string]$Expect)
    if (-not $Url) { return $true }
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.UseProxy = $false
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(5)
    try {
        $resp = $client.GetAsync($Url).GetAwaiter().GetResult()
        $code = [int]$resp.StatusCode
        if ($code -lt 200 -or $code -ge 400) { return $false }
        if (-not $Expect) { return $true }
        $body = $resp.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        return ($body -match [regex]::Escape($Expect))
    } catch { return $false } finally { $client.Dispose() }
}

# ── 工具定位 ──────────────────────────────────────────────────────────
function Get-CommandPath([string]$Name) {
    $c = Get-Command $Name -ErrorAction SilentlyContinue
    if ($c -and $c.Source) { return $c.Source }
    return $null
}

function Find-Java {
    $candidates = @()
    if ($env:JAVA_HOME) { $candidates += (Join-Path $env:JAVA_HOME 'bin\java.exe') }
    $onPath = Get-CommandPath 'java'
    if ($onPath) { $candidates += $onPath }
    $candidates += @(
        (Join-Path $env:ProgramFiles 'Eclipse Adoptium\jdk-17*\bin\java.exe'),
        (Join-Path $env:ProgramFiles 'Java\jdk-17*\bin\java.exe'),
        (Join-Path $env:ProgramFiles 'Java\jdk-21*\bin\java.exe'),
        (Join-Path $env:USERPROFILE 'scoop\apps\openjdk17\current\bin\java.exe'),
        'C:\Java\jdk-17\bin\java.exe'
    )
    foreach ($c in $candidates) {
        $hit = Get-Item -Path $c -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

function Get-JavaVersion([string]$JavaExe) {
    if (-not $JavaExe) { return $null }
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try {
        $out = & $JavaExe -version 2>&1 | Out-String
    } catch { $out = '' } finally { $ErrorActionPreference = $prev }
    if ($out -match 'version "(\d+)') { return [int]$matches[1] }
    return $null
}

function Find-Python {
    $names = @('python', 'python3', 'py')
    $candidates = @()
    foreach ($n in $names) {
        $p = Get-CommandPath $n
        if ($p) { $candidates += $p }
    }
    $candidates += @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe')
    )
    foreach ($c in $candidates) {
        if (-not (Test-Path -LiteralPath $c)) { continue }
        # 跳过 Microsoft Store 的占位程序（python.exe 0 字节或跑起来无输出）
        $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        try {
            $out = & $c -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>&1 | Out-String
        } catch { $out = '' } finally { $ErrorActionPreference = $prev }
        if ($out -match '^(\d+)\.(\d+)') { return @{ Path = $c; Version = "$($matches[1]).$($matches[2])" } }
    }
    return $null
}

function Find-RedisServer {
    $p = Get-CommandPath 'redis-server'
    if ($p) { return $p }
    $candidates = @(
        (Join-Path $env:ProgramFiles 'Memurai\memurai.exe'),
        (Join-Path $env:ProgramFiles 'Redis\redis-server.exe'),
        'C:\Program Files\Memurai\memurai.exe'
    )
    $candidates += @(Get-ChildItem -Path (Join-Path $env:USERPROFILE 'scoop\apps\redis') -Filter 'redis-server.exe' -Recurse -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    foreach ($c in $candidates) { if ($c -and (Test-Path -LiteralPath $c)) { return $c } }
    return $null
}

function Find-MySqlClient {
    $p = Get-CommandPath 'mysql'
    if ($p) { return $p }
    $candidates = @(
        'C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe',
        'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe',
        'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe'
    )
    $candidates += @(Get-ChildItem -Path 'C:\Program Files\MySQL' -Filter 'mysql.exe' -Recurse -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    foreach ($c in $candidates) { if ($c -and (Test-Path -LiteralPath $c)) { return $c } }
    return $null
}

# ── 启动/停止 ─────────────────────────────────────────────────────────
#
# Start-ServiceProcess 是所有应用服务的统一启动入口（后端 / 知识 / AI / 前端等）。
# 它做了四件事：① 端口预检（已在跑且健康则跳过，端口被占但不健康则报错）
# ② 注入 ExtraEnv 环境变量（仅在 CreateProcess 那一刻生效，起完立即还原，不污染后续服务）
# ③ 用 Start-Process 拉起进程并把 stdout/stderr 重定向到 .runtime/logs/
# ④ 轮询健康端点直到就绪 / 进程退出 / 超时。
#
# Stop-ServiceProcess 是统一停止入口：优先读 pid 文件杀进程树，失败则按端口兜底找占用者。
# 两路都杀不掉时只告警不误杀（端口可能被别的程序占用）。
#
function Start-ServiceProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,           # 服务名（用于日志、pid 文件名、输出）
        [Parameter(Mandatory = $true)][int]$Port,             # 服务监听端口（用于预检和就绪等待）
        [Parameter(Mandatory = $true)][string]$WorkDir,       # 进程工作目录
        # 两种启动方式二选一：
        #   -Exe + -ArgString  直接 CreateProcess（java / python 用，路径含空格也安全）
        #   -CommandLine       经 cmd /c（npm 这类 .cmd 包装器用，必须走 shell 才能解析）
        [string]$Exe,
        [string]$ArgString,
        [string]$CommandLine,
        [string]$HealthUrl,                                   # 健康检查 URL（如 http://127.0.0.1:8080/actuator/health）
        [string]$Expect,                                      # 健康响应体内需包含的字符串（如 'UP'），为空则只看 HTTP 状态码
        [hashtable]$ExtraEnv = @{},                           # 仅本进程需要的环境变量（如 KNOWLEDGE_API_KEY），启动后还原
        [int]$TimeoutSeconds = 240                            # 等待就绪的超时秒数
    )

    Initialize-Runtime       # 确保 .runtime/pids 与 .runtime/logs 目录存在
    Clear-ProxyVars          # 兜底：调用方忘了清也会被这里纠正（防止系统代理劫持 localhost 健康检查）

    # ── 端口预检：避免重复拉起 ──────────────────────────────────────
    if (Test-Port $Port) {
        # 端口已被占用：如果健康检查也通过，说明服务已经在跑，直接跳过（幂等）
        if (Test-Health $HealthUrl $Expect) { Write-Ok "$Name 已在 $Port 运行，跳过"; return $true }
        # 端口被占但健康检查不过：多半是上一次的残留进程半死不活，让用户先停掉
        Write-Warn "$Name 端口 $Port 被占用但健康检查不过，可能残留进程；先运行 4-停止平台.bat"
        return $false
    }
    if (-not (Test-Path -LiteralPath $WorkDir)) { Write-Fail "$Name 工作目录不存在：$WorkDir"; return $false }

    # ── 准备日志文件（按服务名 + 时间戳命名，便于排查）──────────────
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $log = Join-Path $script:LogDir ("$Name-$stamp.log")        # stdout
    $errLog = Join-Path $script:LogDir ("$Name-$stamp.err.log") # stderr

    # ── 注入环境变量（仅在子进程创建那一刻生效）────────────────────
    # 为什么用"先保存→设置→finally 还原"而不是拼在命令行里？
    # 因为口令里可能含 & " % 等字符，拼在 cmd /c 里会被 shell 解析错乱。
    # 父子进程环境继承发生在 CreateProcess 瞬间，起完立刻还原，不影响后续启动的其它服务。
    $saved = @{}
    foreach ($k in $ExtraEnv.Keys) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
        [Environment]::SetEnvironmentVariable($k, [string]$ExtraEnv[$k], 'Process')
    }
    Write-Step "启动 $Name（端口 $Port）"
    try {
        if ($Exe) {
            # 直接启动可执行文件（java / python / ollama 等）
            $proc = Start-Process -FilePath $Exe -ArgumentList $ArgString -WorkingDirectory $WorkDir `
                -WindowStyle Hidden -PassThru -RedirectStandardOutput $log -RedirectStandardError $errLog
        } else {
            # 走 cmd /c 启动（npm 是 .cmd 包装器，必须经 shell 解析）
            $proc = Start-Process -FilePath $env:ComSpec -WorkingDirectory $WorkDir `
                -ArgumentList @('/c', $CommandLine) -WindowStyle Hidden -PassThru `
                -RedirectStandardOutput $log -RedirectStandardError $errLog
        }
    } finally {
        # 无论成功失败都还原环境变量，避免污染后续服务
        foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k], 'Process') }
    }
    # 记录 PID 到 .runtime/pids/<Name>.pid，供 Stop-ServiceProcess 读取
    [System.IO.File]::WriteAllText((Join-Path $script:PidDir "$Name.pid"), [string]$proc.Id)

    # ── 等待就绪：轮询健康端点 ─────────────────────────────────────
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 1200
        # 健康检查通过 → 服务就绪
        if (Test-Health $HealthUrl $Expect) { Write-Ok "$Name 就绪（PID $($proc.Id)）"; return $true }
        # 进程已经退出 → 启动失败，打印日志末尾帮助排查
        if ($proc.HasExited) {
            Write-Fail "$Name 启动失败（进程已退出），日志末尾："
            Get-Content -LiteralPath $log -Tail 15 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
            Get-Content -LiteralPath $errLog -Tail 8 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
            return $false
        }
    }
    # 超时：进程还活着但健康检查一直不过（可能在加载索引 / 编译等）
    Write-Warn "$Name 在 $TimeoutSeconds 秒内未通过健康检查（日志：$log）"
    return $false
}

# Stop-ServiceProcess：停止单个服务，采用"PID 文件优先 + 端口兜底"双保险。
function Stop-ServiceProcess {
    param([string]$Name, [int]$Port)
    $pidFile = Join-Path $script:PidDir "$Name.pid"
    $killed = $false
    # ── 第一优先：读 pid 文件杀进程树 ─────────────────────────────
    if (Test-Path -LiteralPath $pidFile) {
        $procId = (Get-Content -LiteralPath $pidFile | Select-Object -First 1)
        if ($procId) {
            # taskkill /T = 杀整个进程树（cmd → mvn → java 一并回收）
            # /F = 强制结束。临时降级 ErrorActionPreference 是因为 taskkill
            # 对"进程已不存在"会往 stderr 写错误，在 Stop 模式下会中断整个停止流程。
            $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
            try { & taskkill.exe /PID $procId /T /F 2>&1 | Out-Null } catch { }
            $ErrorActionPreference = $prev
            if ($LASTEXITCODE -eq 0) { $killed = $true }
        }
        # 无论是否杀掉，都删掉 pid 文件（避免下次读到失效 PID）
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    }
    # ── 第二优先：按端口找占用者兜底 ─────────────────────────────
    # pid 文件丢失 / 被手动改过 / 杀进程树失败时，用端口反查监听进程。
    if (-not $killed -and $Port -gt 0 -and (Test-Port $Port)) {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($conn) {
            $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
            try { & taskkill.exe /PID $conn.OwningProcess /T /F 2>&1 | Out-Null } catch { }
            $ErrorActionPreference = $prev
            $killed = ($LASTEXITCODE -eq 0)
        }
    }
    # ── 结果汇报 ─────────────────────────────────────────────────
    if ($killed) { Write-Ok "$Name 已停止" }
    elseif ($Port -gt 0 -and (Test-Port $Port)) { Write-Warn "$Name 仍在 $Port 监听" }
    else { Write-Ok "$Name 未在运行" }
}
