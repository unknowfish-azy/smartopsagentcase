<#
  一次性安装环境：装 Python 依赖、前端依赖、生成 .env、建数据库。
  用法：
    2-安装环境.bat                 # 标准安装（含语义检索依赖，下载量较大）
    2-安装环境.bat -Lite           # 轻量安装（跳过 sentence-transformers/torch，知识库自动降级为 hash 向量）
    2-安装环境.bat -MysqlRootPassword 你的密码
    2-安装环境.bat -ReinstallNpm    # 强制重装前端依赖
#>
param(
    [switch]$Lite,
    [switch]$ReinstallNpm,
    [switch]$SkipDb,
    [string]$MysqlRootPassword = '',
    [string]$AdminPassword = ''
)

. (Join-Path $PSScriptRoot '_common.ps1')
Clear-ProxyVars

Write-Head 'SmartOpsAgent 环境安装（只需跑一次）'
Write-Host "包目录：$script:Root"
Write-Blank

# ── 0. 依赖体检，缺什么直接说清楚 ────────────────────────────────────
Write-Step '检查必需组件'
$missing = @()

$node = Get-CommandPath 'node'
$npm = Get-CommandPath 'npm'
$nodeMajor = 0
if ($node) { $v = (& $node -v 2>&1 | Out-String).Trim(); if ($v -match 'v(\d+)') { $nodeMajor = [int]$matches[1] } }
if (-not $node -or $nodeMajor -lt 18) { $missing += 'Node.js >= 18  (winget install OpenJS.NodeJS.LTS)' }

$py = Find-Python
if (-not $py) { $missing += 'Python >= 3.11  (winget install Python.Python.3.12)' }
elseif ([int]($py.Version.Split('.')[1]) -ge 13) {
    Write-Warn "Python $($py.Version) 版本偏新：部分依赖（httptools / pytesseract 等）可能还没有预编译包，建议装 3.12"
}

$java = Find-Java
if (-not $java) { $missing += 'JDK 17  (winget install EclipseAdoptium.Temurin.17.JDK)' }
else { $env:JAVA_HOME = (Split-Path -Parent (Split-Path -Parent $java)); Write-Ok "JDK: $java" }

