$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot

if (-not (Test-Path (Join-Path $repoRoot 'pyproject.toml') -PathType Leaf)) {
    throw 'Run install/install.ps1 from a HealthVideo repository containing pyproject.toml.'
}

$venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython -PathType Leaf)) {
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not create .venv with Python.'
    }
}

& $venvPython -m pip install -e '.[dev]'
if ($LASTEXITCODE -ne 0) {
    throw 'Python dependencies could not be installed.'
}

$pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
if ($null -ne $pnpm) {
    & $pnpm.Source install --frozen-lockfile
} else {
    $corepack = Get-Command corepack -ErrorAction SilentlyContinue
    if ($null -eq $corepack) {
        throw 'pnpm was not found. Install pnpm 11+ or enable Corepack.'
    }
    & $corepack.Source pnpm install --frozen-lockfile
}
if ($LASTEXITCODE -ne 0) {
    throw 'Video dependencies could not be installed.'
}

$doctor = Join-Path $repoRoot '.venv\Scripts\healthvideo.exe'
& $doctor doctor
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
