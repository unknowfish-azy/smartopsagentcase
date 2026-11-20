# .SYNOPSIS
# SmartOpsAgent 桌面手 SSH 反向隧道——被控端起、被控端验。
#
# .DESCRIPTION
# 按 ARCHITECTURE 3.5 部署形态：每台 Windows 被控端各建一条 ssh -R，
# driver 只绑被控端 loopback 9222，云端 agent 去碰 127.0.0.1:192XX。
# 本脚本只做本机动作：前置检查 -> 起隧道 -> 远端验证 -> 状态/清理。
# 云端 sshd 配置 (allowtcpforwarding/gatewayports) 由运维在起隧道前确认。
#
# 端口规划：云端监听 19200 + machine_index，每台机器固定一个 index。
# 注册表放 docs/desktop_hand/machine_ports.csv。
# 禁止动态抢端口——端口冲突会让两台机器互相覆盖 driver。
#
# .PARAMETER MachineIndex
# 0 基索引。云端端口 = 19200 + MachineIndex。默认 0。
#
# .PARAMETER CloudHost
# 阿里云主机名或 IP。必填。
#
# .PARAMETER CloudUser
# SSH 登录云端的用户。必填。
#
# .PARAMETER CloudPort
# SSH 端口。默认 22。
#
# .PARAMETER DriverLocalPort
# 被控端 driver 绑定端口。默认 9222（与 driver_service.py 一致）。
#
# .PARAMETER Action
# start / status / stop / probe。默认 start。
#
# .EXAMPLE
# .\desktop_hand_tunnel.ps1 -Action probe -CloudHost aliyun-a.example.com -CloudUser ops
# .\desktop_hand_tunnel.ps1 -Action start -MachineIndex 3 -CloudHost aliyun-a.example.com -CloudUser ops

param(
    [ValidateRange(0, 999)]
    [int]$MachineIndex = 0,

    [Parameter(Mandatory = $true)]
    [string]$CloudHost,

    [Parameter(Mandatory = $true)]
    [string]$CloudUser,

    [int]$CloudPort = 22,

    [int]$DriverLocalPort = 9222,

    [ValidateSet("start", "status", "stop", "probe")]
    [string]$Action = "start"
)

# 注意：脚本级 $ErrorActionPreference 不设 Stop。
# 原因：ssh.exe 把版本号 / 某些状态信息写到 stderr，Stop 会把它们当 NativeCommandError 终止脚本。
# 需要严格检查的地方（Test-NetConnection 等）内部自己 try/catch。
$ErrorActionPreference = 'Continue'

$RemotePort = 19200 + $MachineIndex
# 所有含 host:port / user@host / 远端命令的拼接一律用单引号格式串 + -f，
# 避免 PowerShell 把 @{...} 当 hash literal、把 $var:port 当 namespace 分隔符。
$ForwardSpec = '127.0.0.1:{0}:127.0.0.1:{1}' -f $RemotePort, $DriverLocalPort
$DriverHealth = 'http://127.0.0.1:{0}/health' -f $DriverLocalPort
$TunnelLog = Join-Path $env:TEMP ('smartops-tunnel-mid{0}.log' -f $MachineIndex)

