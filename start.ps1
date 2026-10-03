param([int]$Port = 8765, [string]$Data = '', [switch]$NoReload)
$ErrorActionPreference = 'Stop'
$taskPython = & (Join-Path $PSScriptRoot 'tools\resolve-python.ps1') -Root $PSScriptRoot
Push-Location $PSScriptRoot
try {
    $taskArguments = @('-m', 'mapwalker')
    if ($Data) { $taskArguments += @('--data', $Data) }
    $taskArguments += @('serve', '--port', "$Port")
    if (-not $NoReload) { $taskArguments += '--reload' }
    & $taskPython @taskArguments
}
finally { Pop-Location }
