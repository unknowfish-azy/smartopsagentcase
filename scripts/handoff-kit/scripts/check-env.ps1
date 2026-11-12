<#
  环境体检：把"能不能跑"这件事一条一条列清楚。
  用法：1-检查环境.bat  或  powershell -ExecutionPolicy Bypass -File check-env.ps1
#>
param()

. (Join-Path $PSScriptRoot '_common.ps1')
Clear-ProxyVars

Write-Head 'SmartOpsAgent 环境体检'
Write-Host "包目录：$script:Root"
Write-Blank

$problems = @()
$nextSteps = @()

# ── 1. Node / npm ────────────────────────────────────────────────────
$node = Get-CommandPath 'node'
$npm = Get-CommandPath 'npm'
$nodeOk = $false
if ($node) {
    $v = (& $node -v 2>&1 | Out-String).Trim()
    $major = 0
    if ($v -match 'v(\d+)') { $major = [int]$matches[1] }
    if ($major -ge 18) { Write-Ok "Node.js $v"; $nodeOk = $true }
    else { Write-Fail "Node.js $v 版本过低（需 >= 18）"; $problems += 'node' }
} else {
    Write-Fail 'Node.js 未安装（前端需要）'
    $problems += 'node'
}
if ($npm) { Write-Ok "npm $((& $npm -v 2>&1 | Out-String).Trim())" } elseif ($nodeOk) { Write-Warn 'npm 不在 PATH' }

# ── 2. Python ────────────────────────────────────────────────────────
$py = Find-Python
$pyOk = $false
if ($py) {
    $pyMajor = [int]($py.Version.Split('.')[0]); $pyMinor = [int]($py.Version.Split('.')[1])
    if ($pyMajor -eq 3 -and $pyMinor -ge 11) {
        if ($pyMinor -ge 13) {
            Write-Warn "Python $($py.Version)  $($py.Path)"
            Write-Warn '  版本偏新：httptools / pytesseract 等依赖可能没有预编译包，建议装 Python 3.12'
        } else {
            Write-Ok "Python $($py.Version)  ($($py.Path))"
        }
        $pyOk = $true
    }
    else { Write-Fail "Python $($py.Version) 版本过低（需 >= 3.11）"; $problems += 'python' }
} else {
    Write-Fail 'Python 未安装（AI 服务 / 知识服务需要）'
    $problems += 'python'
}

# ── 3. JDK ───────────────────────────────────────────────────────────
$java = Find-Java
$javaOk = $false
if ($java) {
    $jv = Get-JavaVersion $java
    if ($jv -ge 17) { Write-Ok "JDK $jv  ($java)"; $javaOk = $true; $env:JAVA_HOME = (Split-Path -Parent (Split-Path -Parent $java)) }
    else { Write-Fail "JDK 版本 $jv 过低（需 17+）"; $problems += 'java' }
} else {
    Write-Fail 'JDK 17 未安装（后端需要）'
    $problems += 'java'
}

# ── 4. MySQL / Redis ─────────────────────────────────────────────────
$mysqlPort = Test-Port 3306
$redisPort = Test-Port 6379
$mysqlCli = Find-MySqlClient
$redisExe = Find-RedisServer

if ($mysqlPort) { Write-Ok 'MySQL 3306 正在监听' }
elseif ($mysqlCli) { Write-Warn 'MySQL 已安装但 3306 未监听（需先启动 MySQL 服务）'; $problems += 'mysql-off' }
else { Write-Fail 'MySQL 未安装 / 未启动（后端数据库）'; $problems += 'mysql' }

if ($redisPort) { Write-Ok 'Redis 6379 正在监听' }
elseif ($redisExe) { Write-Warn 'Redis 已安装但未运行（启动平台时会自动拉起）' }
else { Write-Warn 'Redis 未安装（不装也能启动，但后端健康检查会 DOWN、会话/限流可能异常）'; $problems += 'redis' }

