param([int]$Port = 8768, [string]$Config = '')
$ErrorActionPreference = 'Stop'
if ($Port -in @(8765,8767)) { throw 'Use a dedicated private port, normally 8768.' }
$taskPython = Join-Path $env:TEMP 'mapwalker-runtime\Scripts\python.exe'
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.venv\Scripts\python.exe')) { $taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe' }
if (-not $Config) { $Config = Join-Path $PSScriptRoot 'data\tailscale-access.json' }
$taskPreviousConfig = $env:MAPWALKER_ACCESS_CONFIG
$env:MAPWALKER_ACCESS_CONFIG = (Resolve-Path -LiteralPath $Config).Path
Push-Location $PSScriptRoot
try {
    & $taskPython -m mapwalker serve --tailscale --no-worker --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Private listener failed; no unprotected fallback was started.' }
} finally { Pop-Location; $env:MAPWALKER_ACCESS_CONFIG = $taskPreviousConfig }
