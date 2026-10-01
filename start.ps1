param([int]$Port = 8765, [string]$Data = '', [switch]$NoReload)
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    $taskPython = Join-Path $env:TEMP 'mapwalker-runtime\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Create a Python 3.12 environment and install requirements.txt first. See README.md.'
}
Push-Location $PSScriptRoot
try {
    $taskArguments = @('-m', 'mapwalker')
    if ($Data) { $taskArguments += @('--data', $Data) }
    $taskArguments += @('serve', '--port', "$Port")
    if (-not $NoReload) { $taskArguments += '--reload' }
    & $taskPython @taskArguments
}
finally { Pop-Location }
