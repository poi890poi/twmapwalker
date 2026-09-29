param([Parameter(Mandatory=$true)][string]$Origin)
$ErrorActionPreference = 'Stop'
if ($Origin -notmatch '^https://[^/]+$') { throw 'Provide the exact public HTTPS origin, without a trailing slash.' }
$taskHealth = Invoke-RestMethod "$Origin/healthz" -TimeoutSec 20
if ($taskHealth.authentication_required -ne $true) { throw 'STOP: This endpoint is not the authenticated Mapwalker listener.' }
foreach ($taskPath in @('/api/status','/api/browse','/api/export','/app.js','/evidence/viewer/report.html','/api/pois/1/image','/api/tiles/JM50K_1916/16/54895/28092')) {
    $taskCode = 0
    try { $taskResult = Invoke-WebRequest "$Origin$taskPath" -MaximumRedirection 0 -TimeoutSec 20; $taskCode = [int]$taskResult.StatusCode }
    catch { if ($_.Exception.Response) { $taskCode = [int]$_.Exception.Response.StatusCode } else { throw } }
    if ($taskCode -ne 401) { throw "Authentication check failed for $taskPath (HTTP $taskCode)." }
    Write-Output "Protected: $taskPath (401)"
}
$taskLogin = Invoke-WebRequest "$Origin/auth/login" -TimeoutSec 20
if ($taskLogin.StatusCode -ne 200 -or $taskLogin.Content -notmatch 'google-signin') { throw 'Sign-in page is unavailable.' }
Write-Output 'External HTTPS and anonymous-access boundary verified. Complete a real Google sign-in to verify authorized access.'
