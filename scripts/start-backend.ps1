# SmartOps 后端一键启动脚本
# 用法：
#   scripts\start-backend.ps1              # 直接启动（凭据来自 backend\.env.local）
#   scripts\start-backend.ps1 -Build       # 先 mvn -DskipTests package 再启动
#   scripts\start-backend.ps1 -Port 8081   # 指定端口
#
# 坑位说明（2026-11-16 实测）：
#   1. 系统默认 java 是 Java 8，jar 需要 Java 17 —— 脚本自动定位 .jdks\ms-17.0.18
#   2. 裸 java -jar 缺 MySQL 凭据会报 Access denied —— 凭据必须经 backend\.env.local 注入
#      （该文件已被 .gitignore 忽略，不会入库；模板见 backend\.env.example）

param(
    [switch]$Build,
    [int]$Port = 8080,
    [string]$Jdk = "C:\Users\33908\.jdks\ms-17.0.18"
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$jar = Join-Path $repo 'backend\target\smartops-backend-0.0.1-SNAPSHOT.jar'

# 0) 已有健康实例则不重复启动（curl 而非 Invoke-WebRequest：PS5.1 解析 actuator ContentType 会抛异常）
$healthUrl = "http://localhost:$Port/actuator/health"
try {
    $body = curl.exe -s -m 3 $healthUrl
    if ($body -match '"UP"') {
        Write-Host "[跳过] 端口 $Port 已有健康实例，无需启动。如需重启请先停掉对应 java 进程。" -ForegroundColor Yellow
        exit 0
    }
} catch { }

# 1) JDK 17 校验
$java = Join-Path $Jdk 'bin\java.exe'
if (-not (Test-Path $java)) {
    Write-Host "[失败] 未找到 JDK 17：$java（用 -Jdk 参数指定其他路径）" -ForegroundColor Red
    exit 1
}

# 2) 可选构建
if ($Build) {
    Write-Host "[构建] mvn -DskipTests package ..." -ForegroundColor Cyan
    mvn -q -f (Join-Path $repo 'backend\pom.xml') -DskipTests package
    if ($LASTEXITCODE -ne 0) { Write-Host "[失败] Maven 构建失败" -ForegroundColor Red; exit 1 }
}
if (-not (Test-Path $jar)) {
    Write-Host "[失败] jar 不存在：$jar（用 -Build 先构建）" -ForegroundColor Red
    exit 1
}

# 3) 凭据：backend\.env.local > 默认值（全部键注入进程环境，含 SMARTOPS_*，如 SMARTOPS_SCIVERSE_API_KEY）
$envFile = Join-Path $repo 'backend\.env.local'
$cred = @{}
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.+?)\s*$') { $cred[$Matches[1]] = $Matches[2] }
    }
    foreach ($key in $cred.Keys) { Set-Item -Path "env:$key" -Value $cred[$key] }
}
if (-not $cred.ContainsKey('MYSQL_PASSWORD')) {
    Write-Host "[警告] backend\.env.local 未设置 MYSQL_PASSWORD，将使用默认值 root（大概率 Access denied）。" -ForegroundColor Yellow
    Write-Host "        请创建 $envFile 并写入：MYSQL_PASSWORD=<本机MySQL root密码>" -ForegroundColor Yellow
}

# 4) 启动（后台，日志落 .runtime/backend；凭据经进程环境变量继承，兼容 PS5.1+）
$logDir = Join-Path $repo '.runtime\backend'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$stdout = Join-Path $logDir "start-backend-$stamp.out.log"
$stderr = Join-Path $logDir "start-backend-$stamp.err.log"

# 注意：不能用 $args —— 它是 PowerShell 自动变量（脚本参数数组），赋值会导致传参错乱、进程秒退
# SciVerse 网关用 JVM 系统属性硬锁定：系统属性优先级高于 application.yml 与环境变量，
# 避免 yml 默认值/外部配置/系统环境变量任一处残留旧地址导致打到文档站 404。
# 注意 -D 必须写在 -jar 之前，否则会被当成应用参数。
$javaArgs = @(
    '-Dsmartops.sciverse.base-url=https://api.sciverse.space',
    '-Dsmartops.sciverse.search-path=/agentic-search',
    '-Dsmartops.sciverse.content-path=/content',
    '-jar', $jar, '--spring.profiles.active=local', "--server.port=$Port"
)
$env:MYSQL_USERNAME = if ($cred['MYSQL_USERNAME']) { $cred['MYSQL_USERNAME'] } else { 'root' }
$env:MYSQL_PASSWORD = if ($cred['MYSQL_PASSWORD']) { $cred['MYSQL_PASSWORD'] } else { 'root' }
$proc = Start-Process -FilePath $java -ArgumentList $javaArgs -WorkingDirectory (Join-Path $repo 'backend') `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
Write-Host "[启动] PID $($proc.Id)，Java 17，local profile，端口 $Port" -ForegroundColor Green
Write-Host "[日志] $stdout"

# 5) 健康检查（最长 120 秒）
$ready = $false
foreach ($i in 1..40) {
    Start-Sleep -Seconds 3
    if ($proc.HasExited) {
        Write-Host "[失败] 进程已退出（exit $($proc.ExitCode)），日志尾部：" -ForegroundColor Red
        Get-Content $stdout -Tail 20 -ErrorAction SilentlyContinue
        Get-Content $stderr -Tail 20 -ErrorAction SilentlyContinue
        exit 1
    }
    try {
        $body = curl.exe -s -m 3 $healthUrl
        if ($body -match '"UP"') { $ready = $true; break }
    } catch { }
}
if ($ready) {
    Write-Host "[就绪] http://localhost:$Port 健康检查通过（耗时约 $($i * 3) 秒）" -ForegroundColor Green
} else {
    Write-Host "[超时] 120 秒未就绪，日志尾部（stdout/stderr）：" -ForegroundColor Red
    Get-Content $stdout -Tail 15 -ErrorAction SilentlyContinue
    Get-Content $stderr -Tail 15 -ErrorAction SilentlyContinue
    exit 1
}
