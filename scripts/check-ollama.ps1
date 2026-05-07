$ErrorActionPreference = "Stop"

$response = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get
$models = $response.models | ForEach-Object { $_.name }

if ($models -notcontains "gemma4:e4b") {
  Write-Host "gemma4:e4b was not found. Run: ollama pull gemma4:e4b"
  exit 1
}

Write-Host "Ollama is running and gemma4:e4b is available."
