#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$logDir = Join-Path (Split-Path -Parent $PSScriptRoot) 'data\logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$computer = Get-CimInstance Win32_ComputerSystem
$before = @{
    automaticManagedPagefile = $computer.AutomaticManagedPagefile
    settings = @(Get-CimInstance Win32_PageFileSetting | Select-Object Name,InitialSize,MaximumSize)
}
$before | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $logDir 'paging-before.json')
Set-CimInstance -InputObject $computer -Property @{ AutomaticManagedPagefile = $true } | Out-Null
@{
    automaticManagedPagefile = (Get-CimInstance Win32_ComputerSystem).AutomaticManagedPagefile
    restartRequired = $true
    message = 'System-managed Windows paging enabled. Restart Windows to activate it. No restart was initiated.'
} | ConvertTo-Json | Set-Content (Join-Path $logDir 'paging-repair-result.json')
