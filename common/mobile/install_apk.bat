@echo off
echo ===================================================
echo Blinky APK Installer
echo ===================================================
echo.
echo Searching for adb.exe...

set ADB_PATH=adb
set APK_PATH=android\app\build\outputs\apk\debug\app-debug.apk

:: Check if adb is in PATH
where adb >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [OK] adb found in system PATH.
    goto run_install
)

:: Check ANDROID_HOME
if not "%ANDROID_HOME%"=="" (
    if exist "%ANDROID_HOME%\platform-tools\adb.exe" (
        set ADB_PATH="%ANDROID_HOME%\platform-tools\adb.exe"
        echo [OK] adb found in %%ANDROID_HOME%%.
        goto run_install
    )
)

:: Check Local AppData default Android Sdk path
if exist "%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe" (
    set ADB_PATH="%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
    echo [OK] adb found in LocalAppData.
    goto run_install
)

echo [ERROR] adb.exe could not be found. 
echo Please ensure Android SDK Platform Tools are installed and adb is in your system PATH.
pause
exit /b 1

:run_install
echo.
:: Debug is the default for device testing. A stale release APK must not override it.
set APK_PATH=android\app\build\outputs\apk\debug\app-debug.apk
if /I "%~1"=="release" set APK_PATH=android\app\build\outputs\apk\release\app-release.apk

if not exist "%APK_PATH%" (
    echo [ERROR] Could not find any APK.
    echo Expected APK:
    echo %APK_PATH%
    echo.
    echo Please make sure you successfully ran the local build command first.
    pause
    exit /b 1
)

echo Found APK: %APK_PATH%


echo Installing APK to your connected device...
%ADB_PATH% install -r "%APK_PATH%"
if %ERRORLEVEL% equ 0 (
    echo.
    echo [SUCCESS] APK successfully installed on your phone!
    echo.
    echo Next steps:
    echo 1. For debug testing, start the PC app with 'bun run dev' from the repository root.
    echo    This starts Metro and the desktop development transport required by the debug APK.
    echo 2. Keep your phone connected via USB. 'connect_usb.bat' forwards ports 9001, 9002, 9004, and 8081.
    echo 3. Connect using 'localhost' in the mobile app.
    echo.
    echo To explicitly install a release APK, run this script with the 'release' argument.
) else (
    echo.
    echo [ERROR] Failed to install APK.
    echo Please make sure:
    echo 1. Your phone is connected via USB.
    echo 2. USB Debugging is ENABLED in Developer Options.
    echo 3. The screen is unlocked and you authorize your PC if prompted.
)
echo.
pause
