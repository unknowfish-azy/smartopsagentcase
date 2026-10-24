$ErrorActionPreference = 'Stop'

function Get-ConfigStatus {
    param([string[]]$Names, [switch]$Optional)
    foreach ($name in $Names) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if (-not [string]::IsNullOrWhiteSpace($value)) { return 'OK' }
    }
    if ($Optional) { return 'OPTIONAL' }
    return 'MISSING'
}

$checks = [ordered]@{
    MySQL     = Get-ConfigStatus @('MYSQL_PASSWORD')
    Redis     = Get-ConfigStatus @('REDIS_PASSWORD') -Optional
    LLM       = Get-ConfigStatus @('LLM_PROVIDER')
    Encryption = Get-ConfigStatus @('SMARTOPS_API_KEY_ENCRYPTION_KEY')
    Internal  = Get-ConfigStatus @('SMARTOPS_INTERNAL_TOKEN')
    Knowledge = Get-ConfigStatus @('KNOWLEDGE_SERVICE_URL')
}

foreach ($item in $checks.GetEnumerator()) {
    '{0,-12} {1}' -f $item.Key, $item.Value
}

if ($checks.Values -contains 'MISSING') { exit 1 }
