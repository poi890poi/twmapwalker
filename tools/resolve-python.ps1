param(
    [Parameter(Mandatory=$true)][string]$Root,
    [string]$TempPath = $env:TEMP,
    [string]$LocalAppData = $env:LOCALAPPDATA
)
$ErrorActionPreference = 'Stop'
# TEMP can move independently of an already installed virtual environment.
# Prefer the project environment, then the current and original user temp roots.
$taskCandidates = @((Join-Path $Root '.venv\Scripts\python.exe'))
if ($TempPath) { $taskCandidates += Join-Path $TempPath 'mapwalker-runtime\Scripts\python.exe' }
if ($LocalAppData) { $taskCandidates += Join-Path $LocalAppData 'Temp\mapwalker-runtime\Scripts\python.exe' }
foreach ($taskCandidate in ($taskCandidates | Select-Object -Unique)) {
    if (Test-Path -LiteralPath $taskCandidate -PathType Leaf) {
        return (Resolve-Path -LiteralPath $taskCandidate).Path
    }
}
throw 'Mapwalker Python runtime not found. Install requirements.lock.txt into a Python 3.12 .venv in the project, or restore the existing mapwalker-runtime environment.'
