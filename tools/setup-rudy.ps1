param([string]$Data = '', [switch]$UpdateMap)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
if (-not $Data) { $Data = Join-Path $taskRoot 'data' }
$taskFolder = Join-Path $Data 'rudy'
New-Item -ItemType Directory -Force $taskFolder | Out-Null
if (-not (Get-Command java -ErrorAction SilentlyContinue)) { throw 'Install Java 17 or later before installing Rudy.' }
$taskJar = Join-Path $taskFolder 'mapsforgesrv.jar'
$taskJarHash = 'fb1c83776bc0a3d2550426edb11e727fc230f9611064adcb76953981a1168d79'
if (-not (Test-Path -LiteralPath $taskJar)) {
    Invoke-WebRequest 'https://github.com/telemaxx/mapsforgesrv/releases/download/v0.30.0.0/mapsforgesrv-fatjar.jar' -OutFile ($taskJar+'.download') -TimeoutSec 600
    if ((Get-FileHash -LiteralPath ($taskJar+'.download')).Hash.ToLower() -ne $taskJarHash) { throw 'Renderer checksum mismatch' }
    Move-Item -LiteralPath ($taskJar+'.download') -Destination $taskJar -Force
}
if ((Get-FileHash -LiteralPath $taskJar).Hash.ToLower() -ne $taskJarHash) { throw 'Renderer checksum mismatch' }
$taskMap = Join-Path $taskFolder 'map/MOI_OSM_Taiwan_TOPO_Rudy.map'
if ($UpdateMap -or -not (Test-Path -LiteralPath $taskMap)) {
    $taskZip = Join-Path $taskFolder 'map.download.zip'
    Invoke-WebRequest 'https://moi.kcwu.csie.org/MOI_OSM_Taiwan_TOPO_Rudy.map.zip' -OutFile $taskZip -TimeoutSec 600
    $taskStaging = Join-Path $taskFolder ('install-'+[guid]::NewGuid().ToString('N'))
    Expand-Archive -LiteralPath $taskZip -DestinationPath $taskStaging
    $taskCandidate = Join-Path $taskStaging 'MOI_OSM_Taiwan_TOPO_Rudy.map'
    if (-not (Test-Path -LiteralPath $taskCandidate)) { throw 'Map archive contains no Rudy map' }
    New-Item -ItemType Directory -Force (Split-Path -Parent $taskMap) | Out-Null
    # Stop Mapwalker before updates so no renderer holds the previous map open.
    Move-Item -LiteralPath $taskCandidate -Destination $taskMap -Force
    @{
        url='https://moi.kcwu.csie.org/MOI_OSM_Taiwan_TOPO_Rudy.map.zip'
        downloaded_utc=[DateTime]::UtcNow.ToString('o')
        archive_sha256=(Get-FileHash -LiteralPath $taskZip).Hash.ToLower()
        map_sha256=(Get-FileHash -LiteralPath $taskMap).Hash.ToLower()
        renderer_version='0.30.0.0'
        renderer_sha256=$taskJarHash
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskFolder 'installation.json') -Encoding utf8
}
Write-Output 'Rudy installed. Restart Mapwalker and choose Rudy in Comparison layer.'
