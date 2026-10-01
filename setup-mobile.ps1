#Requires -Version 5.1
<#
.SYNOPSIS
  Blinky mobile one-click setup (Windows) -- installs deps, prints LAN IP, starts Expo QR.
.USAGE
  powershell -ExecutionPolicy Bypass -File setup-mobile.ps1
  .\setup-mobile.ps1 -Tunnel     # use ngrok tunnel when phone+PC are on different networks
  .\setup-mobile.ps1 -Usb        # USB mode: adb reverse + localhost (no Wi-Fi needed)
  .\setup-mobile.ps1 -Clear      # start Metro with cache cleared (expo start -c)
  Flow: 1) run desktop first (.\run.ps1)  2) run this script  3) scan QR  4) enter PC IP, tap Establish Link.
#>
param([switch]$Tunnel, [switch]$Usb, [switch]$Clear)
$ErrorActionPreference = "Stop"
function Write-Step($m){ Write-Host "`n[STEP] $m" -ForegroundColor Cyan }
function Write-Ok($m){ Write-Host "  [OK] $m" -ForegroundColor Green }
function Write-Warn($m){ Write-Host "  [WARN] $m" -ForegroundColor Yellow }
function Fail($msg,$hint,$fix){
  Write-Host "`n================================ ERROR ================================" -ForegroundColor Red
  Write-Host "[ERROR] $msg" -ForegroundColor Red
  if($hint){ Write-Host "`n  Why: $hint" -ForegroundColor Yellow }
  if($fix){ Write-Host "  Fix and retry:`n    $fix" -ForegroundColor White }
  Write-Host "`n  Mobile setup aborted. Fix above, then re-run: .\setup-mobile.ps1`n" -ForegroundColor Red
  exit 1
}
function Test-Cmd($n){ try{ $null=Get-Command $n -ErrorAction Stop; return $true }catch{ return $false } }

$RepoRoot=$PSScriptRoot; if(-not $RepoRoot){ $RepoRoot=Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location $RepoRoot
$MobileDir=Join-Path $RepoRoot "common\mobile"
Write-Host "`n============================================================" -ForegroundColor Magenta
Write-Host "  Blinky - Mobile One-click Setup (Windows)" -ForegroundColor Magenta
Write-Host "  Mobile dir: $MobileDir" -ForegroundColor DarkGray
Write-Host "============================================================" -ForegroundColor Magenta

if(-not (Test-Path "$MobileDir\package.json")){ Fail "common/mobile/package.json not found." "Run from the Blinky repo root; checkout may be incomplete." "cd <path-to-Blinky>  then .\setup-mobile.ps1" }

# Resolve bun.
$BunCmd=$null
if(Test-Cmd "bun"){ $BunCmd="bun" }
foreach($p in @("$env:USERPROFILE\.bun\bin\bun.exe")){ if((-not $BunCmd)-and (Test-Path $p)){ $BunCmd=$p } }
if(-not $BunCmd){ Fail "Bun not found." "Mobile bundler runs on Bun/Expo." 'powershell -ExecutionPolicy Bypass -File setup.ps1  # then .\setup-mobile.ps1' }

Write-Step "Installing mobile dependencies (common/mobile)"
try{
  $oldEAP=$ErrorActionPreference; $ErrorActionPreference="Continue"
  $out=& $BunCmd install --cwd $MobileDir 2>&1 | Out-String; $code=$LASTEXITCODE
  $ErrorActionPreference=$oldEAP; Write-Host $out
  if($code -ne 0){ throw "bun install exited with $code" }
  Write-Ok "Mobile deps installed"
}catch{ $ErrorActionPreference="Stop"; Fail "Mobile bun install failed: $_" "Usually network or old Bun." "cd common\mobile; bun install  # manual retry" }

# Expo CLI check (clear error: bunx expo vs missing install).
Write-Step "Checking Expo CLI"
$expoOk=$false
try{
  $oldEAP=$ErrorActionPreference; $ErrorActionPreference="Continue"
  $ev=& $BunCmd x expo --version 2>&1 | Out-String; $code=$LASTEXITCODE
  $ErrorActionPreference=$oldEAP
  if($code -eq 0 -and ($ev -match "\d+\.\d+")){ $expoOk=$true; Write-Ok "Expo $($ev.Trim())" }
  else{ throw $ev }
}catch{
  $ErrorActionPreference="Stop"
  Write-Warn "Expo CLI check failed (non-blocking; 'bun run start' will fetch it): $($_.Exception.Message)"
  Write-Host "    If Metro fails to start, fix with: cd common\mobile; bun install; bunx expo --version" -ForegroundColor DarkGray
}

# Desktop backend check: port 9001 should be listening (bun run dev).
Write-Step "Checking desktop backend (port 9001)"
$pcRunning=$false
try{
  $tcp=New-Object Net.Sockets.TcpClient
  $iar=$tcp.BeginConnect("127.0.0.1",9001,$null,$null)
  if($iar.AsyncWaitHandle.WaitOne(1200)){ $tcp.EndConnect($iar); $pcRunning=$true }
  $tcp.Close()
}catch{}
if($pcRunning){ Write-Ok "Desktop backend reachable on 127.0.0.1:9001" }
else{
  Write-Warn "Desktop backend NOT reachable on port 9001."
  Write-Host "    The phone remote-controls the PC via the DESKTOP pipeline (same CommandBar executor)." -ForegroundColor DarkGray
  Write-Host "    Start it first in another terminal:  .\run.ps1  (or: bun run dev)" -ForegroundColor White
  Write-Host "    Continuing anyway so you can still scan the QR and prepare the phone." -ForegroundColor DarkGray
}

# Print LAN IPv4s so user knows what to type as "PC IP" + Establish Link.
Write-Step "Your PC IP (type this in the phone app, then Establish Link)"
try{
  $ips=Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.PrefixOrigin -ne "WellKnown" } | Select-Object -ExpandProperty IPAddress -Unique
  if($ips){ foreach($ip in $ips){ Write-Host "  PC IP: $ip :9001" -ForegroundColor Green } }
  else{ Write-Warn "No LAN IPv4 found. Are you on Wi-Fi?" }
}catch{ Write-Warn "Could not enumerate IPs (ipconfig fallback): $_"; try{ ipconfig | Select-String "IPv4" | ForEach-Object { Write-Host "  $_" -ForegroundColor Green } }catch{} }

