# Pure HTTP readiness helpers; dot-sourcing does not start or stop any process.
function Test-ServiceReadiness {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [string]$ExpectedService,
        [switch]$RequireIndex
    )
    $response = $null
    $reader = $null
    try {
        $request = [System.Net.HttpWebRequest]::Create($Uri)
        $request.Proxy = $null
        $request.Timeout = 3000
        $request.ReadWriteTimeout = 3000
        $request.AllowAutoRedirect = $false
        $response = $request.GetResponse()
        if ([int]$response.StatusCode -ne 200) { return $false }
        $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
        $payload = $reader.ReadToEnd() | ConvertFrom-Json
        if ($ExpectedService -and $payload.service -ne $ExpectedService) { return $false }
        if ($RequireIndex) {
            return ($payload.ready -is [bool] -and $payload.ready -eq $true -and
                ($payload.chunks -is [int] -or $payload.chunks -is [long]) -and
                $payload.chunks -gt 0 -and $payload.status -eq 'READY')
        }
        return ($payload.status -eq 'UP')
    }
    catch { return $false }
    finally {
        if ($reader) { $reader.Dispose() }
        if ($response) { $response.Close() }
    }
}

function Wait-ServiceReadiness {
    param(
        [Parameter(Mandatory = $true)][string]$ServiceName,
        [Parameter(Mandatory = $true)][string]$Uri,
        [string]$ExpectedService,
        [switch]$RequireIndex,
        [ValidateRange(1, 3600)][int]$TimeoutSeconds = 120,
        [ValidateRange(1, 60)][int]$PollSeconds = 2
    )
    $timer = [Diagnostics.Stopwatch]::StartNew()
    do {
        if (Test-ServiceReadiness -Uri $Uri -ExpectedService $ExpectedService -RequireIndex:$RequireIndex) {
            Write-Host ("[OK] {0} HTTP readiness: {1}" -f $ServiceName, $Uri)
            return
        }
        if ($timer.Elapsed.TotalSeconds -ge $TimeoutSeconds) { break }
        Start-Sleep -Seconds ([Math]::Min($PollSeconds, [Math]::Ceiling($TimeoutSeconds - $timer.Elapsed.TotalSeconds)))
    } while ($timer.Elapsed.TotalSeconds -lt $TimeoutSeconds)
    throw ("Readiness failed for {0}: {1}. A listening port alone is insufficient; inspect process ownership, index and logs." -f $ServiceName, $Uri)
}
