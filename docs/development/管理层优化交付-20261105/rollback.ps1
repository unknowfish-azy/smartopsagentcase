[CmdletBinding()]
param(
    [string]$ProjectRoot = ([System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))),
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$taskRelative = 'docs/development/管理层优化与开源参考实施计划-20261105.md'
$taskExpectedHash = '6ce9b3d80b5ce78ec7a6a1377ce57229ee2f385fb742b5fe9f1a7320dcff119c'
$taskTarget = [System.IO.Path]::GetFullPath((Join-Path $taskRoot $taskRelative))
$taskPrefix = $taskRoot.TrimEnd([char[]]@('\', '/')) + [System.IO.Path]::DirectorySeparatorChar
if (-not $taskTarget.StartsWith($taskPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Target is outside the selected project root.'
}

# Check each existing ancestor; do not follow a junction or symbolic link.
$taskAncestor = $taskRoot
if (-not (Test-Path -LiteralPath $taskRoot -PathType Container)) {
    throw 'Project root must be an existing directory.'
}
if ((Get-Item -LiteralPath $taskRoot).Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
    throw 'Project root must not be a reparse point.'
}
foreach ($taskPart in @('docs', 'development')) {
    $taskAncestor = Join-Path $taskAncestor $taskPart
    if (Test-Path -LiteralPath $taskAncestor) {
        $taskDirectory = Get-Item -LiteralPath $taskAncestor
        if (-not $taskDirectory.PSIsContainer -or ($taskDirectory.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            throw 'Taskbook ancestor must be a regular directory.'
        }
    }
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
