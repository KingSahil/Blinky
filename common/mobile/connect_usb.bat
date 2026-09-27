@echo off
echo ===================================================
echo Blinky USB Connection Helper
echo ===================================================
echo.
echo Searching for adb.exe...

set ADB_PATH=adb

:: Check if adb is in PATH
where adb >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [OK] adb found in system PATH.
    goto run_adb
)

:: Check ANDROID_HOME
if not "%ANDROID_HOME%"=="" (
    if exist "%ANDROID_HOME%\platform-tools\adb.exe" (
        set ADB_PATH="%ANDROID_HOME%\platform-tools\adb.exe"
        echo [OK] adb found in %%ANDROID_HOME%%.
        goto run_adb
    )
)

:: Check Local AppData default Android Sdk path
if exist "%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe" (
    set ADB_PATH="%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
    echo [OK] adb found in LocalAppData.
    goto run_adb
)

echo [ERROR] adb.exe could not be found. 
echo Please ensure Android SDK Platform Tools are installed and adb is in your system PATH.
pause
exit /b 1

:run_adb
echo.
echo Running 'adb reverse tcp:9001 tcp:9001', 'adb reverse tcp:9002 tcp:9002', and 'adb reverse tcp:8081 tcp:8081'...
%ADB_PATH% reverse tcp:9001 tcp:9001
if %ERRORLEVEL% neq 0 goto reverse_error
%ADB_PATH% reverse tcp:9002 tcp:9002
if %ERRORLEVEL% neq 0 goto reverse_error
%ADB_PATH% reverse tcp:8081 tcp:8081 >nul 2>nul
if %ERRORLEVEL% neq 0 goto reverse_error
echo [SUCCESS] USB reverse routing established!
echo Inside the Blinky Mobile App, connect using IP: localhost
echo Make sure your Blinky desktop app is running.
goto finish

:reverse_error
echo [ERROR] Failed to run adb reverse.
echo Please make sure:
echo 1. Your phone is connected via USB.
echo 2. USB Debugging is ENABLED in Developer Options on your phone.
echo 3. You accepted the 'Allow USB debugging' prompt on your phone screen.

:finish
echo.
pause
