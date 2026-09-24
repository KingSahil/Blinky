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
powershell -Command "New-NetFirewallRule -DisplayName 'Blinky File Transfer Port 9002' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 9002"
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
