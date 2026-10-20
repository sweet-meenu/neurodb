# Sets up and runs the NeuroDB backend (FastAPI, neurodb-core), frontend
# (Next.js, neurodb-web), and the medical-knowledge RAG demo (Streamlit,
# neurodb-medbot) together in one console. Press Ctrl+C to stop all three.
#
# Usage: .\run.ps1
#
# First run bootstraps everything needed -- no manual setup required:
#   - Installs 'uv' (Python package/version manager) if it isn't already on PATH.
#   - uv sync in neurodb-core (installs Python deps, fetches the right Python
#     version automatically -- no system Python required).
#   - npm install in neurodb-web.
#   - Creates neurodb-medbot/.venv via uv and installs its requirements.txt
#     into it (no system Python/pip required there either).
# Every subsequent run repeats these installs, which are near-instant no-ops
# once everything's already in place, so dependencies never silently drift.
#
# The only prerequisite this script can't install for you is Node.js/npm
# (neurodb-web needs Node 20+) -- see https://nodejs.org/ if that check fails.

$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$backendDir = Join-Path $root "neurodb-core"
$frontendDir = Join-Path $root "neurodb-web"
$medbotDir = Join-Path $root "neurodb-medbot"

# ---- 0. Prerequisite checks / bootstrap -------------------------------------

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "Node.js/npm not found on PATH." -ForegroundColor Red
    Write-Host "Install Node.js 20+ from https://nodejs.org/, open a new terminal, and re-run .\run.ps1" -ForegroundColor Red
    exit 1
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "'uv' (Python package/version manager) not found -- installing it now via https://astral.sh/uv/install.ps1 ..." -ForegroundColor Yellow
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    # The installer adds uv to a user-scoped PATH entry that this already-running
    # session won't see yet -- add its default install dir so the rest of this
    # script can use it immediately without requiring a new terminal.
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "uv installed, but isn't resolving on PATH in this session -- open a new terminal and re-run .\run.ps1" -ForegroundColor Red
        exit 1
    }
}

# ---- 1. .env bootstrapping (only fills in what's genuinely missing) --------

$envLocal = Join-Path $frontendDir ".env.local"
$envExample = Join-Path $frontendDir ".env.example"
if (-not (Test-Path $envLocal) -and (Test-Path $envExample)) {
    Copy-Item $envExample $envLocal
    Write-Host "Created neurodb-web/.env.local from .env.example"
}

$medbotEnv = Join-Path $medbotDir ".env"
$medbotEnvExample = Join-Path $medbotDir ".env.example"
if (-not (Test-Path $medbotEnv) -and (Test-Path $medbotEnvExample)) {
    Copy-Item $medbotEnvExample $medbotEnv
    Write-Host "Created neurodb-medbot/.env from .env.example -- fill in GEMINI_API_KEY before using the chatbot"
}

# ---- 2. Install dependencies -------------------------------------------------

Write-Host "`nInstalling backend dependencies (uv sync)..." -ForegroundColor Cyan
Push-Location $backendDir
uv sync
Pop-Location

Write-Host "`nInstalling frontend dependencies (npm install)..." -ForegroundColor Cyan
Push-Location $frontendDir
npm install
Pop-Location

Write-Host "`nInstalling medbot dependencies (uv venv + uv pip install)..." -ForegroundColor Cyan
$medbotVenv = Join-Path $medbotDir ".venv"
$medbotPython = Join-Path $medbotVenv "Scripts\python.exe"
if (-not (Test-Path $medbotPython)) {
    Push-Location $medbotDir
    uv venv
    Pop-Location
}
uv pip install --python $medbotPython -r (Join-Path $medbotDir "requirements.txt")

# ---- 3. Launch all three -----------------------------------------------------

$backend = $null
$frontend = $null
$medbot = $null

function Stop-All {
    Write-Host "`nStopping backend, frontend, and medbot..."
    foreach ($p in @($backend, $frontend, $medbot)) {
        if ($p -and -not $p.HasExited) {
            try {
                Start-Process -FilePath "taskkill" -ArgumentList "/PID", $p.Id, "/T", "/F" -NoNewWindow -Wait -ErrorAction SilentlyContinue | Out-Null
            } catch {}
        }
    }
}

try {
    Write-Host "`nStarting backend (FastAPI) on http://localhost:8000 ..." -ForegroundColor Cyan
    $backend = Start-Process -FilePath "uv" `
        -ArgumentList "run", "uvicorn", "neurodb_core.app:create_app", "--factory", "--reload" `
        -WorkingDirectory $backendDir -NoNewWindow -PassThru

    Write-Host "Starting frontend (Next.js) on http://localhost:3000 ..." -ForegroundColor Cyan
    $frontend = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", "npm run dev" `
        -WorkingDirectory $frontendDir -NoNewWindow -PassThru

    Write-Host "Starting medbot (Streamlit) on http://localhost:8501 ..." -ForegroundColor Cyan
    $medbotStreamlit = Join-Path $medbotVenv "Scripts\streamlit.exe"
    $medbot = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", "`"$medbotStreamlit`" run app.py" `
        -WorkingDirectory $medbotDir -NoNewWindow -PassThru

    Write-Host "`nAll three services are running. Press Ctrl+C to stop them.`n" -ForegroundColor Green
    Wait-Process -Id $backend.Id, $frontend.Id, $medbot.Id
}
finally {
    Stop-All
}