function Write-Step([string]$Message) {
    Write-Host "  $Message" -ForegroundColor DarkCyan
}
function Write-Ok([string]$Message) {
    Write-Host "  OK  $Message" -ForegroundColor Green
}
function Write-Fail([string]$Message) {
    Write-Host "  FAIL $Message" -ForegroundColor Red
}
function Write-Warn([string]$Message) {
    Write-Host "  WARN $Message" -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# 前置检查
# ---------------------------------------------------------------------------

function Test-Preflight {
    Write-Host ''
    Write-Host ('== Preflight (index={0}, cloud port={1}) ==' -f $MachineIndex, $RemotePort) -ForegroundColor Cyan

    if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
        Write-Fail 'ssh not found -- install OpenSSH Client (Windows Optional Feature) or Git for Windows'
        return $false
    }
    # ssh -V 把版本号输出到 stderr。2>&1 把 stderr 合并到 PowerShell 输出流。
    # 注意：直接内联 (@(ssh -V 2>&1) -as [string]) 在某些场景下会因为 native command 
    # 还没完全结束就被 PowerShell 截断而拿到空——先存数组再 -as string 更稳。
    $sshOut = @(ssh -V 2>&1)
    $sshVersion = ($sshOut -as [string]).Trim()
    Write-Ok ('ssh OK: {0}' -f $sshVersion)

    try {
        $resp = Invoke-WebRequest -Uri $DriverHealth -TimeoutSec 3 -UseBasicParsing
        Write-Ok ('driver local OK: {0} -> 200' -f $DriverHealth)
    } catch {
        Write-Warn ('driver local NOT reachable ({0}) -- start driver_service first' -f $DriverHealth)
    }

    try {
        $tcp = Test-NetConnection -ComputerName $CloudHost -Port $CloudPort -WarningAction SilentlyContinue
        if ($tcp.TcpTestSucceeded) {
            Write-Ok ('outbound TCP OK: {0}:{1}' -f $CloudHost, $CloudPort)
        } else {
            Write-Fail ('outbound TCP FAIL: {0}:{1} -- if only 443 is open, WSS redesign needed' -f $CloudHost, $CloudPort)
            return $false
        }
    } catch {
        Write-Warn ('outbound check error: {0}' -f $_)
    }

    $existing = Get-CimInstance Win32_Process -Filter "name='ssh.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and ($_.CommandLine -match "127\.0\.0\.1:$RemotePort") }
    if ($existing) {
        $pids = ($existing | ForEach-Object { $_.ProcessId }) -join ', '
        Write-Warn ('existing tunnel for this index (pid={0}) -- start will stop it first' -f $pids)
    }

    Write-Host ''
    Write-Host '== Cloud side (manual checks, script does NOT run remotely) ==' -ForegroundColor Cyan
    Write-Step '#1 sshd config:'
    Write-Step ('   ssh {0}@{1} -p {2} "sshd -T | grep -E allowtcpforwarding|gatewayports"' -f $CloudUser, $CloudHost, $CloudPort)
    Write-Step '   expected: allowtcpforwarding yes, gatewayports no'
    Write-Step ('#2 port {0} free:' -f $RemotePort)
    Write-Step ('   ssh {0}@{1} -p {2} "ss -tlnp | grep :{0}"' -f $CloudUser, $CloudHost, $CloudPort, $RemotePort)
    Write-Step '#3 tunnel up, verify loopback binding:'
    Write-Step ('   ssh {0}@{1} -p {2} "ss -tlnp | grep :{0}"' -f $CloudUser, $CloudHost, $CloudPort, $RemotePort)
    Write-Step ('   expected: 127.0.0.1:{0} NOT 0.0.0.0:{0} (latter leaks driver to public)' -f $RemotePort)
    return $true
}

# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------

