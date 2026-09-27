$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$VenvPath = Join-Path $RepoRoot ".venv"
$PythonPath = Join-Path $VenvPath "Scripts\python.exe"
$RequirementsPath = Join-Path $PSScriptRoot "..\requirements.txt"

if (-not (Test-Path $VenvPath)) {
  py -3.11 -m venv $VenvPath
}

& $PythonPath -m pip install --upgrade pip
& $PythonPath -m pip install -r $RequirementsPath
& $PythonPath -m playwright install chromium

Write-Host "Python environment ready at $VenvPath"
