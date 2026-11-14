# ============================================================
# SmartOpsAgent Development Startup
# ============================================================
# 新手提示：如果你是第一次跑这个项目，请先用 scripts/handoff-kit/ 下的
#   1-检查环境.bat → 2-安装环境.bat → 3-启动平台.bat
# 一键脚本会自动生成 .env 安全密钥、建库、装依赖，比手动跑本脚本省心。
# 本脚本适合已装好环境、想快速拉起各服务（各服务独立 cmd 窗口看日志）的场景。
# ============================================================

$ErrorActionPreference = "Stop"


$ProjectRoot = Split-Path -Parent $PSScriptRoot

$ProjectRoot = Split-Path -Parent $ProjectRoot

# 新手保护：.env 不存在时提醒，避免启动后因缺密钥报错
$envFile = Join-Path $ProjectRoot '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    Write-Host ""
    Write-Host "[!!] 未找到 .env 文件。" -ForegroundColor Yellow
    Write-Host "     首次运行请先执行 scripts\handoff-kit\2-安装环境.bat" -ForegroundColor Yellow
    Write-Host "     （它会自动生成 .env 并填入随机密钥），或手动 copy .env.example .env 后填写必需安全字段。" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "     仍要继续？服务可能因缺少 SMARTOPS_CHAT_RUN_TOKEN_SECRET / KNOWLEDGE_API_KEY 等启动失败。" -ForegroundColor Yellow
    $reply = Read-Host "     输入 Y 继续，其它键退出"
    if ($reply -notmatch '^[Yy]$') { exit 1 }
}


$BackendDir = Join-Path $ProjectRoot "backend"

$FrontendDir = Join-Path $ProjectRoot "frontend"

$AIServiceDir = Join-Path $ProjectRoot "ai-service"

$DockerDir = Join-Path $ProjectRoot "deploy\docker"

# 本地启动必须与项目的 Maven 设置和 .env 保持一致：默认 Maven 用户目录
# 在当前机器上解析为 C:\.m2，既不可写又缺少依赖；项目提供了可写的专用仓库设置。
$envFile = Join-Path $ProjectRoot '.env'
if (Test-Path -LiteralPath $envFile) {
    foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
            $name = $matches[1]
            $value = $matches[2].Trim()
            if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
}
$jdk17 = Join-Path $env:USERPROFILE 'scoop\apps\openjdk17\current'
if (Test-Path -LiteralPath (Join-Path $jdk17 'bin\java.exe')) {
    $env:JAVA_HOME = $jdk17
    $env:Path = (Join-Path $jdk17 'bin') + ';' + $env:Path
}


Write-Host ""
Write-Host "============================================"
Write-Host " SmartOpsAgent Development Environment"
Write-Host "============================================"
Write-Host ""


# ============================================================
# Environment Check
# ============================================================

Write-Host "[1/5] Checking environment..."


$requiredCommands = @(
    "java",
    "mvn",
    "node",
    "npm",
    "python",
    "docker"
)


foreach ($command in $requiredCommands) {

    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {

        Write-Error "Missing command: $command"

        exit 1
    }

}


Write-Host "[OK] Environment ready."


# ============================================================
# Docker
# ============================================================
# MySQL + Redis 通过 docker compose 拉起（需要 Docker Desktop 已运行）。
# 与 start-platform.ps1 不同：本脚本直接在当前 shell 前台执行 docker compose，
# 不做健康检查等待——容器拉起后立刻进入下一步，后端启动时 MySQL 可能还没就绪，
# 后端会自动重试连接（Spring Boot 的 datasource 初始化有重试机制）。

Write-Host ""
Write-Host "[2/5] Starting MySQL and Redis..."


if (Test-Path $DockerDir) {

    Push-Location $DockerDir

    try {

        docker compose up -d

    }
    finally {

        Pop-Location

    }

}
else {

    Write-Warning "Docker directory not found: $DockerDir"

}


# ============================================================
# Backend
# ============================================================
# 启动策略：先 mvn package 打 jar，再用 java -jar 跑（而非 mvn spring-boot:run）。
# 原因：mvn spring-boot:run 会额外驻留一个 Maven 启动器 JVM（约 343MB），
# 加上应用 JVM（约 249MB）合计约 590MB；直接跑 jar 只需一个 JVM，省一半内存。
#
# /k 表示命令执行完后保留 cmd 窗口（与 start-platform.ps1 的 Hidden 窗口不同），
# 方便开发者实时看后端日志、Ctrl+C 停止。

Write-Host ""
Write-Host "[3/5] Starting Backend..."


if (Test-Path $BackendDir) {

    $BackendJvmOptions = "-Xms64m -Xmx512m -XX:MaxMetaspaceSize=192m " +
        "-XX:ReservedCodeCacheSize=96m -XX:MaxDirectMemorySize=128m " +
        "-XX:+UseSerialGC -XX:+ExitOnOutOfMemoryError"

    Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList "/k", "cd /d `"$BackendDir`" && mvn -s .mvn\smartops-settings.xml -q -DskipTests package && java $BackendJvmOptions -Dfile.encoding=UTF-8 -jar target\smartops-backend-0.0.1-SNAPSHOT.jar"

}
else {

    Write-Warning "Backend directory not found."

}


# ============================================================
# AI Service
# ============================================================
# uvicorn 单进程启动，不加 --reload（演示时不需要热重载，省一个 reloader 父进程）。
# /k 保留窗口看实时日志。

Write-Host ""
Write-Host "[4/5] Starting AI Service..."


if (Test-Path $AIServiceDir) {

    Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList "/k", "cd /d `"$AIServiceDir`" && python -m uvicorn app.main:app --host 0.0.0.0 --port 8001"

}
else {

    Write-Warning "AI Service directory not found."

}


# ============================================================
# Frontend
# ============================================================
# 用户层（5173）与管理员层（5174）是两个独立的 Vite dev server：
#   5173 用户层   -> vite.config.js
#   5174 管理员层 -> vite.config.admin.mjs
# 两者共用同一后端与同一套会话 / CSRF。
# NODE_OPTIONS 限制 Vite 内存上限（512MB），避免大项目 OOM。

Write-Host ""
Write-Host "[5/5] Starting Frontend..."

if (Test-Path $FrontendDir) {

    Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList "/k", "cd /d `"$FrontendDir`" && set `"NODE_OPTIONS=--max-old-space-size=512`" && npm run dev"

    Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList "/k", "cd /d `"$FrontendDir`" && set `"NODE_OPTIONS=--max-old-space-size=512`" && npm run dev:admin"

}
else {

    Write-Warning "Frontend directory not found."

}


Write-Host ""
Write-Host "============================================"
Write-Host " SmartOpsAgent startup commands launched."
Write-Host "============================================"
Write-Host ""

Write-Host "Backend    : http://localhost:8080"

Write-Host "AI Service : http://localhost:8001"

Write-Host "用户层     : http://localhost:5173"

Write-Host "管理员层   : http://localhost:5174"

Write-Host "MySQL      : localhost:3306"

Write-Host "Redis      : localhost:6379"

Write-Host ""
