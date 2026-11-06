$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    Write-Error 'Project environment is missing. Follow README_GARMIN.md to install it.'
    exit 1
}
Push-Location $Project
try {
    & $Python (Join-Path $Project 'sync_garmin.py') --interactive
    exit $LASTEXITCODE
} finally {
    Pop-Location
}

