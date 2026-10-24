# ============================================================
# SmartOpsAgent 管理员层前端服务（独立端口）
# ============================================================
#
# 用户层与管理层原本共用 5173 与同一个 SPA 实例，入口靠 ?portal=admin 区分。
# 本脚本单独拉起管理员层服务（默认 127.0.0.1:5174），使用户层 5173
# 与管理层 5174 各自独立、互不抢占端口。
#
# 两个入口共用同一后端与同一套会话/CSRF，分离的只是前端静态服务。
#
#   用户层   http://127.0.0.1:5173/       （npm run dev）
#   管理员层 http://127.0.0.1:5174/       （npm run dev:admin，本脚本）
#
# 只启动管理员层前端；后端、数据库、AI Service 请按其自身脚本启动。

[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [int]$Port = 5174,
    [string]$BackendOrigin = ''
)

$ErrorActionPreference = 'Stop'

$FrontendDir = Join-Path $ProjectRoot 'frontend'

if (-not (Test-Path $FrontendDir)) {
    Write-Error "找不到前端目录：$FrontendDir"
    exit 1
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Error '缺少 npm，请先安装 Node.js。'
    exit 1
}

# 端口占用要在启动前发现，避免 Vite 因 strictPort 直接退出却看不出原因。
$occupied = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object LocalPort -eq $Port)
if ($occupied.Count) {
    $owners = ($occupied | Select-Object -ExpandProperty OwningProcess -Unique) -join ', '
    Write-Warning "端口 $Port 已被占用（PID: $owners）。请先释放该端口，或用 -Port 指定其他端口。"
    exit 1
}

if ($BackendOrigin) {
    $env:SMARTOPS_BACKEND_ORIGIN = $BackendOrigin
}
$effectiveBackend = if ($env:SMARTOPS_BACKEND_ORIGIN) { $env:SMARTOPS_BACKEND_ORIGIN } else { 'http://127.0.0.1:8080' }

# 管理员层入口固定在 5174；-Port 覆盖时同步传给 Vite。
$env:SMARTOPS_ADMIN_PORT = "$Port"

Write-Host ''
Write-Host '============================================'
Write-Host ' SmartOpsAgent 管理员层前端服务'
Write-Host '============================================'
Write-Host "项目根目录 : $ProjectRoot"
Write-Host "管理员层   : http://127.0.0.1:$Port/"
Write-Host "用户层     : http://127.0.0.1:5173/ （由 npm run dev 提供，本脚本不动它）"
Write-Host "后端代理   : $effectiveBackend"
Write-Host ''

Push-Location $FrontendDir
try {
    & npm.cmd run dev:admin
}
finally {
    Pop-Location
}
