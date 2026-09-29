param([int]$Port = 8767, [string]$Data = '', [string]$Config = '')
$ErrorActionPreference = 'Stop'
if ($Port -eq 8765) { throw 'Keep port 8765 for the local worker. Use a separate port for public access.' }
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { $taskPython = Join-Path $env:TEMP 'mapwalker-runtime\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Install requirements.lock.txt into a Python 3.12 environment first.' }
$taskPreviousConfig = $env:MAPWALKER_ACCESS_CONFIG
if ($Config) { $env:MAPWALKER_ACCESS_CONFIG = (Resolve-Path -LiteralPath $Config).Path }
Push-Location $PSScriptRoot
try {
    $taskArguments = @('-m', 'mapwalker')
    if ($Data) { $taskArguments += @('--data', $Data) }
    $taskArguments += @('serve', '--public', '--no-worker', '--port', "$Port")
    & $taskPython @taskArguments
    if ($LASTEXITCODE -ne 0) { throw 'Public listener failed; no unauthenticated fallback was started.' }
}
finally { Pop-Location; $env:MAPWALKER_ACCESS_CONFIG = $taskPreviousConfig }
