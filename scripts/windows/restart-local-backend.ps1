param([string]$Java = "$env:USERPROFILE\scoop\apps\openjdk17\current\bin\java.exe")

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$backend = Join-Path $root 'backend'
$jar = Join-Path $backend 'target\smartops-backend-0.0.1-SNAPSHOT.jar'
if (!(Test-Path -LiteralPath $jar)) { throw 'Build the backend jar before restarting' }
if (!(Test-Path -LiteralPath $Java)) { throw 'Java 17 executable not found' }
if (Test-Path -LiteralPath (Join-Path $root '.runtime\mini\runtime\ollama.exe')) { & (Join-Path $PSScriptRoot 'start-mini.ps1') }
$credentialFile = Join-Path $root '.runtime\secrets\bootstrap.env'
if (!(Test-Path -LiteralPath $credentialFile)) { throw 'Create a private bootstrap environment before first startup' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$runtimeDirectory = Join-Path $root '.runtime\backend'
[System.IO.Directory]::CreateDirectory($runtimeDirectory) | Out-Null
$runtimeJar = Join-Path $runtimeDirectory "smartops-backend-$stamp.jar"
Copy-Item -LiteralPath $jar -Destination $runtimeJar
$previous = @{}
try {
    foreach ($file in @((Join-Path $root '.env'), $credentialFile)) {
        Get-Content -LiteralPath $file -Encoding UTF8 | ForEach-Object {
            if ($_ -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
                $name = $matches[1]
                if (!$previous.ContainsKey($name)) { $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
                [Environment]::SetEnvironmentVariable($name, $matches[2].Trim().Trim('"').Trim("'"), 'Process')
            }
        }
    }
    $listeners = @(Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($listener in $listeners) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$listener"
        if (!$process -or $process.Name -ne 'java.exe' -or ($process.CommandLine -notmatch [regex]::Escape($backend) -and $process.CommandLine -notmatch [regex]::Escape($runtimeDirectory) -and $process.CommandLine -notmatch 'com\.smartops\.SmartOpsApplication')) { throw 'Port 8080 belongs to another application; refusing to stop it' }
        Stop-Process -Id $listener -Force
        Wait-Process -Id $listener -Timeout 20 -ErrorAction SilentlyContinue
    }
    $logs = Join-Path $root '.runtime\logs'
    [System.IO.Directory]::CreateDirectory($logs) | Out-Null
    $process = Start-Process -FilePath $Java -ArgumentList @('-Dfile.encoding=UTF-8', '-jar', "`"$runtimeJar`"", '--server.address=127.0.0.1', '--smartops.security.internal-bypass=false') -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs "backend-secure-$stamp.out.log") -RedirectStandardError (Join-Path $logs "backend-secure-$stamp.err.log")
    Write-Output "Backend launched: PID $($process.Id), logs .runtime/logs/backend-secure-$stamp.*.log"
} finally {
    foreach ($name in $previous.Keys) { [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process') }
}
