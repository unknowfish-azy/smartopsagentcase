[CmdletBinding()]
param(
    [string]$ProjectRoot = ([System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))),
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$taskRelative = 'docs/development/路演短板优化与多模型实施任务书-20261105.md'
$taskExpectedHash = '38e9ab83f7572c349e0b1219782d09cb6e8ecc02758403ca62930da613dcac96'
$taskTarget = [System.IO.Path]::GetFullPath((Join-Path $taskRoot $taskRelative))
$taskPrefix = $taskRoot.TrimEnd([char[]]@('\', '/')) + [System.IO.Path]::DirectorySeparatorChar
if (-not $taskTarget.StartsWith($taskPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Target is outside the selected project root.'
}
if (-not (Test-Path -LiteralPath $taskTarget)) {
    Write-Output 'NOOP: taskbook is already absent.'
    return
}
$taskFile = Get-Item -LiteralPath $taskTarget
if ($taskFile.PSIsContainer -or ($taskFile.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
    throw 'Expected a regular taskbook file.'
}
$taskActualHash = (Get-FileHash -LiteralPath $taskTarget -Algorithm SHA256).Hash.ToLowerInvariant()
if ($taskActualHash -ne $taskExpectedHash) {
    throw 'Hash mismatch: taskbook changed after delivery; no file was removed.'
}
Write-Output ('VERIFIED: ' + $taskTarget)
if (-not $Apply) {
    Write-Output 'DRY_RUN: use -Apply to remove only this newly added taskbook. Delivery evidence is retained.'
    return
}
Remove-Item -LiteralPath $taskTarget
Write-Output 'ROLLED_BACK: taskbook removed; delivery evidence retained.'
