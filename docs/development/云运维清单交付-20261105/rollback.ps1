[CmdletBinding(SupportsShouldProcess=$true, ConfirmImpact='Medium')]
param([switch]$VerifyOnly)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$documentDirectory = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$targetPath = [System.IO.Path]::GetFullPath((Join-Path $documentDirectory '云计算运维专业化不足与优化清单-20261105.md'))
$allowedPrefix = $projectRoot.TrimEnd('\') + '\'
if (-not $targetPath.StartsWith($allowedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Rollback target is outside the project root.'
}
if (-not (Test-Path -LiteralPath $targetPath -PathType Leaf)) {
    Write-Output 'Document is already absent; no action required.'
    return
}
$expectedHash = '8d4e39932badd03e416521ad57434b190275f1f083435d45401cfb48e572dead'
$actualHash = (Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedHash) {
    throw 'Document content changed; rollback stopped to preserve later edits.'
}
if ($VerifyOnly) {
    Write-Output 'Verified: path is within the project and SHA256 matches. No files removed.'
    return
}
if ($PSCmdlet.ShouldProcess($targetPath, 'Remove the newly added checklist document')) {
    Remove-Item -LiteralPath $targetPath
    Write-Output 'Checklist document removed. Delivery evidence was retained.'
}
