# SmartOpsAgent Windows development startup (PowerShell 5.1 compatible)
[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [switch]$SkipDependencies,
    [int]$StartupTimeoutSeconds = 120,
    [int]$PollIntervalSeconds = 2
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'service-readiness.ps1')

function Test-TcpPort {
    param([string]$HostName, [int]$Port, [int]$TimeoutMilliseconds = 1000)

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMilliseconds, $false)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Wait-TcpPort {
    param([string]$ServiceName, [int]$Port)

    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    Write-Host ("[WAIT] {0} port {1} (timeout {2}s)..." -f $ServiceName, $Port, $StartupTimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPort -HostName '127.0.0.1' -Port $Port) {
            Write-Host ("[OK]   {0} is listening on {1}" -f $ServiceName, $Port)
            return
        }
        Start-Sleep -Seconds $PollIntervalSeconds
    }
    throw ("Timed out waiting for {0} on port {1}. Check the service window and logs." -f $ServiceName, $Port)
}

function Ensure-Ollama {
    $ollamaUrl = 'http://127.0.0.1:11434'
    Write-Host '[CHECK] Ollama (11434)'
    if (-not (Test-TcpPort -HostName '127.0.0.1' -Port 11434)) {
        $ollama = Get-Command 'ollama' -ErrorAction SilentlyContinue
        if (-not $ollama) {
            throw 'Ollama is not listening on 11434 and ollama.exe was not found on PATH.'
        }
        Write-Host '[START] Ollama serve'
        Start-Process -FilePath $ollama.Source -ArgumentList @('serve') -WindowStyle Hidden | Out-Null
    }

    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $tags = Invoke-RestMethod -Uri ($ollamaUrl + '/api/tags') -Method Get -TimeoutSec 3
            if ($null -ne $tags) {
                Write-Host '[OK]   Ollama API is ready on 11434'
                return
            }
        }
        catch {
            # The process may be listening before the HTTP API is ready.
        }
        Start-Sleep -Seconds $PollIntervalSeconds
    }
    throw 'Timed out waiting for Ollama API /api/tags on port 11434.'
}

function Start-CommandWindow {
    param([string]$Name, [string]$WorkingDirectory, [string]$Command, [int]$Port)

    if (-not (Test-Path -LiteralPath $WorkingDirectory -PathType Container)) {
        throw ("{0} directory not found: {1}" -f $Name, $WorkingDirectory)
    }
    if ($Port -gt 0 -and (Test-TcpPort -HostName '127.0.0.1' -Port $Port)) {
        Write-Host ("[CHECK] {0}: existing listener on {1}; verifying readiness instead of starting a duplicate" -f $Name, $Port)
        return
    }
    $logDirectory = Join-Path $ProjectRoot '.runtime\launcher-logs'
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $logName = ($Name -replace '[^a-zA-Z0-9_-]', '-') + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')
    $stdout = Join-Path $logDirectory ($logName + '.stdout.log')
    $stderr = Join-Path $logDirectory ($logName + '.stderr.log')
    Write-Host ("[START] {0}; logs: {1}" -f $Name, $stdout)
    Start-Process -FilePath 'cmd.exe' -WorkingDirectory $WorkingDirectory `
        -ArgumentList @('/c', $Command) -WindowStyle Hidden `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr | Out-Null
}

$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$frontendDir = Join-Path $ProjectRoot 'frontend'
$backendDir = Join-Path $ProjectRoot 'backend'
$aiServiceDir = Join-Path $ProjectRoot 'ai-service'

function Import-ProjectEnvironment {
    param([Parameter(Mandatory = $true)][string]$Root)

    $envFile = Join-Path $Root '.env'
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
        Write-Host ("[OK]   project environment loaded from {0}" -f $envFile)
    }

    $jdkCandidates = @(
        (Join-Path $env:USERPROFILE 'scoop\apps\openjdk17\current'),
        (Join-Path $env:ProgramFiles 'Java\jdk-17')
    )
    $jdk = $jdkCandidates | Where-Object { Test-Path -LiteralPath (Join-Path $_ 'bin\java.exe') } | Select-Object -First 1
    if ($jdk) {
        $env:JAVA_HOME = $jdk
        $env:Path = (Join-Path $jdk 'bin') + ';' + $env:Path
        Write-Host ("[OK]   Java 17 selected: {0}" -f $jdk)
    }
}

