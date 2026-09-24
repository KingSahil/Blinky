@echo off
echo ===================================================
echo Blinky Windows Firewall Setup Helper
echo ===================================================
echo.
echo This script will add inbound firewall rules for Blinky ports 9001 and 9002.
echo It must be run as Administrator.
echo.

:: Check for Administrator privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Please right-click this file and select "Run as Administrator".
    echo.
    pause
    exit /b 1
)

echo Adding inbound rule for TCP port 9001...
powershell -Command "New-NetFirewallRule -DisplayName 'Blinky WebSocket Port 9001' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 9001"
if %errorlevel% neq 0 goto firewall_error

set "BLINKY_EXE=%LOCALAPPDATA%\Blinky\blinky.exe"
if not exist "%BLINKY_EXE%" set "BLINKY_EXE=%LOCALAPPDATA%\Programs\Blinky\blinky.exe"
if not exist "%BLINKY_EXE%" (
    echo Could not find Blinky in the default per-user install locations.
    set /p "BLINKY_EXE=Enter the full path to Blinky's blinky.exe: "
)
if not exist "%BLINKY_EXE%" (
    echo [ERROR] The specified Blinky executable was not found.
    goto firewall_error
)

echo Adding program-scoped inbound rule for TCP port 9002...
netsh advfirewall firewall add rule name="Blinky File Transfer Port 9002" dir=in action=allow program="%BLINKY_EXE%" protocol=TCP localport=9002 enable=yes
if %errorlevel% neq 0 goto firewall_error

echo.
echo [SUCCESS] Firewall rules added successfully!
echo Blinky is now allowed to accept WebSocket and file transfer connections from your phone.
goto finish

:firewall_error
echo.
echo [ERROR] Failed to add both firewall rules. Please check if PowerShell is blocked.

:finish
echo.
pause
