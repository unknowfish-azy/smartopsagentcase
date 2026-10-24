# ============================================================
# SmartOpsAgent Development Startup
# ============================================================

$ErrorActionPreference = "Stop"


$ProjectRoot = Split-Path -Parent $PSScriptRoot

$ProjectRoot = Split-Path -Parent $ProjectRoot


$BackendDir = Join-Path $ProjectRoot "backend"

$FrontendDir = Join-Path $ProjectRoot "frontend"

$AIServiceDir = Join-Path $ProjectRoot "ai-service"

$DockerDir = Join-Path $ProjectRoot "deploy\docker"


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

    Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList "/k", "cd /d `"$BackendDir`" && mvn spring-boot:run"

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

    Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList "/k", "cd /d `"$AIServiceDir`" && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001"

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
        -ArgumentList "/k", "cd /d `"$FrontendDir`" && npm run dev"

    Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList "/k", "cd /d `"$FrontendDir`" && npm run dev:admin"

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