@echo off
echo ===================================================
echo Blinky Windows Firewall Setup Helper
echo ===================================================
echo.
echo This script will add an inbound firewall rule for Port 9001.
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

if %errorlevel% equ 0 (
    echo.
    echo [SUCCESS] Firewall rule added successfully!
    echo Blinky is now allowed to accept connections from your phone on port 9001.
) else (
    echo.
    echo [ERROR] Failed to add firewall rule. Please check if PowerShell is blocked.
)
echo.
pause
