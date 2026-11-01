$ErrorActionPreference = 'Stop'
$installRoot = Join-Path $env:LOCALAPPDATA 'Blinky/ui-tars'
$pidFile = Join-Path $installRoot 'server.pid'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Output 'No UI-TARS server PID recorded.'; exit 0 }
$serverProcessId = [int](Get-Content -LiteralPath $pidFile)
$serverProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$serverProcessId" -ErrorAction SilentlyContinue
$runtimeRoot = [IO.Path]::GetFullPath((Join-Path $installRoot 'runtime')) + [IO.Path]::DirectorySeparatorChar
if ($serverProcess) {
    if ($serverProcess.Name -ne 'llama-server.exe' -or -not $serverProcess.ExecutablePath.StartsWith($runtimeRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Recorded PID belongs to a different program; refusing to stop it.'
    }
    Stop-Process -Id $serverProcessId
    Write-Output 'Stopped the local UI-TARS server.'
} else { Write-Output 'UI-TARS server is already stopped.' }
