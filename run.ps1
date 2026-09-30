#Requires -Version 5.1
<#
.SYNOPSIS
  Blinky one-click run (Windows). Validates setup, then launches the app.
.USAGE
  powershell -ExecutionPolicy Bypass -File run.ps1
  .\run.ps1                    # full (auto-falls back to --no-docker if needed)
  .\run.ps1 -NoDocker          # force skip Docker/SearXNG
  .\run.ps1 -NoMobile          # skip USB-mobile autodetect (pass to dev script)
  Any failure prints [ERROR] + exact fix command.
#>
param([switch]$NoDocker, [switch]$NoMobile)
$ErrorActionPreference = "Stop"
function Write-Step($m){ Write-Host "`n[STEP] $m" -ForegroundColor Cyan }
function Write-Ok($m){ Write-Host "  [OK] $m" -ForegroundColor Green }
function Write-Warn($m){ Write-Host "  [WARN] $m" -ForegroundColor Yellow }
function Fail($msg,$hint,$fix){
  Write-Host "`n================================ ERROR ================================" -ForegroundColor Red
  Write-Host "[ERROR] $msg" -ForegroundColor Red
  if($hint){ Write-Host "`n  Why: $hint" -ForegroundColor Yellow }
  if($fix){ Write-Host "  Fix and retry:`n    $fix" -ForegroundColor White }
  Write-Host "`n  Run aborted. Fix above, then re-run: .\run.ps1`n" -ForegroundColor Red
  exit 1
}
function Test-Cmd($n){ try{ $null=Get-Command $n -ErrorAction Stop; return $true }catch{ return $false } }

$RepoRoot=$PSScriptRoot; if(-not $RepoRoot){ $RepoRoot=Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location $RepoRoot
Write-Host "`n  Blinky - One-click Run (Windows)  |  Repo: $RepoRoot" -ForegroundColor Magenta

# Resolve bun (incl. default install path without restart).
$BunCmd=$null
if(Test-Cmd "bun"){ $BunCmd="bun" }
foreach($p in @("$env:USERPROFILE\.bun\bin\bun.exe")){ if((-not $BunCmd)-and (Test-Path $p)){ $BunCmd=$p } }
if(-not $BunCmd){ Fail "Bun not found. Setup did not complete." "One-click setup installs Bun first." 'powershell -ExecutionPolicy Bypass -File setup.ps1  # then .\run.ps1' }

Write-Step "Pre-flight checks"
if(-not (Test-Path "$RepoRoot\package.json")){ Fail "package.json missing in $RepoRoot." "Wrong folder." "cd <path-to-Blinky>  then .\run.ps1" }
if(-not (Test-Path "$RepoRoot\node_modules")){ Fail "node_modules missing. Dependencies were never installed." "Run setup once." 'powershell -ExecutionPolicy Bypass -File setup.ps1  # then .\run.ps1' }
else{ Write-Ok "node_modules present" }
$VenvPython="$RepoRoot\.venv\Scripts\python.exe"
if(-not (Test-Path $VenvPython)){ Fail "Python .venv missing at $VenvPython." "Run setup once." 'powershell -ExecutionPolicy Bypass -File setup.ps1  # then .\run.ps1' }
else{ Write-Ok ".venv present" }
if(-not (Test-Cmd "cargo")){
  $cargoHome=Join-Path $env:USERPROFILE ".cargo\bin"; if((Test-Path $cargoHome)-and($env:Path -notlike "*$cargoHome*")){ $env:Path="$cargoHome;$env:Path" }
}
if(-not (Test-Cmd "cargo")){ Fail "Rust/Cargo not found. Tauri cannot start." "Setup warns about this; install Rust." "winget install Rustlang.Rustup  # restart terminal, then .\run.ps1" }
else{ Write-Ok "$((cargo --version 2>&1 | Out-String).Trim())" }
if(-not (Test-Path "$RepoRoot\.env")){ Fail ".env missing. API keys/config were never created." "Run setup once." 'powershell -ExecutionPolicy Bypass -File setup.ps1  # then edit .env, then .\run.ps1' }
else{
  Write-Ok ".env present"
  $t=Get-Content "$RepoRoot\.env" -Raw -ErrorAction SilentlyContinue
  if(($t -match "BLINKY_AI_PROVIDER\s*=\s*groq")-and($t -notmatch "GROQ_API_KEY\s*=\s*gsk_")){
    Write-Warn "GROQ_API_KEY empty with provider=groq: app starts but AI answers 401. Fix: paste gsk_... key into .env (https://console.groq.com)."
  }
}

# Clear stale listeners on dev ports (common "port in use" confusion).
Write-Step "Clearing stale dev ports (5173, 9001, 9002, 8081)"
try{
  $cmd='Get-NetTCPConnection -State Listen -LocalPort 5173,9001,9002,8081 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | Sort-Object -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }'
  powershell -NoProfile -Command $cmd 2>$null | Out-Null
  Write-Ok "Dev ports cleared (if anything was stale)"
}catch{ Write-Warn "Port cleanup skipped: $_" }

# Pick docker vs no-docker automatically.
$useNoDocker=$NoDocker.IsPresent
if(-not $useNoDocker){
  try{ docker info 2>&1 | Out-Null; if($LASTEXITCODE -ne 0){ $useNoDocker=$true } }catch{ $useNoDocker=$true }
  if($useNoDocker){ Write-Warn "Docker daemon not running: launching WITHOUT SearXNG web search. Start Docker Desktop to enable search." }
  else{ Write-Ok "Docker daemon running: SearXNG search enabled" }
}

Write-Step "Launching Blinky (Ctrl+C to stop)"
Write-Host "  Hotkeys: CTRL + SHIFT + SPACE  (fallback CTRL + SHIFT + ENTER)" -ForegroundColor DarkGray
Write-Host "  Mobile:  .\setup-mobile.ps1  (QR + USB flow, phone remote)" -ForegroundColor DarkGray
$args2=@("run"); if($useNoDocker){ $args2+=@("dev:no-docker") } else{ $args2+=@("dev") }
if($NoMobile){ $args2+=@("--","--no-mobile") }
try{ & $BunCmd @args2 }
catch{ Fail "Failed to launch: $_" "See error above (often Rust build error = missing MSVC/WebView2, or port conflict)." '.\run.ps1  # retry  |  powershell -ExecutionPolicy Bypass -File setup.ps1  # repair' }
