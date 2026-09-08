$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot

if (-not (Test-Path (Join-Path $repoRoot 'pyproject.toml') -PathType Leaf)) {
    throw 'Run install/doctor.ps1 from a HealthVideo repository containing pyproject.toml.'
}

$doctor = Join-Path $repoRoot '.venv\Scripts\healthvideo.exe'
if (-not (Test-Path $doctor -PathType Leaf)) {
    throw 'Missing .venv. Run install/install.ps1 first.'
}

& $doctor doctor
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