Import-ProjectEnvironment -Root $ProjectRoot

try {
    if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
        throw ("Project root not found: {0}" -f $ProjectRoot)
    }

    Ensure-Ollama

    if (-not $SkipDependencies) {
        $dockerDir = Join-Path $ProjectRoot 'deploy\docker'
        if (Test-Path -LiteralPath $dockerDir -PathType Container) {
            if (Get-Command docker -ErrorAction SilentlyContinue) {
                Write-Host '[START] Docker dependencies (MySQL / Redis)'
                Start-Process -FilePath 'cmd.exe' -WorkingDirectory $dockerDir `
                    -ArgumentList @('/c', 'docker compose up -d') -WindowStyle Hidden | Out-Null
            }
            else {
                Write-Warning 'docker was not found; continuing without dependency containers.'
            }
        }
    }
    else {
        Write-Host '[SKIP] Docker dependencies'
    }

    Start-CommandWindow -Name 'Frontend user (5173)' -WorkingDirectory $frontendDir -Port 5173 `
        -Command 'set "NODE_OPTIONS=--max-old-space-size=512" && npm run dev -- --host 0.0.0.0 --port 5173'
    Wait-TcpPort -ServiceName 'Frontend user' -Port 5173

    Start-CommandWindow -Name 'Frontend admin (5174)' -WorkingDirectory $frontendDir -Port 5174 `
        -Command 'set "NODE_OPTIONS=--max-old-space-size=512" && npm run dev:admin -- --host 0.0.0.0 --port 5174'
    Wait-TcpPort -ServiceName 'Frontend admin' -Port 5174

    Start-CommandWindow -Name 'Backend (8080)' -WorkingDirectory $backendDir -Port 8080 `
        -Command 'mvn -s .mvn\smartops-settings.xml -q -DskipTests package && java -Xms64m -Xmx512m -XX:MaxMetaspaceSize=192m -XX:ReservedCodeCacheSize=96m -XX:MaxDirectMemorySize=128m -XX:+UseSerialGC -XX:+ExitOnOutOfMemoryError -Dfile.encoding=UTF-8 -jar target\smartops-backend-0.0.1-SNAPSHOT.jar'
    Wait-ServiceReadiness -ServiceName 'Backend' -Uri 'http://127.0.0.1:8080/actuator/health' -TimeoutSeconds $StartupTimeoutSeconds -PollSeconds $PollIntervalSeconds

    Start-CommandWindow -Name 'AI service (8001)' -WorkingDirectory $aiServiceDir -Port 8001 `
        -Command 'python -m uvicorn app.main:app --host 0.0.0.0 --port 8001'
    Wait-ServiceReadiness -ServiceName 'AI service' -Uri 'http://127.0.0.1:8001/api/health' -ExpectedService 'smartops-ai-service' -TimeoutSeconds $StartupTimeoutSeconds -PollSeconds $PollIntervalSeconds

    # 开发态加 --reload（只监听 knowledge/ 下的 .py）：改代码后自动换 worker，
    # 父进程不退出，不用再手工重启；生产部署不要开这个开关。
    Start-CommandWindow -Name 'Knowledge service (8002)' -WorkingDirectory $ProjectRoot -Port 8002 `
        -Command 'python -m uvicorn knowledge.server:app --host 0.0.0.0 --port 8002 --reload --reload-dir knowledge'
    Wait-ServiceReadiness -ServiceName 'Knowledge service' -Uri 'http://127.0.0.1:8002/api/ready' -ExpectedService 'smartops-knowledge-service' -RequireIndex -TimeoutSeconds $StartupTimeoutSeconds -PollSeconds $PollIntervalSeconds

    Write-Host ''
    Write-Host '============================================'
    Write-Host ' SmartOpsAgent services are ready (OK)'
    Write-Host '============================================'
    Write-Host 'Frontend user    : http://localhost:5173'
    Write-Host 'Frontend admin   : http://localhost:5174'
    Write-Host 'Backend          : http://localhost:8080'
    Write-Host 'AI service       : http://localhost:8001'
    Write-Host 'Knowledge        : http://localhost:8002'
    exit 0
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
