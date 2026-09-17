@echo off
:: ============================================
:: Register the Blinky Unlock Credential Provider
:: Must be run as Administrator
:: ============================================

net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] This script must be run as Administrator.
    echo Requesting elevation...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b 0
)

set GUID={E0A8C5B2-9F3D-4E7A-B1C6-8D2F5A3E9B70}
set DLL_SRC=%~dp0UnlockProvider.dll
set DLL_DEST=C:\Windows\System32\UnlockProvider.dll

if not exist "%DLL_SRC%" (
    echo [ERROR] UnlockProvider.dll not found in %~dp0
    pause
    exit /b 1
)

echo [INFO] Copying UnlockProvider.dll to System32...
copy /Y "%DLL_SRC%" "%DLL_DEST%"
if errorlevel 1 (
    echo [ERROR] Failed to copy DLL to System32.
    pause
    exit /b 1
)

echo [INFO] Registering COM server...
reg add "HKLM\SOFTWARE\Classes\CLSID\%GUID%" /ve /d "UnlockProvider" /f >nul
reg add "HKLM\SOFTWARE\Classes\CLSID\%GUID%\InprocServer32" /ve /d "%DLL_DEST%" /f >nul
reg add "HKLM\SOFTWARE\Classes\CLSID\%GUID%\InprocServer32" /v ThreadingModel /d "Apartment" /f >nul

echo [INFO] Registering credential provider...
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\%GUID%" /ve /d "UnlockProvider" /f >nul

echo [INFO] Installing BlinkyUnlock scheduled task...
if not exist "%ProgramData%\Blinky" mkdir "%ProgramData%\Blinky"
copy /Y "%~dp0unlock_helper.ps1" "%ProgramData%\Blinky\unlock_helper.ps1"
if errorlevel 1 (
    echo [WARN] Could not copy unlock_helper.ps1 to %ProgramData%\Blinky
)

powershell -NoProfile -Command ^
  "& { $a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ''%ProgramData%\Blinky\unlock_helper.ps1'''); $p = New-ScheduledTaskPrincipal -UserId SYSTEM -LogonType ServiceAccount -RunLevel Highest; $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; Register-ScheduledTask -Force -TaskName BlinkyUnlock -Action $a -Principal $p -Settings $s | Out-Null; Write-Host '[INFO] BlinkyUnlock scheduled task registered (runs as SYSTEM).' }"

echo.
echo ============================================
echo  Blinky Unlock Provider Registered!
echo ============================================
echo  Credential Provider: active on lock screen
echo  Named pipe:  \\.\pipe\CredentialProviderPipe
echo  Unlock task: schtasks /run /tn BlinkyUnlock
echo ============================================
pause
