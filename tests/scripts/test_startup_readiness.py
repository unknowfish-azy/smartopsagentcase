import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import socket
import subprocess
import threading

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_windows_readiness_checks_real_http_contract(tmp_path):
    executable = shutil.which("pwsh.exe") or shutil.which("powershell.exe")
    if not executable:
        pytest.skip("PowerShell not installed")
    fixtures = {
        "/ready": (200, {"service": "smartops-knowledge-service", "status": "READY", "ready": True, "chunks": 2}),
        "/empty": (200, {"service": "smartops-knowledge-service", "status": "UP", "ready": False, "chunks": 0}),
        "/legacy": (200, {"service": "smartops-knowledge-service", "status": "UP", "chunks": 2}),
        "/wrong": (200, {"service": "unrelated", "status": "READY", "ready": True, "chunks": 2}),
        "/failed": (503, {"ready": False}),
        "/fractional": (200, {"service": "smartops-knowledge-service", "status": "READY", "ready": True, "chunks": 0.5}),
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status, body = fixtures[self.path]
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    wrapper = tmp_path / "readiness.ps1"
    wrapper.write_text('''param([string]$Library,[string]$BaseUrl)
$ErrorActionPreference='Stop'
. $Library
$results=@{}
foreach($name in @('ready','empty','legacy','wrong','failed','fractional')) {
 $results[$name]=Test-ServiceReadiness -Uri ($BaseUrl+'/'+$name) -ExpectedService 'smartops-knowledge-service' -RequireIndex
}
Wait-ServiceReadiness -ServiceName test -Uri ($BaseUrl+'/ready') -ExpectedService 'smartops-knowledge-service' -RequireIndex -TimeoutSeconds 1
$results['waitReady']=$true
$results['waitEmptyTimedOut']=$false
try {
 Wait-ServiceReadiness -ServiceName test -Uri ($BaseUrl+'/empty') -ExpectedService 'smartops-knowledge-service' -RequireIndex -TimeoutSeconds 1 -PollSeconds 1
} catch { $results['waitEmptyTimedOut']=$true }
$results | ConvertTo-Json -Compress
''', encoding="utf-8")
    try:
        process = subprocess.run([executable, "-NoProfile", "-NonInteractive", "-File", str(wrapper), str(ROOT / "scripts/windows/service-readiness.ps1"), f"http://127.0.0.1:{server.server_port}"], capture_output=True, text=True, timeout=25)
        assert process.returncode == 0, process.stderr
        assert json.loads(process.stdout.strip().splitlines()[-1]) == {"ready": True, "empty": False, "legacy": False, "wrong": False, "failed": False, "fractional": False, "waitReady": True, "waitEmptyTimedOut": True}
    finally:
        server.shutdown()
        server.server_close()


def test_existing_listener_is_not_started_again(tmp_path):
    executable = shutil.which("pwsh.exe") or shutil.which("powershell.exe")
    if not executable:
        pytest.skip("PowerShell not installed")
    wrapper = tmp_path / "reuse.ps1"
    wrapper.write_text('''param([string]$Launcher,[string]$Root,[int]$Port)
$ErrorActionPreference='Stop'
$ProjectRoot=$Root
$tokens=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($Launcher,[ref]$tokens,[ref]$errors)
foreach($functionName in @('Test-TcpPort','Start-CommandWindow')) {
 $node=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $functionName},$true)
 . ([scriptblock]::Create($node.Extent.Text))
}
function Start-Process { throw 'Unexpected duplicate process start' }
Start-CommandWindow -Name test -WorkingDirectory $Root -Command 'exit 99' -Port $Port
'NO_DUPLICATE'
''', encoding="utf-8")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        result = subprocess.run([executable, "-NoProfile", "-NonInteractive", "-File", str(wrapper), str(ROOT / "scripts/windows/start-all.ps1"), str(tmp_path), str(listener.getsockname()[1])], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("NO_DUPLICATE")
