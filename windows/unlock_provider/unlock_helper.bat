@echo off
:: ============================================================
:: BlinkyUnlock Helper — runs as SYSTEM via scheduled task
:: Finds the active console session and reconnects it via tscon.
:: This dismisses Win+L lock screens without needing a password.
:: ============================================================
powershell.exe -NoProfile -WindowStyle Hidden -Command ^
"Add-Type -TypeDefinition 'using System.Runtime.InteropServices; public class K { [DllImport(""kernel32.dll"")]public static extern uint WTSGetActiveConsoleSessionId(); }' -ErrorAction Stop; & ([System.Environment]::SystemDirectory + '\\tscon.exe') ([K]::WTSGetActiveConsoleSessionId()) '/dest:console'"
