param(
    [switch]$SkipTts
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot

if (-not (Test-Path (Join-Path $repoRoot 'pyproject.toml') -PathType Leaf)) {
    throw 'Run install/install.ps1 from a HealthVideo repository containing pyproject.toml.'
}

$venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython -PathType Leaf)) {
    if ($null -eq (Get-Command python -ErrorAction SilentlyContinue)) {
        throw 'Python 3.11+ was not found on PATH. Install Python and retry.'
    }
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

$ttsPython = Join-Path $repoRoot 'cache\tts-venv\Scripts\python.exe'
if (-not $SkipTts) {
    $ttsReady = $false
    $ttsProbe = "import sys, vieneu; from importlib.metadata import version; sys.exit(0 if sys.version_info[:2] == (3, 11) and version('vieneu') == '3.6.4' else 1)"
    if (Test-Path $ttsPython -PathType Leaf) {
        try {
            & $ttsPython -c $ttsProbe 2>$null
            $ttsReady = $LASTEXITCODE -eq 0
        } catch {
            $ttsReady = $false
        }
    }
    if ($ttsReady) {
        Write-Host 'TTS ready: Python 3.11 / vieneu 3.6.4; skipping install.'
    } else {
        $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
        if ($null -ne $uvCommand) {
            $uv = $uvCommand.Source
        } else {
            $uv = Join-Path $repoRoot '.venv\Scripts\uv.exe'
            if (-not (Test-Path $uv -PathType Leaf)) {
                & $venvPython -m pip install uv
                if ($LASTEXITCODE -ne 0) {
                    throw 'uv could not be installed into .venv for TTS setup.'
                }
            }
        }
        if (-not (Test-Path $ttsPython -PathType Leaf)) {
            & $uv venv --python 3.11 (Join-Path $repoRoot 'cache\tts-venv')
            if ($LASTEXITCODE -ne 0) {
                throw 'Could not create cache/tts-venv with Python 3.11 using uv.'
            }
        }
        & $uv pip install --python $ttsPython 'vieneu==3.6.4'
        if ($LASTEXITCODE -ne 0) {
            throw 'VieNeu 3.6.4 dependencies could not be installed.'
        }
        & $ttsPython -c $ttsProbe
        if ($LASTEXITCODE -ne 0) {
            throw 'TTS verification failed: cache/tts-venv requires Python 3.11 and importable vieneu 3.6.4.'
        }
    }
} else {
    Write-Host 'TTS setup skipped (-SkipTts).'
}

$doctor = Join-Path $repoRoot '.venv\Scripts\healthvideo.exe'
& $doctor doctor
if ($LASTEXITCODE -ne 0) {
    throw 'Environment checks failed. Follow the doctor remedies above and rerun install/install.ps1.'
}
Write-Host 'HealthVideo installation complete.'
