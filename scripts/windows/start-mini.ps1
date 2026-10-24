param([switch]$Restart)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$directory = Join-Path $root '.runtime\mini'
$executable = Join-Path $directory 'runtime\ollama.exe'
if (!(Test-Path -LiteralPath $executable)) { throw 'Install the approved local inference runtime before starting Mini' }
$executable = (Resolve-Path -LiteralPath $executable).Path
$listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object LocalPort -eq 11434)
foreach ($listener in $listeners) {
    if ($listener.LocalAddress -notin @('127.0.0.1', '::1')) { throw 'Port 11434 is not bound to loopback; refusing to reuse it' }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    if (!$process -or ![string]::Equals($process.ExecutablePath, $executable, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Port 11434 belongs to another application; refusing to stop it'
    }
}
if ($listeners.Count -gt 0 -and !$Restart) {
    Write-Output 'Mini inference runtime is already running on 127.0.0.1:11434'
    return
}
foreach ($listener in $listeners | Sort-Object OwningProcess -Unique) {
    Stop-Process -Id $listener.OwningProcess -Force
    Wait-Process -Id $listener.OwningProcess -Timeout 20 -ErrorAction SilentlyContinue
}
$settings = @{
    OLLAMA_HOST = '127.0.0.1:11434'
    OLLAMA_MODELS = (Join-Path $directory 'models')
    OLLAMA_NO_CLOUD = '1'
    OLLAMA_NUM_PARALLEL = '1'
    OLLAMA_MAX_LOADED_MODELS = '1'
    OLLAMA_CONTEXT_LENGTH = '8192'
}
$previous = @{}
try {
    foreach ($name in $settings.Keys) {
        $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $settings[$name], 'Process')
    }
    $logs = Join-Path $directory 'logs'
    [System.IO.Directory]::CreateDirectory($logs) | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $process = Start-Process -FilePath $executable -ArgumentList 'serve' -WorkingDirectory (Split-Path $executable) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs "server-$stamp.out.log") -RedirectStandardError (Join-Path $logs "server-$stamp.err.log")
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($process.HasExited) { throw 'Mini runtime exited during startup; inspect the private runtime log' }
        try {
            $tags = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2
            $ready = $true
            break
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (!$ready) { throw 'Mini runtime did not become ready' }
    if (!($tags.models | Where-Object name -eq 'qwen3:1.7b')) { Write-Warning 'Runtime ready, but qwen3:1.7b is not installed; Mini will show model_missing until downloaded' }
    Write-Output "Mini inference ready: PID $($process.Id), local-only port 11434"
} finally {
    foreach ($name in $previous.Keys) { [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process') }
}
