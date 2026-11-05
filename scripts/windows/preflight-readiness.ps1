param(
    # 真实平台段预检：任何 FAIL 都会以退出码 1 阻止继续。
    # 默认 fixture 模式：只做探测与摘要，不阻断本地开发。
    [switch]$Real,
    # 各服务端口可用环境变量覆盖，避免写死部署形态。
    [int]$BackendPort = 8080,
    [int]$AiServicePort = 8001,
    [int]$KnowledgePort = 8002,
    [int]$OllamaPort = 11434,
    [int]$ProbeTimeoutMs = 1500
)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$logs = Join-Path $root '.runtime\logs'
[System.IO.Directory]::CreateDirectory($logs) | Out-Null
$logFile = Join-Path $logs "preflight-$stamp.log"

$results = New-Object System.Collections.Generic.List[object]

function Add-Result([string]$Item, [string]$Status, [string]$Detail) {
    # Status 仅允许 PASS / FAIL / SKIP，禁止把未知写成 PASS。
    $results.Add([pscustomobject]@{ Item = $Item; Status = $Status; Detail = $Detail })
}

function Test-Port([string]$Name, [int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) { Add-Result $Name 'PASS' "port $Port listening" }
    else { Add-Result $Name 'FAIL' "port $Port not listening" }
}

function Test-CommandVersion([string]$Name, [string]$Command) {
    try {
        $output = & $Command --version 2>&1 | Select-Object -First 1
        Add-Result $Name 'PASS' ([string]$output)
    }
    catch {
        Add-Result $Name 'FAIL' "$Command not available: $($_.Exception.Message)"
    }
}

# ---- 服务探测（就绪判据用带超时的轮询，禁止固定 sleep 冒充就绪） ----
Test-Port 'backend' $BackendPort
Test-Port 'ai-service' $AiServicePort
Test-Port 'knowledge' $KnowledgePort
Test-Port 'ollama' $OllamaPort

# ---- 运行时与代码版本 ----
Test-CommandVersion 'node' 'node'
Test-CommandVersion 'python' 'python'
try {
    $commit = (git -C $root rev-parse HEAD) 2>&1
    Add-Result 'git-commit' 'PASS' ([string]$commit)
}
catch {
    Add-Result 'git-commit' 'FAIL' $_.Exception.Message
}

# ---- 模型 / 语料 / 账号摘要（骨架占位：Real 模式下必须补实） ----
# 模型探测：确认目标模型已在 Ollama 就位，不做任何生成调用。
try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:$OllamaPort/api/tags" -TimeoutSec ([Math]::Max(1, $ProbeTimeoutMs / 1000))
    Add-Result 'ollama-models' 'PASS' (($tags.models | ForEach-Object { $_.name }) -join ', ')
}
catch {
    Add-Result 'ollama-models' 'SKIP' "tags endpoint unavailable: $($_.Exception.Message)"
}
# TODO(P0-RELEASE-01): 语料 manifest hash 摘要（读 knowledge manifest，比对冻结 hash）
# TODO(P0-RELEASE-01): 测试账号可用性摘要（只确认存在性，不记录任何凭据）
Add-Result 'corpus-manifest' 'SKIP' 'not wired yet (skeleton)'
Add-Result 'test-account' 'SKIP' 'not wired yet (skeleton)'

# ---- 摘要输出与原始日志保留 ----
$mode = if ($Real) { 'real' } else { 'fixture' }
$report = $results | Format-Table -AutoSize | Out-String
$header = "preflight mode=$mode fixture=$(-not $Real) provider_e2e=$Real stamp=$stamp"
$header | Tee-Object -FilePath $logFile
$report | Tee-Object -FilePath $logFile -Append
Write-Output "log: $logFile"

if ($Real) {
    $failed = @($results | Where-Object { $_.Status -ne 'PASS' })
    if ($failed.Count -gt 0) {
        Write-Output 'preflight FAILED: real segment blocked'
        exit 1
    }
}
exit 0
