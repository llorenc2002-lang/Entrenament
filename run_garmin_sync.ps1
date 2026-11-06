$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Project '.venv\Scripts\python.exe'
Push-Location $Project
try {
    & $Python (Join-Path $Project 'sync_garmin.py')
    exit $LASTEXITCODE
} finally {
    Pop-Location
}