function Start-Tunnel {
    Write-Host ''
    Write-Host '== Starting tunnel ==' -ForegroundColor Cyan
    Stop-Tunnel -Silent

    $sshArgs = @(
        '-R', $ForwardSpec,
        '-o', 'ExitOnForwardFailure=yes',
        '-o', 'ServerAliveInterval=30',
        '-o', 'ServerAliveCountMax=3',
        '-o', 'LogLevel=ERROR',
        '-o', 'ControlMaster=no',
        '-N',
        '-p', "$CloudPort",
        ('{0}@{1}' -f $CloudUser, $CloudHost)
    )

    Write-Step ('ssh {0}' -f ($sshArgs -join ' '))
    $proc = Start-Process -FilePath ssh -ArgumentList $sshArgs `
        -RedirectStandardOutput $TunnelLog -RedirectStandardError $TunnelLog -PassThru
    Start-Sleep -Seconds 2

    if ($proc.HasExited) {
        Write-Fail ('tunnel exited immediately (exit={0})' -f $proc.ExitCode)
        if (Test-Path $TunnelLog) {
            Write-Step 'log:'
            Get-Content $TunnelLog | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
        }
        Write-Host '  common causes: port occupied, allowtcpforwarding=no, key auth failed'
        return $null
    }
    Write-Ok ('tunnel PID={0}' -f $proc.Id)
    Write-Step ('log: {0}' -f $TunnelLog)
    return $proc
}

# ---------------------------------------------------------------------------
# Verify remote binding
# ---------------------------------------------------------------------------

function Test-RemotePort {
    Write-Host ''
    Write-Host ('== Verifying cloud port {0} ==' -f $RemotePort) -ForegroundColor Cyan

    # bash -lc 把整条远端命令包起来，PowerShell 不会提前解析管道 / 重定向。
    # StrictHostKeyChecking=accept-new 让首次连接不阻塞在指纹确认上。
    # here-string 结束标记 '@ 必须独占一行，后面不能跟 -replace 等操作符
    $remoteCmd = (@'
bash -lc 'ss -tlnp 2>/dev/null | grep -E ":PORT " || netstat -tlnp 2>/dev/null | grep :PORT || echo NO_LISTENER'
'@).Replace('PORT', [string]$RemotePort)

    try {
        $out = & ssh -p $CloudPort -o StrictHostKeyChecking=accept-new "$CloudUser@$CloudHost" $remoteCmd 2>&1
    } catch {
        Write-Warn ('remote probe failed: {0}' -f $_)
        return $false
    }
    $out = ($out -join "`n").Trim()

    if ($out -match 'NO_LISTENER') {
        Write-Fail ('cloud {0} NOT listening -- tunnel down' -f $RemotePort)
        return $false
    }
    if ($out -match '0\.0\.0\.0:' -or $out -match '\*\:' -or $out -match (':::' + [regex]::Escape([string]$RemotePort))) {
        Write-Fail ('cloud {0} bound to 0.0.0.0 / * / :: -- driver LEAKED to public' -f $RemotePort)
        return $false
    }
    if ($out -match ('127\.0\.0\.1:' + [regex]::Escape([string]$RemotePort))) {
        Write-Ok ('cloud {0} bound only to loopback -- OK' -f $RemotePort)
        Write-Step ('ss output: {0}' -f $out)
        return $true
    }
    Write-Warn ('cloud binding unexpected: {0}' -f $out)
    return $false
}

# ---------------------------------------------------------------------------
# Stop + status
# ---------------------------------------------------------------------------

function Stop-Tunnel([switch]$Silent) {
    $procs = Get-CimInstance Win32_Process -Filter "name='ssh.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and ($_.CommandLine -match "127\.0\.0\.1:$RemotePort") }

    if (-not $procs) {
        if (-not $Silent) { Write-Warn ('no tunnel for index={0}' -f $MachineIndex) }
        return
    }
    foreach ($p in $procs) {
        Stop-Process -Id $p.ProcessId -Force
        Write-Host ('  stopped PID={0}' -f $p.ProcessId)
    }
}

function Show-Status {
    Write-Host ''
    Write-Host '== local ssh -R tunnels ==' -ForegroundColor Cyan
    $procs = Get-CimInstance Win32_Process -Filter "name='ssh.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and ($_.CommandLine -match ' -R ') }
    if (-not $procs) {
        Write-Warn 'no ssh -R tunnels running'
        return
    }
    $procs | ForEach-Object { Write-Host ('  PID={0}  {1}' -f $_.ProcessId, $_.CommandLine) }
}

# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

switch ($Action) {
    'probe'  { Test-Preflight | Out-Null }
    'status' { Show-Status }
    'stop'   { Stop-Tunnel }
    'start'  {
        $ok = Test-Preflight
        if (-not $ok) {
            Write-Host 'preflight FAILED -- fix and retry -Action start' -ForegroundColor Yellow
            exit 1
        }
        $proc = Start-Tunnel
        if (-not $proc) { exit 1 }
        Write-Host ''
        Write-Host 'sleeping 3s for tunnel to establish...' -ForegroundColor DarkCyan
        Start-Sleep -Seconds 3
        Test-RemotePort
        Write-Host ''
        Write-Host ('== Next: register DesktopHand in agent, run_id="machine-{0}" ==' -f $MachineIndex) -ForegroundColor DarkCyan
    }
}