if ($missing.Count -gt 0) {
    Write-Fail '缺少以下组件，先装好再回来：'
    $missing | ForEach-Object { Write-Host "   - $_" -ForegroundColor Yellow }
    Write-Blank
    Write-Host '装完请关掉本窗口重新打开（PATH 才会刷新）。' -ForegroundColor Gray
    Write-Host '按任意键关闭...' -ForegroundColor DarkGray
    if (-not $env:SMARTOPS_NO_PAUSE) { $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown') }
    exit 1
}
Write-Ok "Node.js $(& $node -v)  /  Python $($py.Version)"

# ── 1. 生成 .env ─────────────────────────────────────────────────────
Write-Step '准备 .env 配置'
$envPath = Get-DotEnvPath
$envExists = Test-Path -LiteralPath $envPath
if (-not $envExists) {
    $example = Join-Path $script:Root '.env.example'
    if (-not (Test-Path -LiteralPath $example)) { Write-Fail '找不到 .env.example，包不完整'; exit 1 }
    Copy-Item -LiteralPath $example -Destination $envPath -Force
    Write-Ok '已从 .env.example 生成 .env'
} else {
    Write-Ok '.env 已存在，仅补全缺失项（不覆盖你改过的值）'
}

$envMap = Read-DotEnv

# 随机密钥：缺失才生成，已有就保留，重复安装不会把已跑通的环境改坏
function Ensure-Secret([string]$Key, [scriptblock]$Generator) {
    $cur = (Read-DotEnv)[$Key]
    if ([string]::IsNullOrWhiteSpace($cur)) {
        $val = & $Generator
        Set-DotEnvValue -Path $envPath -Key $Key -Value $val
        Write-Ok "生成 $Key"
    }
}

Ensure-Secret 'SMARTOPS_CHAT_RUN_TOKEN_SECRET' { New-RandomHex 24 }
Ensure-Secret 'CHAT_RUN_TOKEN_SECRET' { (Read-DotEnv)['SMARTOPS_CHAT_RUN_TOKEN_SECRET'] }
Ensure-Secret 'SMARTOPS_INTERNAL_TOKEN' { New-RandomHex 24 }
Ensure-Secret 'KNOWLEDGE_API_KEY' { New-RandomHex 24 }
Ensure-Secret 'SMARTOPS_API_KEY_ENCRYPTION_KEY' { New-RandomBase64Key 32 }

$envMap = Read-DotEnv
if ([string]::IsNullOrWhiteSpace($envMap['SMARTOPS_BOOTSTRAP_USERNAME'])) {
    Set-DotEnvValue -Path $envPath -Key 'SMARTOPS_BOOTSTRAP_USERNAME' -Value 'admin'
}
if ($AdminPassword) {
    Set-DotEnvValue -Path $envPath -Key 'SMARTOPS_BOOTSTRAP_PASSWORD' -Value $AdminPassword
} elseif ([string]::IsNullOrWhiteSpace($envMap['SMARTOPS_BOOTSTRAP_PASSWORD'])) {
    $AdminPassword = 'Ops@' + (New-RandomHex 5)
    Set-DotEnvValue -Path $envPath -Key 'SMARTOPS_BOOTSTRAP_PASSWORD' -Value $AdminPassword
}

if ($MysqlRootPassword) {
    Set-DotEnvValue -Path $envPath -Key 'MYSQL_PASSWORD' -Value $MysqlRootPassword
    Set-DotEnvValue -Path $envPath -Key 'SMARTOPS_MYSQL_PASSWORD' -Value $MysqlRootPassword
    Write-Ok '已写入你提供的 MySQL 口令'
} else {
    $envMap = Read-DotEnv
    if ([string]::IsNullOrWhiteSpace($envMap['MYSQL_PASSWORD'])) {
        Set-DotEnvValue -Path $envPath -Key 'MYSQL_PASSWORD' -Value 'root'
        Set-DotEnvValue -Path $envPath -Key 'SMARTOPS_MYSQL_PASSWORD' -Value 'root'
        Write-Warn 'MySQL 口令默认按 root 处理；如果你的 root 口令不同，重跑：2-安装环境.bat -MysqlRootPassword 你的口令'
    }
}

# 轻量模式明确走 hash 向量，避免每次启动都在等模型加载
if ($Lite) {
    Set-DotEnvValue -Path $envPath -Key 'KNOWLEDGE_EMBEDDING_BACKEND' -Value 'hash'
    Write-Ok '轻量模式：知识库使用 hash 向量（零下载，语义能力降级）'
}

# ── 2. 数据库 ────────────────────────────────────────────────────────
if (-not $SkipDb) {
    Write-Step '准备 MySQL 数据库 smartops'
    if (-not (Test-Port 3306)) {
        $svc = Get-Service -Name 'MySQL*' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($svc) {
            Write-Step "MySQL 未运行，尝试启动服务 $($svc.Name)"
            try { Start-Service -Name $svc.Name -ErrorAction Stop; Start-Sleep -Seconds 4 } catch { Write-Warn "启动失败：$($_.Exception.Message)" }
        }
    }
    if (-not (Test-Port 3306)) {
        Write-Warn 'MySQL 3306 未监听，跳过建库。装好 MySQL 后重跑本脚本，或用客户端手工执行：'
        Write-Host '   CREATE DATABASE IF NOT EXISTS smartops DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;' -ForegroundColor Gray
    } else {
        $mysql = Find-MySqlClient
        $envMap = Read-DotEnv
        $dbPwd = $envMap['MYSQL_PASSWORD']
        if (-not $mysql) {
            Write-Warn '找不到 mysql 命令行客户端（只装了服务端也会这样）。请用 Navicat / DBeaver 手工执行：'
            Write-Host '   CREATE DATABASE IF NOT EXISTS smartops DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;' -ForegroundColor Gray
            Write-Host '   建表脚本：backend\src\main\resources\db\local-schema.sql（后端启动时 Flyway 也会自动建表）' -ForegroundColor Gray
        } else {
            $sql = 'CREATE DATABASE IF NOT EXISTS smartops DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;'
            $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
            if ([string]::IsNullOrWhiteSpace($dbPwd)) {
                $out = & $mysql -h 127.0.0.1 -P 3306 -u root -e $sql 2>&1 | Out-String
            } else {
                $out = & $mysql -h 127.0.0.1 -P 3306 -u root "-p$dbPwd" -e $sql 2>&1 | Out-String
            }
            $code = $LASTEXITCODE
            $ErrorActionPreference = $prev
            if ($code -eq 0) { Write-Ok '数据库 smartops 已就绪（表结构由后端启动时自动迁移）' }
            else {
                Write-Warn '建库失败，输出如下：'
                Write-Host ($out.Trim()) -ForegroundColor DarkGray
                Write-Warn '常见原因：MySQL 口令不对 / MySQL 未启动。可用 -MysqlRootPassword 指定口令后重跑。'
            }
        }
    }
}

# ── 3. Python 依赖 ───────────────────────────────────────────────────
Write-Step '安装 Python 依赖（AI 服务 + 知识服务）'
Write-Host '  提示：首次安装需要联网，标准模式会下载 torch 等大包（约 2-3 GB，视网速 5-20 分钟）' -ForegroundColor Gray

$ErrorActionPreference = 'Continue'
& $py.Path -m pip install --upgrade pip --disable-pip-version-check -q
& $py.Path -m pip install -r (Join-Path $script:Root 'ai-service\requirements.txt') --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    Write-Warn 'AI 服务依赖安装失败。常见原因：① 网络问题（换镜像）② Python 版本太新没有预编译包（推荐 3.12）'
    Write-Host '   python -m pip install -r ai-service\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple' -ForegroundColor Gray
}

