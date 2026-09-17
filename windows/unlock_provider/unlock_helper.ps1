# BlinkyUnlock helper - runs as SYSTEM via scheduled task
# Calls tscon to reconnect the active console session (dismisses Win+L lock screen)
Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
public class K32 {
    [DllImport("kernel32.dll")]
    public static extern uint WTSGetActiveConsoleSessionId();
}
'@
$sessionId = [K32]::WTSGetActiveConsoleSessionId()
& "$env:SystemRoot\System32\tscon.exe" $sessionId '/dest:console'
