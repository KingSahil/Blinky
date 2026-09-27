@echo off
:: ============================================
:: Unregister the Blinky Unlock Credential Provider
:: Must be run as Administrator
:: ============================================

net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] This script must be run as Administrator.
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b 0
)

set GUID={E0A8C5B2-9F3D-4E7A-B1C6-8D2F5A3E9B70}
set DLL_DEST=C:\Windows\System32\UnlockProvider.dll

echo [INFO] Removing credential provider registration...
reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\%GUID%" /f >nul 2>&1

echo [INFO] Removing COM registration...
reg delete "HKLM\SOFTWARE\Classes\CLSID\%GUID%" /f >nul 2>&1

echo [INFO] Removing DLL from System32...
del /f "%DLL_DEST%" >nul 2>&1

echo [INFO] Removing BlinkyUnlock scheduled task...
Unregister-ScheduledTask -TaskName "BlinkyUnlock" -Confirm:$false 2>nul
schtasks /delete /tn "BlinkyUnlock" /f >nul 2>&1
del /f "%ProgramData%\Blinky\unlock_helper.ps1" >nul 2>&1

echo.
echo ============================================
echo  Blinky Unlock Provider Unregistered.
echo ============================================
timeout /t 3
