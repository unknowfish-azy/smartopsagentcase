$ErrorActionPreference = 'Stop'

# Some Windows shells expose both Path and PATH; Start-Process rejects that environment.
$processPath = [Environment]::GetEnvironmentVariable('Path')
Remove-Item Env:PATH -ErrorAction SilentlyContinue
[Environment]::SetEnvironmentVariable('Path', $processPath)

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runtimeRoot = Join-Path $projectRoot 'data\local\observability'
$logRoot = Join-Path $runtimeRoot 'logs'
$dataRoot = Join-Path $runtimeRoot 'data'
New-Item -ItemType Directory -Force $logRoot, $dataRoot | Out-Null

function Wait-Ready {
    param([string]$Name, [string]$Url, [System.Diagnostics.Process]$Process)
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($Process.HasExited) {
            throw "$Name exited before becoming ready. Check $logRoot."
        }
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return }
        } catch { Start-Sleep -Seconds 1 }
    }
    throw "$Name did not become ready at $Url. Check $logRoot."
}

function Start-LocalService {
    param([string]$Name, [string]$Executable, [string[]]$Arguments, [string]$ReadyUrl)
    if (-not (Test-Path -LiteralPath $Executable)) {
        throw "Missing $Name executable: $Executable. See docs/OBSERVABILITY_SETUP.md."
    }
    try {
        $response = Invoke-WebRequest -Uri $ReadyUrl -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            Write-Output "$Name already ready at $ReadyUrl"
            return
        }
    } catch { }
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot "$Name.stdout.log") -RedirectStandardError (Join-Path $logRoot "$Name.stderr.log") -PassThru
    Wait-Ready -Name $Name -Url $ReadyUrl -Process $process
    Write-Output "$Name ready at $ReadyUrl (PID $($process.Id))"
}

$prometheus = Join-Path $runtimeRoot 'bin\prometheus-3.5.0.windows-amd64\prometheus.exe'
$loki = Join-Path $runtimeRoot 'bin\loki-windows-amd64.exe'
$promtail = Join-Path $runtimeRoot 'bin\promtail-windows-amd64.exe'
$windowsExporter = Join-Path $runtimeRoot 'bin\windows_exporter-0.31.8-amd64.exe'
$prometheusConfig = Join-Path $projectRoot 'infrastructure\observability\windows\prometheus.yml'
$lokiConfig = Join-Path $projectRoot 'infrastructure\observability\windows\loki.yml'
$promtailConfig = Join-Path $runtimeRoot 'promtail.yml'
$positions = (Join-Path $dataRoot 'promtail-positions.yml').Replace('\', '/')
$backendLogs = (Join-Path $logRoot 'backend.log').Replace('\', '/')

@"
server:
  http_listen_address: 127.0.0.1
  http_listen_port: 9081
  grpc_listen_port: 0
positions:
  filename: '$positions'
clients:
  - url: http://127.0.0.1:3100/loki/api/v1/push
scrape_configs:
  - job_name: smartops-backend
    pipeline_stages:
      - drop:
          expression: 'Using generated security password:'
    static_configs:
      - targets: [localhost]
        labels:
          job: smartops-backend
          __path__: '$backendLogs'
"@ | Set-Content -LiteralPath $promtailConfig -Encoding UTF8

Start-LocalService -Name 'windows-exporter' -Executable $windowsExporter -Arguments @('--web.listen-address=127.0.0.1:9182', '--collectors.enabled=cpu,memory,logical_disk,net,os,system') -ReadyUrl 'http://127.0.0.1:9182/metrics'
Start-LocalService -Name 'prometheus' -Executable $prometheus -Arguments @("--config.file=$prometheusConfig", "--storage.tsdb.path=$(Join-Path $dataRoot 'prometheus')", '--web.listen-address=127.0.0.1:9090') -ReadyUrl 'http://127.0.0.1:9090/-/ready'
Start-LocalService -Name 'loki' -Executable $loki -Arguments @("-config.file=$lokiConfig") -ReadyUrl 'http://127.0.0.1:3100/ready'
Start-LocalService -Name 'promtail' -Executable $promtail -Arguments @("-config.file=$promtailConfig") -ReadyUrl 'http://127.0.0.1:9081/metrics'

Write-Output 'Set SMARTOPS_PROMETHEUS_URL=http://127.0.0.1:9090 and SMARTOPS_LOKI_URL=http://127.0.0.1:3100 in the backend process environment, then restart the backend.'