# USB mode: adb reverse so phone uses 'localhost'.
if($Usb){
  Write-Step "USB mode: adb reverse tcp:9001/9002/9004/8081"
  $adb=$null
  if(Test-Cmd "adb"){ $adb="adb" }
  foreach($p in @("$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe","$env:LOCALAPPDATA\Android\platform-tools\adb.exe")){ if((-not $adb)-and (Test-Path $p)){ $adb=$p } }
  if($env:ANDROID_HOME -and (Test-Path "$env:ANDROID_HOME\platform-tools\adb.exe")){ $adb="$env:ANDROID_HOME\platform-tools\adb.exe" }
  if(-not $adb){ Fail "adb.exe not found (needed for -Usb)." "Install Android SDK Platform Tools and enable USB debugging on the phone." "winget install Google.AndroidSDKPlatformTools  # or https://developer.android.com/tools/adb, then .\setup-mobile.ps1 -Usb" }
  try{
    foreach($port in @(9001,9002,9004,8081)){ & $adb reverse "tcp:$port" "tcp:$port" 2>&1 | Out-String | Write-Host }
    Write-Ok "USB reverse routing done. In the phone app use IP: localhost"
  }catch{ Fail "adb reverse failed: $_" "Phone not connected / USB debugging off / authorization prompt not accepted." "1) enable Developer Options > USB debugging  2) accept RSA prompt on phone  3) adb devices  4) re-run .\setup-mobile.ps1 -Usb" }
}

# Firewall hint for port 9001 (phone must reach PC).
Write-Step "Firewall note (phone must reach PC :9001)"
Write-Host "  If the phone cannot connect, allow TCP 9001 inbound:" -ForegroundColor DarkGray
Write-Host '    New-NetFirewallRule -DisplayName "Blinky Mobile 9001" -Direction Inbound -LocalPort 9001 -Protocol TCP -Action Allow' -ForegroundColor DarkGray
Write-Host "  Or run: common\mobile\allow_firewall.bat (admin)" -ForegroundColor DarkGray

# Launch Expo: QR prints automatically. --host lan is the reliable default.
Write-Step "Starting Expo (QR prints below -- scan it)"
$expoArgs=@("run","start","--","--host","lan")
if($Tunnel){ $expoArgs=@("run","start","--","--tunnel"); Write-Warn "Tunnel mode: uses ngrok (slower, needs @expo/ngrok + internet). Same-Wi-Fi LAN is faster." }
if($Clear){ $expoArgs+=@("-c"); Write-Host "  Cache clear requested (-Clear)." -ForegroundColor DarkGray }
Write-Host ""
Write-Host "  ================= PHONE TEST FLOW (what the devs implemented) =================" -ForegroundColor Green
Write-Host "  1) Scan the QR below with Expo Go (or open it in your Blinky dev build)." -ForegroundColor White
Write-Host "     NOTE: full app needs the custom dev build (native modules). If you see" -ForegroundColor Yellow
Write-Host "     'Cannot find native module ExponentImagePicker', you are in Expo Go or an" -ForegroundColor Yellow
Write-Host "     old build: rebuild via EAS (see common/mobile/README.md) and reopen." -ForegroundColor Yellow
Write-Host "  2) Phone + PC must be on the SAME Wi-Fi (or -Usb mode with IP 'localhost')." -ForegroundColor White
Write-Host "  3) In the app: QR tab (default) - scan the pairing code from the PC app" -ForegroundColor White
Write-Host "     (PC app header -> QR icon). Or Manual tab: enter PC IP (printed above)," -ForegroundColor White
Write-Host "     tap 'Establish Link'." -ForegroundColor White
Write-Host "  4) Test: Power (Sleep/Restart/Shutdown), remote AI query over WS :9001," -ForegroundColor White
Write-Host "     file transfer to a PC folder, camera-roll sync. Mobile just transmits;" -ForegroundColor White
Write-Host "     execution uses the SAME PC CommandBar pipeline/coordinates." -ForegroundColor White
Write-Host "  Metro keys: r = reload, m = dev menu, a = open app, Ctrl+C = stop." -ForegroundColor DarkGray
Write-Host "  =============================================================================" -ForegroundColor Green
Write-Host ""
try{ & $BunCmd $expoArgs --cwd $MobileDir }
catch{ Fail "Expo failed to start: $_" "See error above (common: port 8081 busy, or native-module mismatch)." "cd common\mobile; bun run start:clear  # manual retry. If 8081 busy: close old Metro first." }
