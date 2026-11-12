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
function Start-ServiceProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][string]$WorkDir,
        # 两种启动方式二选一：
        #   -Exe + -ArgString  直接 CreateProcess（java / python 用，路径含空格也安全）
        #   -CommandLine       经 cmd /c（npm 这类 .cmd 包装器用）
        [string]$Exe,
        [string]$ArgString,
        [string]$CommandLine,
        [string]$HealthUrl,
        [string]$Expect,
        [hashtable]$ExtraEnv = @{},
        [int]$TimeoutSeconds = 240
    )

    Initialize-Runtime
    Clear-ProxyVars   # 兜底：调用方忘了清也会被这里纠正

    if (Test-Port $Port) {
        if (Test-Health $HealthUrl $Expect) { Write-Ok "$Name 已在 $Port 运行，跳过"; return $true }
        Write-Warn "$Name 端口 $Port 被占用但健康检查不过，可能残留进程；先运行 4-停止平台.bat"
        return $false
    }
    if (-not (Test-Path -LiteralPath $WorkDir)) { Write-Fail "$Name 工作目录不存在：$WorkDir"; return $false }

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $log = Join-Path $script:LogDir ("$Name-$stamp.log")
    $errLog = Join-Path $script:LogDir ("$Name-$stamp.err.log")

    $saved = @{}
    foreach ($k in $ExtraEnv.Keys) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
        [Environment]::SetEnvironmentVariable($k, [string]$ExtraEnv[$k], 'Process')
    }
    Write-Step "启动 $Name（端口 $Port）"
    try {
        if ($Exe) {
            $proc = Start-Process -FilePath $Exe -ArgumentList $ArgString -WorkingDirectory $WorkDir `
                -WindowStyle Hidden -PassThru -RedirectStandardOutput $log -RedirectStandardError $errLog
        } else {
            $proc = Start-Process -FilePath $env:ComSpec -WorkingDirectory $WorkDir `
                -ArgumentList @('/c', $CommandLine) -WindowStyle Hidden -PassThru `
                -RedirectStandardOutput $log -RedirectStandardError $errLog
        }
    } finally {
        foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k], 'Process') }
    }
    [System.IO.File]::WriteAllText((Join-Path $script:PidDir "$Name.pid"), [string]$proc.Id)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 1200
        if (Test-Health $HealthUrl $Expect) { Write-Ok "$Name 就绪（PID $($proc.Id)）"; return $true }
        if ($proc.HasExited) {
            Write-Fail "$Name 启动失败（进程已退出），日志末尾："
            Get-Content -LiteralPath $log -Tail 15 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
            Get-Content -LiteralPath $errLog -Tail 8 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
            return $false
        }
    }
    Write-Warn "$Name 在 $TimeoutSeconds 秒内未通过健康检查（日志：$log）"
    return $false
}

function Stop-ServiceProcess {
    param([string]$Name, [int]$Port)
    $pidFile = Join-Path $script:PidDir "$Name.pid"
    $killed = $false
    if (Test-Path -LiteralPath $pidFile) {
        $procId = (Get-Content -LiteralPath $pidFile | Select-Object -First 1)
        if ($procId) {
            $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
            try { & taskkill.exe /PID $procId /T /F 2>&1 | Out-Null } catch { }
            $ErrorActionPreference = $prev
            if ($LASTEXITCODE -eq 0) { $killed = $true }
        }
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    }
    if (-not $killed -and $Port -gt 0 -and (Test-Port $Port)) {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($conn) {
            $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
            try { & taskkill.exe /PID $conn.OwningProcess /T /F 2>&1 | Out-Null } catch { }
            $ErrorActionPreference = $prev
            $killed = ($LASTEXITCODE -eq 0)
        }
    }
    if ($killed) { Write-Ok "$Name 已停止" }
    elseif ($Port -gt 0 -and (Test-Port $Port)) { Write-Warn "$Name 仍在 $Port 监听" }
    else { Write-Ok "$Name 未在运行" }
}
