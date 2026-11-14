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

Write-Host ""
Write-Host "[3/5] Starting Backend..."


if (Test-Path $BackendDir) {

    # 不要再使用 mvn spring-boot:run：它会额外驻留一个 Maven 启动器 JVM
    # （实测 343MB），与应用 JVM（249MB）合计约 590MB。
    # 改为「先打包，再用封顶参数的 JVM 直接跑 jar」，与算卦平台（HTLB）一致。
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

Write-Host ""
Write-Host "[4/5] Starting AI Service..."


if (Test-Path $AIServiceDir) {

    # 开发期不加 --reload：它会常驻一个 reloader 父进程 + 一个 worker，
    # 演示时不需要热重载，直接单进程运行即可。
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

Write-Host ""
Write-Host "[5/5] Starting Frontend..."

# 用户层与管理层是两个独立前端服务：
#   5173 用户层   -> vite.config.js        （理念与外观保持不变）
#   5174 管理员层 -> vite.config.admin.mjs （独立入口，不与用户层抢端口）
# 两者共用同一后端与同一套会话 / CSRF。

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
