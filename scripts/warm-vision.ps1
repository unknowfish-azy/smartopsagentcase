# SmartOps vision model warm-up script (ASCII only: PS 5.1 reads non-BOM files as ANSI,
# which corrupts non-ASCII literals and breaks the JSON body).
# Purpose: preload the vision model into memory with keep_alive so the first real
# recognition in a demo does not pay the ~10s cold load.
# Usage:
#   scripts\warm-vision.ps1                    # keep resident for 60 minutes
#   scripts\warm-vision.ps1 -KeepAlive 120m
#
# Pitfalls (verified 2026-11-16):
#   1. Ollama 0.40.8 evicts idle models after ~30-45s; a bare request without
#      keep_alive gets evicted almost immediately. Always pass keep_alive.
#   2. Keep $Model in sync with smartops.vision.model in application.yml.

param(
    [string]$Model = "qwen2.5vl:3b",
    [string]$KeepAlive = "60m"
)

$ErrorActionPreference = 'Stop'
$endPoint = 'http://127.0.0.1:11434/api/chat'

# 1x1 transparent PNG: minimal image, only used to trigger model load.
$tinyPng = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
$body = @{
    model      = $Model
    stream     = $false
    keep_alive = $KeepAlive
    messages   = @(@{
        role    = 'user'
        content = 'Reply with JSON only: {"abnormal":false,"summary":"warmup","issues":[]}'
        images  = @($tinyPng)
    })
    options    = @{ num_ctx = 4096; num_predict = 32 }
} | ConvertTo-Json -Depth 6 -Compress

$sw = [System.Diagnostics.Stopwatch]::StartNew()
# Pass the body via a temp file: PS 5.1 does not escape embedded double quotes
# when forwarding arguments to native executables, which shreds inline JSON.
$tmp = Join-Path $env:TEMP ("warm-vision-" + [guid]::NewGuid().ToString('N') + ".json")
[System.IO.File]::WriteAllText($tmp, $body)
try {
    $raw = curl.exe -s -m 180 $endPoint -d "@$tmp"
} finally {
    Remove-Item $tmp -ErrorAction SilentlyContinue
}
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) {
    Write-Host "[FAIL] Ollama did not respond (exit $LASTEXITCODE). Check that ollama serve is running." -ForegroundColor Red
    exit 1
}
$resp = $raw | ConvertFrom-Json
$sw.Stop()

if ($resp.error) {
    Write-Host "[FAIL] Ollama returned an error: $($resp.error)" -ForegroundColor Red
    exit 1
}

$loadMs = [math]::Round($resp.load_duration / 1e6)
$evalMs = [math]::Round($resp.eval_duration / 1e6)
Write-Host "[READY] Model $Model warmed up and kept resident for $KeepAlive (load $loadMs ms, eval $evalMs ms, total $($sw.ElapsedMilliseconds) ms)" -ForegroundColor Green
Write-Host "[NOTE] After the keep-alive window expires the next call pays a cold load again; rerun this script before a demo." -ForegroundColor Yellow
