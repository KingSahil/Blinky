!macro NSIS_HOOK_PREINSTALL
  ; Stop any running blinky processes to release file locks on update/overwrite
  DetailPrint "Stopping existing Blinky processes..."
  nsExec::ExecToLog 'powershell -Command "Get-Process -Name blinky -ErrorAction SilentlyContinue | Stop-Process -Force; Get-Process | Where-Object { $_.Path -like ''*AppData\Local\Blinky*'' } | Stop-Process -Force -ErrorAction SilentlyContinue"'

  ; Purge old runtime and module directories to avoid stale/colliding files from previous installations
  DetailPrint "Cleaning previous installation files..."
  RMDir /r "$INSTDIR\python_runtime"
  RMDir /r "$INSTDIR\common"
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\windows"
!macroend

!macro NSIS_HOOK_POSTINSTALL
  ; Automatically configure Windows Firewall inbound rules for mobile remote connectivity (port 9001)
  DetailPrint "Configuring Windows Firewall for mobile connectivity..."
  nsExec::ExecToLog 'netsh advfirewall firewall add rule name="Blinky WebSocket Port 9001" dir=in action=allow protocol=TCP localport=9001'
  nsExec::ExecToLog 'netsh advfirewall firewall add rule name="Blinky Application" dir=in action=allow program="$INSTDIR\blinky.exe" enable=yes'

  ; Execute our python addon setup script and wait for it to complete.
  ; $INSTDIR is the installation directory selected by the user.
  ExecWait '"$INSTDIR\python_runtime\Python313\python.exe" "$INSTDIR\common\python\post_install.py"'
!macroend

