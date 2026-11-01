@echo off
echo ========================================================
echo Launching Microsoft Edge with Remote Debugging (Port 9222)
echo ========================================================
echo [1/3] Closing background Edge processes to release profile...
taskkill /F /IM msedge.exe >nul 2>&1
timeout /t 1 /nobreak >nul
echo [2/3] Starting Edge on port 9222 and restoring all previous tabs...
start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --restore-last-session %*
timeout /t 2 /nobreak >nul
echo [3/3] Edge is ready! Blinky browser-use will now connect directly to this window.
