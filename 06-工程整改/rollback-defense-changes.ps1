[CmdletBinding(SupportsShouldProcess)]
param(
    [ValidateSet('status', 'restore')]
    [string]$Mode = 'status',
    [string]$ProjectRoot = 'D:\SmartOpsAgent',
    [string]$Bundle = (Join-Path $PSScriptRoot 'rollback-bundle.zip')
)

$ErrorActionPreference = 'Stop'
$rollbackTool = Join-Path $ProjectRoot 'scripts\rollback_defense.py'
if ($Mode -eq 'status') {
    & python $rollbackTool --root $ProjectRoot --bundle $Bundle
} elseif ($PSCmdlet.ShouldProcess($ProjectRoot, 'Restore scoped files and quarantine current contents')) {
    & python $rollbackTool --root $ProjectRoot --bundle $Bundle --apply
}
if ($LASTEXITCODE -ne 0) { throw 'Rollback preflight or restoration failed; check output.' }
