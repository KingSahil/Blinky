# Start a development session with logs and a fresh toolchain PATH.
# This is also usable by launchers that have no attached terminal.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$logRoot = Join-Path $projectRoot 'data\logs'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$toolDirs = @((Join-Path $env:USERPROFILE '.bun\bin'), (Join-Path $env:USERPROFILE '.cargo\bin'))
$env:Path = ($toolDirs -join ';') + ';' + $env:Path
$env:CARGO_BUILD_JOBS = '1'
$bunPath = Join-Path $env:USERPROFILE '.bun\bin\bun.exe'
if (-not (Test-Path -LiteralPath $bunPath)) { $bunPath = (Get-Command bun -ErrorAction Stop).Source }
$devProcess = Start-Process -FilePath $bunPath -ArgumentList @('run', 'dev') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'dev.stdout.log') -RedirectStandardError (Join-Path $logRoot 'dev.stderr.log') -PassThru
$devProcess.Id | Set-Content (Join-Path $logRoot 'dev.pid')
$devProcess.WaitForExit()
exit $devProcess.ExitCode
