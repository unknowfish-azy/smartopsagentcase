<#
  一键启动：Redis → 后端 → 知识服务 → AI 服务 → 前端（用户端 + 管理端）
  用法：
    3-启动平台.bat
    3-启动平台.bat -Open          # 启动完成后自动打开浏览器
    3-启动平台.bat -SkipAdmin     # 不起管理端（省一点内存）
    3-启动平台.bat -SkipRedis     # 本机已有 Redis 服务时跳过托管
#>
param(
    [switch]$Open,
    [switch]$SkipAdmin,
    [switch]$SkipRedis,
    [int]$TimeoutSeconds = 300
)

. (Join-Path $PSScriptRoot '_common.ps1')
Clear-ProxyVars
Initialize-Runtime

Write-Head 'SmartOpsAgent 启动'
Write-Host "包目录：$script:Root"

if (-not (Test-Path -LiteralPath (Get-DotEnvPath))) {
    Write-Fail '还没有 .env —— 请先双击 2-安装环境.bat'
    Write-Host '按任意键关闭...' -ForegroundColor DarkGray
    if (-not $env:SMARTOPS_NO_PAUSE) { $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown') }
    exit 1
}
Import-DotEnv
$envMap = Read-DotEnv

# JDK / Python / Node 补进 PATH，保证子进程能找到
$java = Find-Java
if ($java) {
    $env:JAVA_HOME = (Split-Path -Parent (Split-Path -Parent $java))
    $env:Path = (Split-Path -Parent $java) + ';' + $env:Path
    Write-Ok "JDK: $java"
} else {
    Write-Fail '未找到 JDK 17，后端无法启动（winget install EclipseAdoptium.Temurin.17.JDK）'
    exit 1
}
$py = Find-Python
if ($py) {
    $env:Path = (Split-Path -Parent $py.Path) + ';' + $env:Path
    Write-Ok "Python: $($py.Path)"
} else {
    Write-Fail '未找到 Python 3.11+（winget install Python.Python.3.12）'
    exit 1
}
$node = Get-CommandPath 'node'
if ($node) { $env:Path = (Split-Path -Parent $node) + ';' + $env:Path; Write-Ok "Node: $node" }
else { Write-Fail '未找到 Node.js（winget install OpenJS.NodeJS.LTS）'; exit 1 }

Write-Blank

# 启动顺序说明：Redis → 后端 → 知识服务 → AI 服务 → 前端。
# 依赖关系：后端需要 MySQL（系统服务，假设已运行）+ Redis；
#           AI 服务需要知识服务（KNOWLEDGE_SERVICE_URL）；
#           前端需要后端（API 代理）。所以按此顺序拉起。
# 每个服务都过 Start-ServiceProcess 的健康检查才算就绪，未就绪会打印日志末尾。

# ── 1. Redis ─────────────────────────────────────────────────────────
# Redis 用于后端的会话、限流、任务状态缓存。不是硬性依赖：
# Redis 不在时后端仍能启动（actuator/health 会显示 DOWN，但接口可用）。
$redisOk = Test-Port 6379
if (-not $redisOk -and -not $SkipRedis) {
    $redisExe = Find-RedisServer
    if ($redisExe) {
        # 优先用本地 redis-server.exe，绑定 127.0.0.1（不暴露到公网）
        Write-Step '启动 Redis（6379）'
        $log = Join-Path $script:LogDir ('redis-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
        $p = Start-Process -FilePath $redisExe -ArgumentList @('--port', '6379', '--bind', '127.0.0.1') -WindowStyle Hidden -PassThru -RedirectStandardOutput $log
        [System.IO.File]::WriteAllText((Join-Path $script:PidDir 'redis.pid'), [string]$p.Id)
        Start-Sleep -Seconds 2
        $redisOk = Test-Port 6379
        if ($redisOk) { Write-Ok 'Redis 就绪' } else { Write-Warn "Redis 未能监听 6379（日志：$log）" }
    } else {
        # 没找到 redis-server.exe，尝试启动系统服务（Memurai / Redis）
        $svc = Get-Service -Name 'Memurai*', 'Redis*' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($svc) {
            Write-Step "启动 Redis 服务 $($svc.Name)"
            try { Start-Service -Name $svc.Name -ErrorAction Stop; Start-Sleep -Seconds 3; $redisOk = Test-Port 6379 } catch { }
        }
    }
}
if ($redisOk) { Write-Ok 'Redis 6379 就绪' }
else { Write-Warn 'Redis 未就绪：平台仍可启动，但后端健康状态会显示 DOWN、会话/限流可能异常' }

# ── 2. 后端（jar 优先，无 Maven 也能跑）───────────────────────────────
# 优先用打好包的 jar 直接跑（省内存、启动快）；jar 不存在时才用 Maven 现场打包。
# JVM 参数经过封顶：-Xmx640m + SerialGC，避免后端吃掉太多内存。
$jar = Join-Path $script:Root 'backend\target\smartops-backend-0.0.1-SNAPSHOT.jar'
$backendDir = Join-Path $script:Root 'backend'
if (-not (Test-Path -LiteralPath $jar)) {
    $mvn = Get-CommandPath 'mvn'
    if ($mvn) {
        Write-Step '未找到 jar，先用 Maven 打包（首次较慢）'
        Push-Location $backendDir
        try { & $mvn -q -DskipTests package } finally { Pop-Location }
    }
}
if (-not (Test-Path -LiteralPath $jar)) {
    Write-Fail "后端 jar 不存在：$jar"
    exit 1
}

# Redis 就绪时期望健康检查返回 'UP'；Redis 不在时后端健康会是 DEGRADED，不做强校验
$backendArgs = '-Xms128m -Xmx640m -XX:MaxMetaspaceSize=320m -XX:+UseSerialGC -XX:TieredStopAtLevel=1 -Dfile.encoding=UTF-8 -jar "{0}" --spring.profiles.active=local --server.port=8080' -f $jar
$backendExpect = if ($redisOk) { 'UP' } else { $null }
$okBackend = Start-ServiceProcess -Name 'backend' -Port 8080 -WorkDir $backendDir -Exe $java -ArgString $backendArgs `
    -HealthUrl 'http://127.0.0.1:8080/actuator/health' -Expect $backendExpect `
    -TimeoutSeconds $TimeoutSeconds

# ── 3. 知识服务（:8002）──────────────────────────────────────────────
# knowledge.server:app 是 FastAPI 应用，提供 RAG 混合检索。
# ExtraEnv 里的 OMP_NUM_THREADS=1 等是为了限制 torch/OpenMP 线程数，
# 否则 torch 会按物理核数起线程（32 核机器 → 提交内存 2.6GB），限制后降到约 1.1GB。
$okKnowledge = Start-ServiceProcess -Name 'knowledge' -Port 8002 -WorkDir $script:Root `
    -Exe $py.Path -ArgString '-m uvicorn knowledge.server:app --host 127.0.0.1 --port 8002' `
    -HealthUrl 'http://127.0.0.1:8002/api/ready' -Expect 'smartops-knowledge-service' `
    -ExtraEnv @{ OMP_NUM_THREADS = '1'; MKL_NUM_THREADS = '1'; OPENBLAS_NUM_THREADS = '1'; NUMEXPR_NUM_THREADS = '1'; TOKENIZERS_PARALLELISM = 'false' } `
    -TimeoutSeconds $TimeoutSeconds

# ── 4. AI 服务（:8001）───────────────────────────────────────────────
# app.main:app 是 FastAPI 应用，提供 LLM 网关、对话、RAG 编排。
# 注入的环境变量：聊天令牌密钥、知识服务 API Key 与地址、LLM Provider。
# 这些值从根 .env 读取，由 2-安装环境.bat 自动生成。
$okAi = Start-ServiceProcess -Name 'ai-service' -Port 8001 -WorkDir (Join-Path $script:Root 'ai-service') `
    -Exe $py.Path -ArgString '-m uvicorn app.main:app --host 127.0.0.1 --port 8001' `
    -HealthUrl 'http://127.0.0.1:8001/api/health' -Expect 'smartops-ai-service' `
    -ExtraEnv @{
        CHAT_RUN_TOKEN_SECRET  = $envMap['SMARTOPS_CHAT_RUN_TOKEN_SECRET']
        KNOWLEDGE_API_KEY      = $envMap['KNOWLEDGE_API_KEY']
        KNOWLEDGE_SERVICE_URL  = 'http://127.0.0.1:8002'
        LLM_PROVIDER           = $envMap['LLM_PROVIDER']
    } `
    -TimeoutSeconds $TimeoutSeconds

# ── 5. 前端 ──────────────────────────────────────────────────────────
# 用户层（5173）与管理端（5174）是两个独立的 Vite dev server，共用同一套后端与会话。
# --strictPort 确保端口被占用时直接失败而不是自动换端口（避免访问错地址）。
$feDir = Join-Path $script:Root 'frontend'
$okFront = Start-ServiceProcess -Name 'frontend' -Port 5173 -WorkDir $feDir `
    -CommandLine 'npm run dev -- --host 127.0.0.1 --port 5173 --strictPort' `
    -HealthUrl 'http://127.0.0.1:5173/' -TimeoutSeconds $TimeoutSeconds

$okAdmin = $false
if (-not $SkipAdmin) {
    $okAdmin = Start-ServiceProcess -Name 'admin' -Port 5174 -WorkDir $feDir `
        -CommandLine 'npm run dev:admin -- --host 127.0.0.1 --port 5174 --strictPort' `
        -HealthUrl 'http://127.0.0.1:5174/' -TimeoutSeconds $TimeoutSeconds
}

# ── 6. 汇总 ──────────────────────────────────────────────────────────
Write-Blank
Write-Host '================ 运行状态 ================' -ForegroundColor White
$rows = @(
    @{ N = 'MySQL';        P = 3306;  H = $null;                                                  E = $null;                       Critical = $true },
    @{ N = 'Redis';        P = 6379;  H = $null;                                                  E = $null;                       Critical = $false },
    @{ N = '后端';         P = 8080;  H = 'http://127.0.0.1:8080/actuator/health';                E = $null;                       Critical = $true },
    @{ N = '知识服务';     P = 8002;  H = 'http://127.0.0.1:8002/api/ready';                      E = 'smartops-knowledge-service'; Critical = $true },
    @{ N = 'AI 服务';      P = 8001;  H = 'http://127.0.0.1:8001/api/health';                     E = 'smartops-ai-service';       Critical = $true },
    @{ N = '用户前端';     P = 5173;  H = 'http://127.0.0.1:5173/';                               E = $null;                       Critical = $true },
    @{ N = '管理前端';     P = 5174;  H = 'http://127.0.0.1:5174/';                               E = $null;                       Critical = $false }
)
$down = @()
foreach ($r in $rows) {
    if ($r.N -eq '管理前端' -and $SkipAdmin) { continue }
    $listen = Test-Port $r.P
    $healthy = if ($listen) { Test-Health $r.H $r.E } else { $false }
    if (-not $healthy -and $r.Critical) { $down += $r.N }
    $flag = if ($healthy) { 'UP  ' } elseif ($listen) { 'WARN' } else { 'DOWN' }
    $color = if ($healthy) { 'Green' } elseif ($listen) { 'Yellow' } else { 'Red' }
    Write-Host ("  [{0}] {1,-10} :{2}" -f $flag, $r.N, $r.P) -ForegroundColor $color
}
Write-Host '=========================================' -ForegroundColor White
Write-Blank
Write-Host '  用户端    http://127.0.0.1:5173/login' -ForegroundColor White
if (-not $SkipAdmin) { Write-Host '  管理端    http://127.0.0.1:5174/login' -ForegroundColor White }
Write-Host ("  管理员    {0} / {1}" -f $envMap['SMARTOPS_BOOTSTRAP_USERNAME'], $envMap['SMARTOPS_BOOTSTRAP_PASSWORD']) -ForegroundColor Yellow
Write-Host ("  日志      {0}" -f $script:LogDir) -ForegroundColor DarkGray
Write-Blank

if ($down.Count -gt 0) {
    Write-Fail ('未就绪：' + ($down -join ', '))
    Write-Host '  排查：1) 看 .runtime\logs 下对应服务的日志末尾  2) 双击 4-停止平台.bat 后重试' -ForegroundColor Gray
    Write-Host '按任意键关闭...' -ForegroundColor DarkGray
    if (-not $env:SMARTOPS_NO_PAUSE) { $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown') }
    exit 1
}

Write-Ok '平台已启动（关掉本窗口不影响，服务在后台运行；停止请双击 4-停止平台.bat）'
if ($Open) { Start-Process 'http://127.0.0.1:5173/login' | Out-Null }
Write-Blank
Write-Host '按任意键关闭本窗口...' -ForegroundColor DarkGray
if (-not $env:SMARTOPS_NO_PAUSE) { $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown') }
exit 0
