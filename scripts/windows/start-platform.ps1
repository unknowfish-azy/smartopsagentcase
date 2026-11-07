#requires -Version 5.1
<#
.SYNOPSIS
    SmartOpsAgent 全栈一键启停（Windows / PowerShell 5.1）。

.DESCRIPTION
    管理本机八个"设备"（服务）：MySQL、Redis、Ollama、后端、knowledge、
    ai-service、前端用户端、前端管理端，可选 mock SSH（E2E 用）。
    特性：
      * 只起没在跑的服务（端口已监听且健康则跳过，不会重复起）
      * 统一从根 .env 注入环境变量（含 run token secret / DB 口令 / LLM 配置）
      * 进程与日志可追溯：.runtime\pids\<svc>.pid、.runtime\logs\<svc>-<ts>.log
      * 停止时按进程树杀（cmd -> mvn -> java 一并回收）
      * 每个服务带健康门禁，起不来会明确报错而不是假成功

.EXAMPLE
    .\start-platform.ps1                 # 启动全部
    .\start-platform.ps1 -Status         # 看状态
    .\start-platform.ps1 -Stop           # 停止全部
    .\start-platform.ps1 -Restart        # 重启全部
    .\start-platform.ps1 -SkipMockSsh    # 不起 mock SSH（演示模式推荐）
    .\start-platform.ps1 -KeepAlive      # 起完后不退出，前台保持（CI / 需要在会话内保活时用）
    .\start-platform.ps1 -Dev            # 后端走 mvn spring-boot:run（改代码即时生效，多一个 JVM 约 400MB）
#>
[CmdletBinding()]
param(
    [switch]$Status,
    [switch]$Stop,
    [switch]$Restart,
    [switch]$SkipMockSsh,
    [switch]$SkipAdmin,
    [switch]$KeepAlive,
    [switch]$Dev,
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # 避免 Invoke-* 的进度条污染输出
Add-Type -AssemblyName System.Net.Http | Out-Null

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$RuntimeDir = Join-Path $ProjectRoot '.runtime'
$PidDir = Join-Path $RuntimeDir 'pids'
$LogDir = Join-Path $RuntimeDir 'logs'
New-Item -ItemType Directory -Path $PidDir, $LogDir -Force | Out-Null

function Write-Step($msg) { Write-Host "[..] $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "[!!] $msg" -ForegroundColor Yellow }

# 从 Git Bash / CI 继承时，环境块里往往同时存在 http_proxy 与 HTTP_PROXY。
# Windows 环境变量大小写不敏感，.NET 在组装子进程环境块时遇到"同名不同大小写"的键会抛异常，
# 一旦抛出，后续每个 Start-Process 都会失败（表现为"脚本跑一半什么都没起来"）。
# 另外本栈全是本机服务，系统代理曾把 127.0.0.1 的请求也劫持出去，导致健康检查假失败。
# 所以这里统一策略：清掉全部 *_proxy，只保留 NO_PROXY=本机网段。
function Clear-ProxyVarDuplicates {
    $vars = [Environment]::GetEnvironmentVariables('Process')
    $keys = @($vars.Keys | Where-Object { $_ -match '(?i)_proxy$' })
    if ($keys.Count -eq 0) { return }
    foreach ($k in $keys) { [Environment]::SetEnvironmentVariable($k, $null, 'Process') }
    [Environment]::SetEnvironmentVariable('NO_PROXY', '127.0.0.1,localhost,::1', 'Process')
    Write-Ok "代理变量已归一化（清除 $($keys.Count) 个：$($keys -join ', ')）"
}

# 只保留有值的键：空值不注入，避免把 .env 里已载入的口令"覆盖成空"
function Select-EnvTable([hashtable]$pairs) {
    $t = @{}
    foreach ($k in $pairs.Keys) {
        $v = $pairs[$k]
        if ($null -ne $v -and "$v".Length -gt 0) { $t[$k] = "$v" }
    }
    return $t
}

function Test-Port([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(800, $false)) { return $false }
        $client.EndConnect($async)
        return $true
    }
    catch { return $false }
    finally { $client.Close() }
}

function Test-Health([string]$Url, [string]$Expect) {
    if (-not $Url) { return $true }
    # 用 HttpClient + UseProxy=false：本机服务不能走系统代理（历史上代理劫持过 localhost）
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.UseProxy = $false
    $handler.AllowAutoRedirect = $true
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(5)
    try {
        $resp = $client.GetAsync($Url).GetAwaiter().GetResult()
        $code = [int]$resp.StatusCode
        if ($code -lt 200 -or $code -ge 400) { return $false }
        if (-not $Expect) { return $true }
        $body = $resp.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        return ($body -match [regex]::Escape($Expect))
    }
    catch { return $false }
    finally { $client.Dispose() }
}

function Import-ProjectEnvironment {
    $envFile = Join-Path $ProjectRoot '.env'
    if (Test-Path -LiteralPath $envFile) {
        # Windows 环境变量大小写不敏感：.env 里同时有 http_proxy/HTTP_PROXY 时必须去重，
        # 否则 SetEnvironmentVariable 会抛 "键重复"（曾导致 Start-Process 直接失败）。
        $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        $skipped = @()
        foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
                $name = $matches[1]; $value = $matches[2]
                if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                    $value = $value.Substring(1, $value.Length - 2)
                }
                if (-not $seen.Add($name)) { $skipped += $name; continue }
                try { [Environment]::SetEnvironmentVariable($name, $value, 'Process') }
                catch { $skipped += $name }
            }
        }
        Write-Ok "环境变量已从 .env 载入"
        if ($skipped.Count -gt 0) { Write-Warn2 ("忽略重复/无效键（Windows 大小写不敏感）：" + (($skipped | Select-Object -Unique) -join ', ')) }
    }
    else { Write-Warn2 "未找到 .env，将使用既有环境变量" }

    # JDK 17（后端必需）
    $candidates = @(
        (Join-Path $env:USERPROFILE 'scoop\apps\openjdk17\current'),
        (Join-Path $env:ProgramFiles 'Java\jdk-17'),
        'D:\Java\jdk-17'
    )
    $jdk = $candidates | Where-Object { Test-Path -LiteralPath (Join-Path $_ 'bin\java.exe') } | Select-Object -First 1
    if ($jdk) {
        $env:JAVA_HOME = $jdk
        $env:Path = (Join-Path $jdk 'bin') + ';' + $env:Path
        Write-Ok "JDK: $jdk"
    }
    else { Write-Warn2 "未找到 JDK 17，后端可能无法启动（请安装或设置 JAVA_HOME）" }
}

