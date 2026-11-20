<#
.SYNOPSIS
    AI 能力链（本机 Ollama 运行时 + ai-service）启停控制。

.DESCRIPTION
    供 Java 后端 /api/runtime/ai/* 调用，统一在 stdout 输出单行 JSON。

    - status：只读探测，不改变任何状态
    - start ：启动 Ollama（仅本平台托管副本）与 ai-service，启动 ai-service 时
              从根 .env 注入 CHAT_RUN_TOKEN_SECRET，避免出现
              CHAT_RUN_TOKEN_NOT_CONFIGURED
    - stop  ：停止 ai-service；Ollama 只有在确认是 .runtime\mini\runtime\ollama.exe
              时才停止，外部安装的 Ollama 一律不碰

    退出码：0 成功；1 失败。

.PARAMETER Action
    status / start / stop

.PARAMETER TimeoutSec
    start 时等待 ai-service 就绪的上限秒数（torch 导入较慢，默认 150）。

.EXAMPLE
    .\ai-runtime-control.ps1 -Action status
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('status', 'start', 'stop')]
    [string]$Action,
    [int]$TimeoutSec = 150
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$managedOllama = Join-Path $root '.runtime\mini\runtime\ollama.exe'
$envFile = Join-Path $root '.env'
$aiWorkDir = Join-Path $root 'ai-service'
$logDir = Join-Path $root '.runtime\logs'

function Get-ListenerPid([int]$Port) {
    $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) { return [int]$conn.OwningProcess }
    return 0
}

function Get-ProcessInfo([int]$ProcId) {
    if (-not $ProcId) { return $null }
    Get-CimInstance Win32_Process -Filter "ProcessId=$ProcId" -ErrorAction SilentlyContinue
}

function Read-EnvFile {
    $map = @{}
    if (Test-Path -LiteralPath $envFile) {
        Get-Content -LiteralPath $envFile | ForEach-Object {
            if ($_ -match '^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$') { $map[$matches[1]] = $matches[2].Trim() }
        }
    }
    return $map
}

function Test-Health([string]$Url) {
    try { return Invoke-RestMethod $Url -TimeoutSec 2 } catch { return $null }
}

function Get-RuntimeState {
    $aiPid = Get-ListenerPid 8001
    $ollamaPid = Get-ListenerPid 11434
    $aiInfo = Get-ProcessInfo $aiPid
    $ollamaInfo = Get-ProcessInfo $ollamaPid

    # 只认命令行指纹匹配的 python + app.main:app，避免误判/误杀
    $aiManaged = [bool]($aiInfo -and $aiInfo.Name -like 'python*' -and $aiInfo.CommandLine -like '*app.main:app*')
    $ollamaManaged = [bool]($ollamaInfo -and $ollamaInfo.ExecutablePath -and
        [string]::Equals($ollamaInfo.ExecutablePath, $managedOllama, [StringComparison]::OrdinalIgnoreCase))

    $health = Test-Health 'http://127.0.0.1:8001/api/health'
    $tags = Test-Health 'http://127.0.0.1:11434/api/tags'
    $models = @()
    if ($tags -and $tags.models) { $models = @($tags.models | ForEach-Object { $_.name }) }

    $envMap = Read-EnvFile
    $secret = [string]$envMap['SMARTOPS_CHAT_RUN_TOKEN_SECRET']

    [pscustomobject]@{
        ollama = [pscustomobject]@{
            running    = [bool]$ollamaPid
            managed    = $ollamaManaged
            pid        = $(if ($ollamaPid) { $ollamaPid } else { 0 })
            models     = $models
            modelReady = [bool]($models -contains 'qwen3:1.7b')
        }
        aiService = [pscustomobject]@{
            running          = [bool]$aiPid
            managed          = $aiManaged
            pid              = $(if ($aiPid) { $aiPid } else { 0 })
            health           = $(if ($health) { [string]$health.status } else { 'DOWN' })
            version          = $(if ($health) { [string]$health.version } else { '' })
            secretConfigured = [bool]$secret
        }
        checkedAt = (Get-Date).ToString('o')
    }
}

function Start-OllamaIfNeeded {
    if (Get-ListenerPid 11434) { return 'already-running' }
    if (-not (Test-Path -LiteralPath $managedOllama)) {
        return 'missing: 11434 未监听，且未安装本平台托管运行时（.runtime\mini\runtime\ollama.exe）'
    }
    & (Join-Path $PSScriptRoot 'start-mini.ps1') | Out-Null
    if (-not (Get-ListenerPid 11434)) { throw 'Ollama 启动后仍未监听 11434' }
    return 'started'
}

function Start-AiServiceIfNeeded {
    $aiPid = Get-ListenerPid 8001
    if ($aiPid) {
        $info = Get-ProcessInfo $aiPid
        if ($info -and $info.Name -like 'python*' -and $info.CommandLine -like '*app.main:app*') { return 'already-running' }
        throw '端口 8001 被非本平台的进程占用，拒绝启动'
    }
    $envMap = Read-EnvFile
    $secret = [string]$envMap['SMARTOPS_CHAT_RUN_TOKEN_SECRET']
    if (-not $secret) {
        throw '根 .env 缺少 SMARTOPS_CHAT_RUN_TOKEN_SECRET，启动后聊天仍会被拒绝'
    }
    $python = (Get-Command python -ErrorAction SilentlyContinue)
    if (-not $python) { throw '未找到 python，请先把 Python 加入 PATH' }

    $env:CHAT_RUN_TOKEN_SECRET = $secret
    foreach ($key in @('LLM_PROVIDER', 'LLM_MODEL', 'LLM_BASE_URL', 'LLM_API_KEY',
            'KNOWLEDGE_SERVICE_URL', 'KNOWLEDGE_API_KEY', 'CHAT_ALLOW_ANONYMOUS')) {
        if ($envMap.ContainsKey($key) -and $envMap[$key]) { Set-Item -Path "Env:$key" -Value $envMap[$key] }
    }

    [System.IO.Directory]::CreateDirectory($logDir) | Out-Null
    Start-Process -FilePath $python.Source `
        -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8001') `
        -WorkingDirectory $aiWorkDir -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir 'ai-service.out.log') `
        -RedirectStandardError (Join-Path $logDir 'ai-service.err.log')

    for ($i = 0; $i -lt $TimeoutSec; $i++) {
        Start-Sleep -Seconds 1
        $health = Test-Health 'http://127.0.0.1:8001/api/health'
        if ($health -and $health.status -eq 'UP') { return 'started' }
    }
    throw "ai-service 在 $TimeoutSec 秒内未就绪，请查看 .runtime\logs\ai-service.err.log"
}

function Stop-AiServiceIfRunning {
    $aiPid = Get-ListenerPid 8001
    if (-not $aiPid) { return 'already-stopped' }
    $info = Get-ProcessInfo $aiPid
    if (-not $info -or $info.Name -notlike 'python*' -or $info.CommandLine -notlike '*app.main:app*') {
        throw '端口 8001 被非本平台的进程占用，拒绝停止'
    }
    Stop-Process -Id $aiPid -Force
    Wait-Process -Id $aiPid -Timeout 15 -ErrorAction SilentlyContinue
    return 'stopped'
}

function Stop-OllamaIfManaged {
    $ollamaPid = Get-ListenerPid 11434
    if (-not $ollamaPid) { return 'already-stopped' }
    $info = Get-ProcessInfo $ollamaPid
    if (-not $info -or -not $info.ExecutablePath -or
        -not [string]::Equals($info.ExecutablePath, $managedOllama, [StringComparison]::OrdinalIgnoreCase)) {
        return 'skipped: Ollama 由外部安装，本平台不停止它'
    }
    Stop-Process -Id $ollamaPid -Force
    Wait-Process -Id $ollamaPid -Timeout 15 -ErrorAction SilentlyContinue
    return 'stopped'
}

$notes = @()
$ok = $true
try {
    switch ($Action) {
        'status' { }
        'start' {
            $notes += "ollama: $(Start-OllamaIfNeeded)"
            $notes += "aiService: $(Start-AiServiceIfNeeded)"
        }
        'stop' {
            $notes += "aiService: $(Stop-AiServiceIfRunning)"
            $notes += "ollama: $(Stop-OllamaIfManaged)"
        }
    }
}
catch {
    $ok = $false
    $notes += "error: $($_.Exception.Message)"
}

$state = $null
try { $state = Get-RuntimeState } catch { }

[pscustomobject]@{
    ok      = $ok
    action  = $Action
    message = ($notes -join ' | ')
    state   = $state
} | ConvertTo-Json -Depth 8 -Compress

if ($ok) { exit 0 } else { exit 1 }
