$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
$taskFixture = Join-Path $taskRoot ('data\runtime-resolution-' + [guid]::NewGuid().ToString('N'))
$taskResolver = Join-Path $taskRoot 'tools\resolve-python.ps1'
$taskArguments = @{
    Root = Join-Path $taskFixture 'project'
    TempPath = Join-Path $taskFixture 'new-temp'
    LocalAppData = Join-Path $taskFixture 'local-app-data'
}
function Assert-Runtime([string]$Expected) {
    $taskActual = & $taskResolver @taskArguments
    if ($taskActual -ne (Resolve-Path -LiteralPath $Expected).Path) { throw "Unexpected runtime: $taskActual" }
}
try {
    $taskLegacy = Join-Path $taskArguments.LocalAppData 'Temp\mapwalker-runtime\Scripts\python.exe'
    $taskCurrent = Join-Path $taskArguments.TempPath 'mapwalker-runtime\Scripts\python.exe'
    $taskProject = Join-Path $taskArguments.Root '.venv\Scripts\python.exe'
    foreach ($taskPath in @($taskLegacy,$taskCurrent,$taskProject)) {
        New-Item -ItemType Directory -Path (Split-Path $taskPath -Parent) -Force | Out-Null
    }
    $taskMissing = $false
    try { & $taskResolver @taskArguments } catch { $taskMissing = $_.Exception.Message -like '*runtime not found*' }
    if (-not $taskMissing) { throw 'Missing runtime must fail clearly' }
    New-Item -ItemType File -Path $taskLegacy | Out-Null
    Assert-Runtime $taskLegacy # TEMP moved; old installed environment still works.
    New-Item -ItemType File -Path $taskCurrent | Out-Null
    Assert-Runtime $taskCurrent
    New-Item -ItemType File -Path $taskProject | Out-Null
    Assert-Runtime $taskProject
    Write-Output 'Runtime resolution: moved TEMP, current TEMP, project precedence and missing-runtime checks passed.'
} finally {
    if (Test-Path -LiteralPath $taskFixture) {
        $taskResolved = (Resolve-Path -LiteralPath $taskFixture).Path
        $taskData = (Resolve-Path -LiteralPath (Join-Path $taskRoot 'data')).Path
        if (-not $taskResolved.StartsWith($taskData + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected fixture cleanup path' }
        Remove-Item -LiteralPath $taskResolved -Recurse -Force
    }
}
