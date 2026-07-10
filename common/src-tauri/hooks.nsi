!macro NSIS_HOOK_POSTINSTALL
  ; Execute our python addon setup script and wait for it to complete.
  ; $INSTDIR is the installation directory selected by the user.
  ExecWait '"$INSTDIR\python_runtime\Python313\python.exe" "$INSTDIR\common\python\post_install.py"'
!macroend
