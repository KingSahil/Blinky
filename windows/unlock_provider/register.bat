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

:: Enable password authentication support (disable Windows 11 passwordless restriction)
echo [INFO] Enabling password sign-in support in registry...
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device" /v DevicePasswordLessBuildVersion /t REG_DWORD /d 0 /f >nul

:: Clean up any obsolete scheduled task from prior revisions
schtasks /delete /tn "BlinkyUnlock" /f >nul 2>&1
if exist "%ProgramData%\Blinky\unlock_helper.ps1" del /f "%ProgramData%\Blinky\unlock_helper.ps1" >nul 2>&1

echo.
echo ============================================
echo  Blinky Unlock Provider Registered!
echo ============================================
echo  Credential Provider: active on lock screen
echo  Named pipe:  \\.\pipe\CredentialProviderPipe
echo ============================================
echo.
echo You can now set your local Windows unlock password for user 'sahil'.
echo (Tip: Setting it to 1750 matches your Windows Hello PIN so you can use 1750 everywhere!)
echo.
set /p NEWPASS="Enter unlock password for sahil (e.g. 1750 or your Microsoft password) [or press Enter to skip]: "
if not "%NEWPASS%"=="" (
    net user sahil "%NEWPASS%"
    if errorlevel 1 (
        echo [ERROR] Failed to set password.
    ) else (
        echo.
        echo [SUCCESS] Local password for sahil set successfully!
    )
)
echo.
pause