if ($Lite) {
    & $py.Path -m pip install "numpy>=1.26,<3" "pypdf>=5.0,<7" --disable-pip-version-check
} else {
    & $py.Path -m pip install -r (Join-Path $script:Root 'knowledge\requirements.txt') --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) {
        Write-Warn '语义检索依赖安装失败，自动退回到轻量依赖（hash 向量仍可跑）'
        & $py.Path -m pip install "numpy>=1.26,<3" "pypdf>=5.0,<7" --disable-pip-version-check
        Set-DotEnvValue -Path $envPath -Key 'KNOWLEDGE_EMBEDDING_BACKEND' -Value 'hash'
    }
}
$ErrorActionPreference = 'Stop'

$prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
$check = & $py.Path -c "import fastapi, uvicorn, numpy; print('deps-ok')" 2>&1 | Out-String
$ErrorActionPreference = $prev
if ($check -match 'deps-ok') { Write-Ok 'Python 依赖就绪' } else { Write-Fail 'Python 依赖仍不完整，请查看上面的报错' }

# ── 4. 前端依赖 ──────────────────────────────────────────────────────
$nodeModules = Join-Path $script:Root 'frontend\node_modules'
if ((Test-Path -LiteralPath $nodeModules) -and -not $ReinstallNpm) {
    Write-Ok '前端依赖已随包内置（node_modules 存在），跳过 npm install'
    Write-Host '  若启动时前端报错，运行：2-安装环境.bat -ReinstallNpm' -ForegroundColor Gray
} else {
    Write-Step '安装前端依赖（npm install）'
    Push-Location (Join-Path $script:Root 'frontend')
    try {
        & $npm install --no-audit --no-fund
        if ($LASTEXITCODE -eq 0) { Write-Ok '前端依赖安装完成' }
        else {
            Write-Warn 'npm install 失败，换国内镜像重试：'
            Write-Host '   npm config set registry https://registry.npmmirror.com' -ForegroundColor Gray
            Write-Host '   cd frontend && npm install' -ForegroundColor Gray
        }
    } finally { Pop-Location }
}

# ── 5. 后端 jar ──────────────────────────────────────────────────────
$jar = Join-Path $script:Root 'backend\target\smartops-backend-0.0.1-SNAPSHOT.jar'
if (Test-Path -LiteralPath $jar) {
    Write-Ok '后端 jar 已内置，运行时不依赖 Maven'
} else {
    $mvn = Get-CommandPath 'mvn'
    if ($mvn) {
        Write-Step '打包后端（mvn package，首次会下载依赖）'
        Push-Location (Join-Path $script:Root 'backend')
        try { & $mvn -DskipTests package } finally { Pop-Location }
    } else {
        Write-Warn '后端 jar 缺失且没有 Maven：请安装 Maven 或向提供者索取 target 下的 jar'
    }
}

# ── 6. 汇总 ──────────────────────────────────────────────────────────
$envMap = Read-DotEnv
Write-Head '安装完成'
Write-Blank
Write-Host '  管理员账号（首次登录用，改 .env 里的 SMARTOPS_BOOTSTRAP_PASSWORD 可改）' -ForegroundColor White
Write-Host ("    用户名：{0}" -f $envMap['SMARTOPS_BOOTSTRAP_USERNAME'])
Write-Host ("    密  码：{0}" -f $envMap['SMARTOPS_BOOTSTRAP_PASSWORD']) -ForegroundColor Yellow
Write-Blank
Write-Host '  MySQL 口令已写入 .env 的 MYSQL_PASSWORD（默认 root，可在 .env 里改）'
Write-Host '  密钥（聊天令牌 / 知识库 API Key / 加密 Key）已随机生成，只存在本机 .env 里'
Write-Blank
Write-Ok '下一步：双击 3-启动平台.bat'
Write-Blank
Write-Host '按任意键关闭...' -ForegroundColor DarkGray
if (-not $env:SMARTOPS_NO_PAUSE) { $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown') }
