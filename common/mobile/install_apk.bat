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
:: Detect if release APK exists, otherwise default to debug APK
set APK_PATH=android\app\build\outputs\apk\release\app-release.apk
if not exist "%APK_PATH%" (
    set APK_PATH=android\app\build\outputs\apk\debug\app-debug.apk
)

if not exist "%APK_PATH%" (
    echo [ERROR] Could not find any APK.
    echo Expected:
    echo - Release: android\app\build\outputs\apk\release\app-release.apk
    echo - Debug:   android\app\build\outputs\apk\debug\app-debug.apk
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
    echo 1. Keep your phone connected via USB.
    echo 2. Run 'connect_usb.bat' to forward port 9001.
    echo 3. Open the 'mobile' app on your phone, type 'localhost' as IP, and click connect!
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