function Get-Python {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $fallback = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'
    if (Test-Path -LiteralPath $fallback) { return $fallback }
    throw '未找到 python（ai-service / knowledge 需要）'
}

function Start-Service4 {
    param(
        [string]$Name,
        [int]$Port,
        [string]$WorkDir,
        [string]$Command,
        [string]$HealthUrl,
        [string]$Expect,
        [string]$PidFile,
        [hashtable]$ExtraEnv = @{}
    )

    if (Test-Port $Port) {
        if (Test-Health $HealthUrl $Expect) {
            Write-Ok "$Name 已在 $Port 运行（跳过）"
            return
        }
        Write-Warn2 "$Name 端口 $Port 被占用但健康检查未通过：先停止旧进程再启动"
        return
    }

    if (-not (Test-Path -LiteralPath $WorkDir -PathType Container)) { throw "$Name 工作目录不存在: $WorkDir" }

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $log = Join-Path $LogDir ("{0}-{1}.log" -f $Name, $stamp)

    Write-Step "启动 $Name（端口 $Port）"
    # 环境变量走"进程继承"，不拼 set "K=V" &&：口令里一旦有 & " % 等字符，cmd 会解析错乱。
    # 父子继承发生在 CreateProcess 那一刻，起完立刻还原，不污染后续服务。
    $saved = @{}
    foreach ($k in $ExtraEnv.Keys) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
        [Environment]::SetEnvironmentVariable($k, [string]$ExtraEnv[$k], 'Process')
    }
    try {
        $proc = Start-Process -FilePath 'cmd.exe' -WorkingDirectory $WorkDir `
            -ArgumentList @('/c', $Command) -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $log -RedirectStandardError ($log -replace '\.log$', '.err.log')
    }
    finally {
        foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k], 'Process') }
    }
    Set-Content -LiteralPath $PidFile -Value $proc.Id -Encoding ASCII

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 1200
        if (Test-Health $HealthUrl $Expect) {
            Write-Ok "$Name 就绪（PID $($proc.Id)，日志 $log）"
            return
        }
        if ($proc.HasExited) {
            Write-Warn2 "$Name 进程已退出，查看日志: $log"
            Get-Content -LiteralPath $log -Tail 15 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "    $_" }
            return
        }
    }
    Write-Warn2 "$Name 在 $TimeoutSeconds 秒内未通过健康检查（日志 $log）"
}

function Stop-Service4 {
    param([string]$Name, [int]$Port, [string]$PidFile)

    $killed = $false
    if (Test-Path -LiteralPath $PidFile) {
        $procId = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($procId) {
            # taskkill 对"进程已不存在"会往 stderr 写错误；在 $ErrorActionPreference='Stop'
            # 下这会被提升成 NativeCommandError 直接中断整个停止流程（重复执行 -Stop 必踩）。
            # 这里临时降级 + 包 try，退出码仍以 $LASTEXITCODE 为准。
            $prev = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try { & taskkill.exe /PID $procId /T /F *>&1 | Out-Null } catch { }
            $ErrorActionPreference = $prev
            if ($LASTEXITCODE -eq 0) { $killed = $true }
        }
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    }
    # 兜底：按端口找占用者
    if (-not $killed -and (Test-Port $Port)) {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($conn) {
            $prev = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try { & taskkill.exe /PID $conn.OwningProcess /T /F *>&1 | Out-Null } catch { }
            $ErrorActionPreference = $prev
            $killed = $LASTEXITCODE -eq 0
        }
    }
    if ($killed) { Write-Ok "$Name 已停止" } elseif (Test-Port $Port) { Write-Warn2 "$Name 仍在 $Port 监听" } else { Write-Ok "$Name 未运行" }
}

# ── 服务定义（端口 / 健康端点 / 期望特征）─────────────────────────────────
$python = $null
$env:NO_PROXY = '127.0.0.1,localhost,::1'

$services = @(
    @{ Name = 'mysql';        Port = 3306;  Health = $null;                                  Expect = $null;                       Kind = 'system';   Critical = $true }
    @{ Name = 'redis';        Port = 6379;  Health = $null;                                  Expect = $null;                       Kind = 'redis';    Critical = $true }
    @{ Name = 'ollama';       Port = 11434; Health = 'http://127.0.0.1:11434/api/tags';      Expect = 'models';                    Kind = 'ollama';   Critical = $false }
    @{ Name = 'backend';      Port = 8080;  Health = 'http://127.0.0.1:8080/actuator/health'; Expect = 'UP';                        Kind = 'backend';  Critical = $true }
    @{ Name = 'knowledge';    Port = 8002;  Health = 'http://127.0.0.1:8002/api/ready';      Expect = 'smartops-knowledge-service'; Kind = 'python';  Critical = $true }
    @{ Name = 'ai-service';   Port = 8001;  Health = 'http://127.0.0.1:8001/api/health';     Expect = 'smartops-ai-service';        Kind = 'python';   Critical = $true }
    @{ Name = 'frontend';     Port = 5173;  Health = 'http://127.0.0.1:5173/';               Expect = $null;                        Kind = 'frontend'; Critical = $true }
    @{ Name = 'admin';        Port = 5174;  Health = 'http://127.0.0.1:5174/';               Expect = $null;                        Kind = 'admin';    Critical = $false }
    @{ Name = 'mock-ssh';     Port = 2222;  Health = $null;                                  Expect = $null;                       Kind = 'mockssh';  Critical = $false }
)

function Show-Status {
    $down = @()
    Write-Host ''
    Write-Host '================ SmartOpsAgent 运行状态 ================' -ForegroundColor White
    foreach ($svc in $services) {
        if ($svc.Name -eq 'mock-ssh' -and -not (Test-Port 2222)) { continue }
        $listening = Test-Port $svc.Port
        $healthy = if ($listening -and $svc.Health) { Test-Health $svc.Health $svc.Expect } elseif ($listening) { $true } else { $false }
        if (-not $healthy -and $svc.Critical) { $down += $svc.Name }
        $flag = if ($healthy) { 'UP  ' } elseif ($listening) { 'WARN' } else { 'DOWN' }
        $color = if ($healthy) { 'Green' } elseif ($listening) { 'Yellow' } else { 'Red' }
        Write-Host ("  [{0}] {1,-12} :{2,-6} {3}" -f $flag, $svc.Name, $svc.Port, $(if ($svc.Health) { $svc.Health } else { '-' })) -ForegroundColor $color
    }
    Write-Host '========================================================'
    return $down
}

# ── 动作分发 ────────────────────────────────────────────────────────────
Clear-ProxyVarDuplicates
Import-ProjectEnvironment
Write-Host ''

if ($Status) { Show-Status; exit 0 }

if ($Stop) {
    foreach ($svc in @($services | Where-Object { $_.Kind -ne 'system' })) {
        Stop-Service4 -Name $svc.Name -Port $svc.Port -PidFile (Join-Path $PidDir ($svc.Name + '.pid'))
    }
    Write-Host ''
    Write-Ok '全部服务已停止（MySQL 为系统服务，未停止）'
    exit 0
}

if ($Restart) {
    foreach ($svc in @($services | Where-Object { $_.Kind -ne 'system' })) {
        Stop-Service4 -Name $svc.Name -Port $svc.Port -PidFile (Join-Path $PidDir ($svc.Name + '.pid'))
    }
    Start-Sleep -Seconds 2
}

# MySQL：系统服务，仅在未监听时尝试拉起
if (-not (Test-Port 3306)) {
    Write-Step 'MySQL 未运行，尝试启动系统服务'
    $svc = Get-Service -Name 'MySQL*' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($svc) {
        try { Start-Service -Name $svc.Name; Start-Sleep -Seconds 3 } catch { Write-Warn2 "MySQL 启动失败: $($_.Exception.Message)" }
    }
    else { Write-Warn2 '未找到 MySQL 服务，请手工启动' }
}
if (-not (Test-Port 3306)) { throw 'MySQL 未就绪（3306 未监听），后续服务会启动失败' }
Write-Ok 'MySQL 3306 就绪'

# Redis
$redisExe = (Get-Command redis-server -ErrorAction SilentlyContinue).Source
if (-not (Test-Port 6379)) {
    if ($redisExe) {
        $log = Join-Path $LogDir ('redis-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
        $p = Start-Process -FilePath $redisExe -ArgumentList @('--port', '6379', '--bind', '127.0.0.1') -WindowStyle Hidden -PassThru -RedirectStandardOutput $log
        Set-Content -LiteralPath (Join-Path $PidDir 'redis.pid') -Value $p.Id -Encoding ASCII
        Start-Sleep -Seconds 2
        Write-Ok "Redis 已启动（PID $($p.Id)）"
    }
    else { Write-Warn2 '未找到 redis-server，请安装或加入 PATH' }
}
if (Test-Port 6379) { Write-Ok 'Redis 6379 就绪' }

# Ollama
if (-not (Test-Port 11434)) {
    $ollamaExe = (Get-Command ollama -ErrorAction SilentlyContinue).Source
    if (-not $ollamaExe) {
        $guess = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
        if (Test-Path -LiteralPath $guess) { $ollamaExe = $guess }
    }
    if ($ollamaExe) {
        $log = Join-Path $LogDir ('ollama-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
        $p = Start-Process -FilePath $ollamaExe -ArgumentList @('serve') -WindowStyle Hidden -PassThru -RedirectStandardOutput $log
        Set-Content -LiteralPath (Join-Path $PidDir 'ollama.pid') -Value $p.Id -Encoding ASCII
        Write-Step '等待 Ollama API 就绪'
        $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
        while ((Get-Date) -lt $deadline -and -not (Test-Health 'http://127.0.0.1:11434/api/tags' 'models')) { Start-Sleep -Seconds 2 }
    }
}
if (Test-Health 'http://127.0.0.1:11434/api/tags' 'models') { Write-Ok 'Ollama 11434 就绪' } else { Write-Warn2 'Ollama 未就绪（AI 对话将不可用）' }

# 后端
# 默认单 JVM 跑打好包的 jar：`mvn spring-boot:run` 会多养一个 ~420MB 的 Maven JVM，
# 而且启动要先跑一遍 Maven 生命周期，纯属浪费。改动源码后 jar 会自动重新打包。
# 需要 Maven 的热重启行为时加 -Dev。
$backendDir = Join-Path $ProjectRoot 'backend'
$backendJar = Join-Path $backendDir 'target\smartops-backend-0.0.1-SNAPSHOT.jar'
$jvmArgs = '-Xms128m -Xmx640m -XX:MaxMetaspaceSize=320m -XX:+UseSerialGC -XX:TieredStopAtLevel=1 -Xss1m -Dfile.encoding=UTF-8'

function Update-BackendJar {
    param([string]$Dir, [string]$Jar)
    if (-not (Test-Path -LiteralPath $Jar)) { return $true }
    $jarTime = (Get-Item -LiteralPath $Jar).LastWriteTimeUtc
    $pomTime = (Get-Item -LiteralPath (Join-Path $Dir 'pom.xml')).LastWriteTimeUtc
    if ($pomTime -gt $jarTime) { return $true }
    $srcRoot = Join-Path $Dir 'src'
    if (-not (Test-Path -LiteralPath $srcRoot)) { return $false }
    $newest = Get-ChildItem -LiteralPath $srcRoot -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in @('.java', '.yml', '.yaml', '.properties', '.xml', '.sql') } |
        Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    return ($newest -and $newest.LastWriteTimeUtc -gt $jarTime)
}

$useJar = -not $Dev
if (-not $useJar) {
    Write-Step '后端以 Maven 模式启动（-Dev 或 jar 不可用）'
    Start-Service4 -Name 'backend' -Port 8080 -WorkDir $backendDir `
        -Command 'mvn -s .mvn\smartops-settings.xml spring-boot:run -Dspring-boot.run.profiles=local -Dspring-boot.run.arguments=--server.port=8080' `
        -HealthUrl 'http://127.0.0.1:8080/actuator/health' -Expect 'UP' `
        -PidFile (Join-Path $PidDir 'backend.pid') `
        -ExtraEnv (Select-EnvTable @{
            SERVER_PORT = '8080'; SERVER__PORT = '8080';
            MYSQL_USERNAME = $env:MYSQL_USERNAME;
            MYSQL_PASSWORD = $env:MYSQL_PASSWORD;
            SMARTOPS_CHAT_RUN_TOKEN_SECRET = $env:SMARTOPS_CHAT_RUN_TOKEN_SECRET;
            SPRING_PROFILES_ACTIVE = 'local';
            MAVEN_OPTS = $jvmArgs;
        })
}
else {
    if (Update-BackendJar -Dir $backendDir -Jar $backendJar) {
        Write-Step '后端源码有更新，先打 jar（mvn -DskipTests package）'
        Push-Location $backendDir
        try {
            & mvn -s .mvn\smartops-settings.xml -q -DskipTests package
            if ($LASTEXITCODE -ne 0) { throw "mvn package 失败（退出码 $LASTEXITCODE）" }
        }
        finally { Pop-Location }
        Write-Ok "jar 已更新：$backendJar"
    }
    Start-Service4 -Name 'backend' -Port 8080 -WorkDir $backendDir `
        -Command ('java {0} -jar "{1}" --spring.profiles.active=local --server.port=8080' -f $jvmArgs, $backendJar) `
        -HealthUrl 'http://127.0.0.1:8080/actuator/health' -Expect 'UP' `
        -PidFile (Join-Path $PidDir 'backend.pid') `
        -ExtraEnv (Select-EnvTable @{
            SERVER_PORT = '8080'; SERVER__PORT = '8080';
            MYSQL_USERNAME = $env:MYSQL_USERNAME;
            MYSQL_PASSWORD = $env:MYSQL_PASSWORD;
            SMARTOPS_CHAT_RUN_TOKEN_SECRET = $env:SMARTOPS_CHAT_RUN_TOKEN_SECRET;
        })
}

# knowledge
# torch/OpenMP 默认按物理核数起线程（本机 32 核 → 提交内存 2.6GB），
# 限制为单线程后从 2.6GB 降到 1.1GB，而语料就 299 条，启动时间几乎不变。
$python = Get-Python
Start-Service4 -Name 'knowledge' -Port 8002 -WorkDir $ProjectRoot `
    -Command ('"{0}" -m uvicorn knowledge.server:app --host 127.0.0.1 --port 8002' -f $python) `
    -HealthUrl 'http://127.0.0.1:8002/api/ready' -Expect 'smartops-knowledge-service' `
    -PidFile (Join-Path $PidDir 'knowledge.pid') `
    -ExtraEnv (Select-EnvTable @{
        KNOWLEDGE_API_KEY = $env:KNOWLEDGE_API_KEY;
        OMP_NUM_THREADS = '1'; MKL_NUM_THREADS = '1';
        OPENBLAS_NUM_THREADS = '1'; NUMEXPR_NUM_THREADS = '1';
        TOKENIZERS_PARALLELISM = 'false';
    })

# ai-service
Start-Service4 -Name 'ai-service' -Port 8001 -WorkDir (Join-Path $ProjectRoot 'ai-service') `
    -Command ('"{0}" -m uvicorn app.main:app --host 127.0.0.1 --port 8001' -f $python) `
    -HealthUrl 'http://127.0.0.1:8001/api/health' -Expect 'smartops-ai-service' `
    -PidFile (Join-Path $PidDir 'ai-service.pid') `
    -ExtraEnv (Select-EnvTable @{
        CHAT_RUN_TOKEN_SECRET = $env:SMARTOPS_CHAT_RUN_TOKEN_SECRET;
        LLM_PROVIDER = $env:LLM_PROVIDER; LLM_MODEL = $env:LLM_MODEL;
        LLM_BASE_URL = $env:LLM_BASE_URL; LLM_API_KEY = $env:LLM_API_KEY;
        KNOWLEDGE_SERVICE_URL = $env:KNOWLEDGE_SERVICE_URL;
        KNOWLEDGE_API_KEY = $env:KNOWLEDGE_API_KEY;
    })

# 前端用户端 / 管理端
Start-Service4 -Name 'frontend' -Port 5173 -WorkDir (Join-Path $ProjectRoot 'frontend') `
    -Command 'set "NODE_OPTIONS=--max-old-space-size=384" && npm run dev -- --host 127.0.0.1 --port 5173' `
    -HealthUrl 'http://127.0.0.1:5173/' -Expect $null -PidFile (Join-Path $PidDir 'frontend.pid')

if (-not $SkipAdmin) {
    Start-Service4 -Name 'admin' -Port 5174 -WorkDir (Join-Path $ProjectRoot 'frontend') `
        -Command 'set "NODE_OPTIONS=--max-old-space-size=384" && npm run dev:admin -- --host 127.0.0.1 --port 5174' `
        -HealthUrl 'http://127.0.0.1:5174/' -Expect $null -PidFile (Join-Path $PidDir 'admin.pid')
}

# mock SSH（E2E 审批链路专用，演示可 -SkipMockSsh）
if (-not $SkipMockSsh) {
    Start-Service4 -Name 'mock-ssh' -Port 2222 -WorkDir $ProjectRoot `
        -Command ('"{0}" scripts/e2e/mock_ssh_server.py' -f $python) `
        -HealthUrl $null -Expect $null -PidFile (Join-Path $PidDir 'mock-ssh.pid')
}

$down = @(Show-Status)

Write-Host ''
Write-Host '访问入口：' -ForegroundColor White
Write-Host '  用户端   http://127.0.0.1:5173'
Write-Host '  管理端   http://127.0.0.1:5174'
Write-Host '  后端     http://127.0.0.1:8080/actuator/health'
Write-Host '  AI 服务  http://127.0.0.1:8001/api/health'
Write-Host '  Knowledge http://127.0.0.1:8002/api/ready'
Write-Host ''
Write-Host '日志：.runtime\logs\    进程号：.runtime\pids\' -ForegroundColor DarkGray

if ($down.Count -gt 0) {
    Write-Host ''
    Write-Warn2 ("启动未完成，以下关键服务未就绪: " + ($down -join ', '))
    Write-Warn2 "排查顺序：1) .runtime\logs 下对应日志末尾报错  2) 端口是否被旧进程占用  3) .\start-platform.ps1 -Stop 后重试"
    exit 1
}
Write-Host ''
Write-Ok '全部关键服务就绪，平台可用'

if ($KeepAlive) {
    Write-Host ''
    Write-Ok '保活模式：本窗口保持不退出，按 Ctrl+C 结束（子进程独立控制台，不受影响）'
    while ($true) { Start-Sleep -Seconds 30 }
}
