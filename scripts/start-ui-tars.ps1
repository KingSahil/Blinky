param([int]$Port = 8119)
$ErrorActionPreference = 'Stop'
$installRoot = Join-Path $env:LOCALAPPDATA 'Blinky/ui-tars'
$runtimeRoot = Join-Path $installRoot 'runtime'
$modelRoot = Join-Path $installRoot 'models'
$server = Get-ChildItem -LiteralPath $runtimeRoot -Filter 'llama-server.exe' -Recurse | Select-Object -First 1
$model = Join-Path $modelRoot 'UI-TARS-1.5-7B-q4_k_m.gguf'
$projector = Join-Path $modelRoot 'UI-TARS-1.5-7B-f16.mmproj'
if (-not $server -or -not (Test-Path -LiteralPath $model) -or -not (Test-Path -LiteralPath $projector)) {
    throw 'UI-TARS model or runtime is missing from LocalAppData/Blinky/ui-tars.'
}
try {
    $models = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/models" -TimeoutSec 3
    if ($models.data.id -contains 'ui-tars-1.5-7b') {
        Write-Output "UI-TARS is already running at http://127.0.0.1:$Port/v1"
        exit 0
    }
} catch { }
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is occupied by another service. Choose another port."
}
$serverArgs = @(
    '-m', ('"' + $model + '"'), '--mmproj', ('"' + $projector + '"'),
    '--alias', 'ui-tars-1.5-7b', '--host', '127.0.0.1', '--port', "$Port",
    '-ngl', '99', '-c', '4096', '-np', '1', '-b', '256', '-ub', '128',
    '--flash-attn', 'on', '--image-max-tokens', '1536', '--no-webui'
)
$process = Start-Process -FilePath $server.FullName -ArgumentList $serverArgs -WorkingDirectory $server.DirectoryName `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $installRoot 'server.stdout.log') `
    -RedirectStandardError (Join-Path $installRoot 'server.stderr.log')
$process.Id | Set-Content -LiteralPath (Join-Path $installRoot 'server.pid')
Write-Output "UI-TARS server starting (PID $($process.Id)). Endpoint: http://127.0.0.1:$Port/v1"
Write-Output "Logs: $installRoot/server.stderr.log"