# ── 5. 项目自带文件 ──────────────────────────────────────────────────
$envFile = Join-Path $script:Root '.env'
if (Test-Path -LiteralPath $envFile) { Write-Ok '.env 已生成' } else { Write-Warn '.env 未生成（安装环境时自动生成）' }

$nm = Join-Path $script:Root 'frontend\node_modules'
if (Test-Path -LiteralPath $nm) { Write-Ok '前端依赖 node_modules 已内置' } else { Write-Warn '前端依赖缺失，安装环境时会执行 npm install' }

$jar = Join-Path $script:Root 'backend\target\smartops-backend-0.0.1-SNAPSHOT.jar'
if (Test-Path -LiteralPath $jar) { Write-Ok "后端 jar 已内置（$([math]::Round((Get-Item $jar).Length/1MB,1)) MB，无需 Maven）" }
else { Write-Warn '后端 jar 缺失，需要 Maven 现场打包' }

if ($pyOk) {
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $aiDep = & $py.Path -c "import fastapi, uvicorn; print('ok')" 2>&1 | Out-String
    $knDep = & $py.Path -c "import numpy; print('ok')" 2>&1 | Out-String
    $ErrorActionPreference = $prev
    if ($aiDep -match 'ok') { Write-Ok 'Python 依赖（fastapi/uvicorn）已安装' } else { Write-Warn 'Python 依赖未安装 → 运行 2-安装环境.bat' }
    if ($knDep -match 'ok') { Write-Ok 'Python 依赖（numpy）已安装' } else { Write-Warn '知识服务依赖未安装 → 运行 2-安装环境.bat' }
}

# ── 6. 端口占用 ──────────────────────────────────────────────────────
Write-Blank
Write-Host '端口占用情况（应为空）：' -ForegroundColor White
$busy = @()
foreach ($p in 5173, 5174, 8080, 8001, 8002) {
    if (Test-Port $p) { Write-Warn "  $p 已被占用"; $busy += $p }
}
if ($busy.Count -eq 0) { Write-Ok '  5173 / 5174 / 8080 / 8001 / 8002 全部空闲' }

# ── 结论 ─────────────────────────────────────────────────────────────
Write-Head '体检结论'
if ($problems.Count -eq 0) {
    if ($busy.Count -gt 0) {
        Write-Warn '依赖齐全，但有端口被占用；先运行 4-停止平台.bat 或关掉占用程序，再启动。'
    } else {
        Write-Ok '依赖齐全，可以直接双击 2-安装环境.bat（首次）或 3-启动平台.bat。'
    }
} else {
    Write-Warn ('需要处理：' + ($problems -join ', '))
    Write-Blank
    Write-Host '推荐用 winget 一条命令装好（Windows 10/11 自带 winget）：' -ForegroundColor White
    if ($problems -contains 'node')   { Write-Host '  winget install OpenJS.NodeJS.LTS' -ForegroundColor Gray }
    if ($problems -contains 'python') { Write-Host '  winget install Python.Python.3.12' -ForegroundColor Gray }
    if ($problems -contains 'java')   { Write-Host '  winget install EclipseAdoptium.Temurin.17.JDK' -ForegroundColor Gray }
    if ($problems -contains 'mysql')  { Write-Host '  winget install Oracle.MySQL' -ForegroundColor Gray }
    if ($problems -contains 'redis')  { Write-Host '  winget install Memurai.MemuraiDeveloper' -ForegroundColor Gray }
    Write-Blank
    Write-Host '没有 winget 就去官网下载安装包；装完关掉本窗口重新打开再体检一次。' -ForegroundColor Gray
    Write-Host '详细说明见包根目录的「换台电脑怎么跑.md」。' -ForegroundColor Gray
}
Write-Blank
Write-Host '按任意键关闭...' -ForegroundColor DarkGray
if (-not $env:SMARTOPS_NO_PAUSE) { $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown') }
