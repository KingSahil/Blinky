#Requires -Version 5.1
<#
.SYNOPSIS
  Blinky one-click setup for Windows -- installs everything, then you just run.
.DESCRIPTION
  Checks + auto-installs toolchain (Bun, Rust, Python), installs JS + Python
  deps, Playwright Chromium, prepares .env, installs mobile deps, runs a
  health-check, and prints exact next steps. Every failure prints a clear
  [ERROR] + Hint + the exact command to fix it.
.USAGE
  powershell -ExecutionPolicy Bypass -File setup.ps1
  .\setup.ps1 -Run              # setup + immediately run the app (bun run dev)
  .\setup.ps1 -Yes              # non-interactive: auto-install without prompting
  .\setup.ps1 -SkipMobile       # skip common/mobile deps (faster PC-only setup)
  One-click run (after setup):  .\run.ps1
  Mobile QR setup:              .\setup-mobile.ps1
#>
param(
  [switch]$Run,
  [switch]$Yes,
  [switch]$SkipMobile
)

$ErrorActionPreference = "Stop"
$Global:CurrentStep = "init"
$Global:SetupFailed = $false

# -- helpers ---------------------------------------------------------------
function Write-Step($msg)  { Write-Host "`n[STEP] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg)   { Write-Host "  [ERR] $msg" -ForegroundColor Red }
function Fail($msg, $hint, $fixCmd) {
  Write-Host "`n================================ ERROR ================================" -ForegroundColor Red
  Write-Host "[ERROR] Step '$Global:CurrentStep' failed:" -ForegroundColor Red
  Write-Host "        $msg" -ForegroundColor Red
  if ($hint)   { Write-Host "`n  Why: $hint" -ForegroundColor Yellow }
  if ($fixCmd) { Write-Host "  Fix and retry:`n    $fixCmd" -ForegroundColor White }
  Write-Host "`n  Setup aborted. Fix the error above, then re-run:" -ForegroundColor Red
  Write-Host "    powershell -ExecutionPolicy Bypass -File setup.ps1" -ForegroundColor White
  Write-Host "  This script is idempotent -- safe to re-run. Full log: setup.log`n" -ForegroundColor DarkGray
  Write-Host "======================================================================`n" -ForegroundColor Red
  $Global:SetupFailed = $true
  exit 1
}
function Confirm-AutoInstall($label) {
  if ($Yes) { return $true }
  try {
    $ans = Read-Host "  '$label' is missing. Auto-install now? [Y/n]"
    return ($ans -eq "" -or $ans -match "^[Yy]")
  } catch { return $false }
}
function Test-Cmd($name) {
  try { $null = Get-Command $name -ErrorAction Stop; return $true } catch { return $false }
}
function Refresh-Path {
  # Pick up installs (bun, cargo, py) without forcing a terminal restart.
  $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
  $user    = [Environment]::GetEnvironmentVariable("Path", "User")
  if ($machine -or $user) { $env:Path = "$machine;$user" }
  $bunHome = Join-Path $env:USERPROFILE ".bun\bin"
  if ((Test-Path $bunHome) -and ($env:Path -notlike "*$bunHome*")) { $env:Path = "$bunHome;$env:Path" }
  $cargoHome = Join-Path $env:USERPROFILE ".cargo\bin"
  if ((Test-Path $cargoHome) -and ($env:Path -notlike "*$cargoHome*")) { $env:Path = "$cargoHome;$env:Path" }
}

$RepoRoot = $PSScriptRoot
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location $RepoRoot

# Log everything to setup.log (in addition to console).
$LogFile = Join-Path $RepoRoot "setup.log"
try { Start-Transcript -Path $LogFile -Append -ErrorAction SilentlyContinue | Out-Null } catch {}

Write-Host "`n============================================================" -ForegroundColor Magenta
Write-Host "  Blinky - One-click Windows Setup" -ForegroundColor Magenta
Write-Host "  Repo: $RepoRoot" -ForegroundColor DarkGray
Write-Host "  Flags: Run=$Run Yes=$Yes SkipMobile=$SkipMobile" -ForegroundColor DarkGray
Write-Host "  Log:  $LogFile" -ForegroundColor DarkGray
Write-Host "============================================================" -ForegroundColor Magenta

# -- 1. Bun (auto-install) ------------------------------------------------
$Global:CurrentStep = "Bun 1.3+ (JS runtime)"
Write-Step "Checking Bun (required)"
$BunCmd = $null
function Find-Bun {
  if (Test-Cmd "bun") { return "bun" }
  foreach ($p in @("$env:USERPROFILE\.bun\bin\bun.exe", "C:\Users\$env:USERNAME\.bun\bin\bun.exe", "C:\Program Files\bun\bun.exe")) {
    if ($p -and (Test-Path $p)) { return $p }
  }
  return $null
}
$BunCmd = Find-Bun
if (-not $BunCmd) {
  Write-Warn "Bun not found in PATH."
  if (Confirm-AutoInstall "Bun") {
    Write-Host "  Installing Bun (https://bun.sh)..." -ForegroundColor DarkGray
    try {
      $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
      powershell -c "irm bun.sh/install.ps1 | iex" 2>&1 | Out-String | Write-Host
      $ErrorActionPreference = $oldEAP
    } catch { $ErrorActionPreference = "Stop"; Write-Warn "Bun installer output: $_" }
    Refresh-Path
    $BunCmd = Find-Bun
  }
}
if (-not $BunCmd) {
  Fail "Bun is required but was not found." `
    "Bun runs the desktop app, dev script, and mobile bundler. The installer was skipped or failed." `
    'powershell -c "irm bun.sh/install.ps1 | iex"  # then RESTART terminal, then re-run .\setup.ps1'
}
try {
  $bunVer = & $BunCmd --version 2>&1 | Out-String
  $bunVer = $bunVer.Trim()
  if ([string]::IsNullOrWhiteSpace($bunVer)) { throw "empty version" }
  Write-Ok "Bun $bunVer ($BunCmd)"
} catch {
  Fail "Bun found at '$BunCmd' but failed to run: $_" `
    "Corrupt install or antivirus quarantine." `
    'powershell -c "irm bun.sh/install.ps1 | iex"  # reinstall, restart terminal, re-run .\setup.ps1'
}

# -- 2. Rust / Cargo (auto-install attempt, blocking for `bun run dev`) ---
$Global:CurrentStep = "Rust/Cargo (Tauri)"
Write-Step "Checking Rust/Cargo (required for Tauri desktop shell)"
$HasCargo = Test-Cmd "cargo"
if (-not $HasCargo) { Refresh-Path; $HasCargo = Test-Cmd "cargo" }
if ($HasCargo) {
  try { Write-Ok "$((cargo --version 2>&1 | Out-String).Trim())" } catch { Write-Warn "cargo present but 'cargo --version' failed: $_" }
} else {
  Write-Warn "Cargo/Rust not found."
  $installed = $false
  if ((Test-Cmd "winget") -and (Confirm-AutoInstall "Rust via winget")) {
    Write-Host "  Installing Rust via winget (Rustlang.Rustup)..." -ForegroundColor DarkGray
    try {
      $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
      winget install --id Rustlang.Rustup -e --accept-source-agreements --accept-package-agreements 2>&1 | Out-String | Write-Host
      $ErrorActionPreference = $oldEAP
      Refresh-Path; $HasCargo = Test-Cmd "cargo"
      if ($HasCargo) { $installed = $true; Write-Ok "$((cargo --version 2>&1 | Out-String).Trim()) (just installed -- if 'bun run dev' still says cargo missing, restart terminal)" }
    } catch { $ErrorActionPreference = "Stop"; Write-Warn "winget Rust install failed: $_" }
  }
  if (-not $installed) {
    Write-Host "  [ERR] Rust is REQUIRED to run/build the Tauri app." -ForegroundColor Red
    Write-Host "  Hint: install manually, then re-run setup (idempotent):" -ForegroundColor Yellow
    Write-Host "    winget install Rustlang.Rustup   # or https://win.rustup.rs" -ForegroundColor White
    Write-Host "  Continuing setup (JS/Python steps) so you make progress, but 'bun run dev' WILL fail until Rust is installed." -ForegroundColor Yellow
  }
}

# -- 2b. Tauri Windows prerequisites (clear errors, non-blocking) ---------
$Global:CurrentStep = "Tauri Windows prerequisites"
Write-Step "Checking Tauri Windows prerequisites (WebView2 + MSVC)"
try {
  $wv = Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\ClientState\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" -ErrorAction SilentlyContinue
  if ($wv) { Write-Ok "WebView2 registry key present" }
  else { Write-Warn "WebView2 not detected. Tauri needs it. Install: https://developer.microsoft.com/microsoft-edge/webview2/ (Evergreen Standalone Installer)." }
} catch { Write-Warn "WebView2 check skipped: $_" }
$hasMsvc = (Test-Cmd "cl") -or (Test-Path "${env:ProgramFiles}\Microsoft Visual Studio") -or (Test-Path "${env:ProgramFiles(x86)}\Microsoft Visual Studio")
if ($hasMsvc) { Write-Ok "MSVC / Visual Studio detected" }
else {
  Write-Warn "MSVC C++ build tools not detected. Tauri build needs them."
  Write-Host "    Install: 'Visual Studio Build Tools' with 'Desktop development with C++' workload:" -ForegroundColor DarkGray
  Write-Host "    https://visualstudio.microsoft.com/downloads/ (Build Tools)  OR  winget install Microsoft.VisualStudio.2022.BuildTools" -ForegroundColor DarkGray
}

# -- 3. Python 3.11+ (auto-install attempt) -------------------------------
$Global:CurrentStep = "Python 3.11+"
Write-Step "Checking Python 3.11+ (required for AI/orchestrator daemon)"
$pyCandidates = @(
  @{ cmd = "py"; args = @("-3.13") },
  @{ cmd = "py"; args = @("-3.12") },
  @{ cmd = "py"; args = @("-3.11") },
  @{ cmd = "python"; args = @() },
  @{ cmd = "python3"; args = @() }
)
$PythonExe = $null; $PythonVersion = $null
foreach ($c in $pyCandidates) {
  try {
    $out = & $c.cmd @($c.args) --version 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0 -and $out -match "Python\s+3\.(\d+)") {
      if ([int]$Matches[1] -ge 11) {
        $PythonExe = "$($c.cmd) $($c.args -join ' ')".Trim()
        if ($c.cmd -in @("python", "python3")) { $PythonExe = (Get-Command $c.cmd -ErrorAction SilentlyContinue).Source }
        $PythonVersion = $out.Trim()
        break
      }
    }
  } catch {}
}
if (-not $PythonExe) {
  Write-Warn "Python 3.11+ not found."
  if ((Test-Cmd "winget") -and (Confirm-AutoInstall "Python 3.13 via winget")) {
    try {
      $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
      winget install --id Python.Python.3.13 -e --accept-source-agreements --accept-package-agreements 2>&1 | Out-String | Write-Host
      $ErrorActionPreference = $oldEAP
      Refresh-Path
      foreach ($c in $pyCandidates) {
        try {
          $out = & $c.cmd @($c.args) --version 2>&1 | Out-String
          if ($LASTEXITCODE -eq 0 -and $out -match "Python\s+3\.(\d+)") {
            if ([int]$Matches[1] -ge 11) {
              $PythonExe = "$($c.cmd) $($c.args -join ' ')".Trim()
              if ($c.cmd -in @("python", "python3")) { $PythonExe = (Get-Command $c.cmd -ErrorAction SilentlyContinue).Source }
              $PythonVersion = $out.Trim()
              break
            }
          }
        } catch {}
      }
    } catch { $ErrorActionPreference = "Stop"; Write-Warn "winget Python install failed: $_" }
  }
}
if (-not $PythonExe) {
  Fail "Python 3.11+ is required but was not found." `
    "The Python daemon (OCR, AI routing, automation) cannot run without it." `
    'winget install Python.Python.3.13  # check "Add to PATH" + "py launcher", RESTART terminal, re-run .\setup.ps1  (or https://python.org)'
}
Write-Ok "Found $PythonVersion via '$PythonExe'"

# Optional tools (never block).
$Global:CurrentStep = "Optional tools (Docker/Ollama/Node)"
Write-Step "Checking optional tools"
try {
  $dv = docker --version 2>&1 | Out-String
  if ($LASTEXITCODE -eq 0) { Write-Ok "$($dv.Trim()) -- enables local SearXNG search" } else { throw }
} catch { Write-Warn "Docker not found (optional). Without it, web search is disabled. Run with --no-docker or install Docker Desktop: https://docker.com" }
try {
  $ov = ollama --version 2>&1 | Out-String
  if ($LASTEXITCODE -eq 0) { Write-Ok "$($ov.Trim()) -- needed only if BLINKY_AI_PROVIDER=ollama (https://ollama.com)" } else { throw }
} catch { Write-Warn "Ollama not found (optional). Only needed for BLINKY_AI_PROVIDER=ollama. Install: https://ollama.com" }
if (Test-Cmd "node") { try { Write-Ok "Node $((node --version 2>&1 | Out-String).Trim()) (optional, helps Expo/mobile)" } catch {} }
else { Write-Warn "Node not found (optional). Bun covers most flows; install Node LTS if Expo/mobile acts up: https://nodejs.org" }

# -- 4. bun install (desktop) ---------------------------------------------
$Global:CurrentStep = "bun install (desktop JS deps)"
Write-Step "Installing desktop JS dependencies (bun install)"
if (-not (Test-Path "$RepoRoot\package.json")) { Fail "package.json not found in $RepoRoot." "You are not in the Blinky repo root." "cd <path-to-Blinky>  then re-run .\setup.ps1" }
try {
  $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  $out = & $BunCmd install 2>&1 | Out-String; $code = $LASTEXITCODE
  $ErrorActionPreference = $oldEAP
  Write-Host $out
  if ($code -ne 0) { throw "bun install exited with code $code. See output above." }
  Write-Ok "Desktop JS dependencies installed"
} catch {
  $ErrorActionPreference = "Stop"
  Fail "bun install failed: $_" "Usually network, locked files, or old Bun. Close editors/terminals locking node_modules." "bun --version  # need 1.3+`nRemove-Item -Recurse -Force node_modules, bun.lockb  # nuclear retry, then re-run .\setup.ps1"
}

# -- 5. Python venv + deps + Playwright -----------------------------------
$Global:CurrentStep = "Python .venv"
Write-Step "Setting up Python virtual environment (.venv)"
$VenvPath = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
$RequirementsPath = Join-Path $RepoRoot "windows\requirements.txt"
if (-not (Test-Path $RequirementsPath)) { Fail "windows/requirements.txt not found." "Repo checkout incomplete." "git pull  then re-run .\setup.ps1" }
if (-not (Test-Path $VenvPython)) {
  Write-Host "  Creating .venv with '$PythonExe'..." -ForegroundColor DarkGray
  try {
    $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    if ($PythonExe -like "py *") { $parts = $PythonExe -split " "; & $parts[0] @($parts[1..($parts.Length - 1)]) -m venv $VenvPath 2>&1 | Out-String | Write-Host }
    else { & $PythonExe -m venv $VenvPath 2>&1 | Out-String | Write-Host }
    $code = $LASTEXITCODE; $ErrorActionPreference = $oldEAP
    if ((-not (Test-Path $VenvPython)) -or ($code -ne 0)) { throw ".venv creation did not produce $VenvPython (exit $code)" }
    Write-Ok ".venv created at $VenvPath"
  } catch {
    $ErrorActionPreference = "Stop"
    Fail "Failed to create .venv: $_" "Missing venv module or broken Python install." "$PythonExe -m ensurepip --upgrade`n$PythonExe -m venv .venv --clear  # manual retry, then re-run .\setup.ps1"
  }
} else { Write-Ok ".venv already exists at $VenvPath" }

$Global:CurrentStep = "pip install (Python deps)"
Write-Step "Installing Python dependencies (may take 2-5 min)"
try {
  $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  & $VenvPython -m pip install --upgrade pip 2>&1 | Out-String | Write-Host
  if ($LASTEXITCODE -ne 0) { throw "pip upgrade exited with $LASTEXITCODE" }
  $ErrorActionPreference = $oldEAP
  Write-Ok "pip upgraded"
} catch { $ErrorActionPreference = "Stop"; Fail "pip upgrade failed: $_" "No internet or broken venv." ".\.venv\Scripts\python.exe -m pip install --upgrade pip  # manual retry" }
try {
  $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  & $VenvPython -m pip install -r $RequirementsPath 2>&1 | Out-String | Write-Host
  if ($LASTEXITCODE -ne 0) { throw "pip install -r exited with $LASTEXITCODE. See output above (often a C++ compiler or Python-version conflict)." }
  $ErrorActionPreference = $oldEAP
  Write-Ok "Python packages installed"
} catch { $ErrorActionPreference = "Stop"; Fail "Python deps failed: $_" "Check windows/requirements.txt vs Python version (3.11-3.13 best)." ".\.venv\Scripts\python.exe -m pip install -r windows\requirements.txt  # manual retry" }

$Global:CurrentStep = "Playwright Chromium"
Write-Step "Installing Playwright Chromium"
try {
  $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  & $VenvPython -m playwright install chromium 2>&1 | Out-String | Write-Host
  if ($LASTEXITCODE -ne 0) { throw "playwright install exited with $LASTEXITCODE" }
  $ErrorActionPreference = $oldEAP
  Write-Ok "Playwright Chromium installed"
} catch { $ErrorActionPreference = "Stop"; Fail "Playwright install failed: $_" "WhatsApp/browser automation needs this." ".\.venv\Scripts\python.exe -m playwright install chromium  # manual retry" }

# -- 6. .env --------------------------------------------------------------
$Global:CurrentStep = ".env"
Write-Step "Preparing .env (API keys are NEVER auto-filled)"
$EnvPath = Join-Path $RepoRoot ".env"
$EnvExample = Join-Path $RepoRoot ".env_example"
if (-not (Test-Path $EnvPath)) {
  if (Test-Path $EnvExample) { Copy-Item $EnvExample $EnvPath; Write-Ok ".env created from .env_example -- EDIT IT to add keys" }
  elseif (Test-Path "$RepoRoot\common\.envexample") { Copy-Item "$RepoRoot\common\.envexample" $EnvPath; Write-Ok ".env created from common/.envexample -- EDIT IT" }
  else { Set-Content -Path $EnvPath -Value "BLINKY_AI_PROVIDER=groq`nGROQ_API_KEY=`nSARVAM_API_KEY=`nBLINKY_SHORTCUT=Space`n"; Write-Ok ".env created (minimal) -- EDIT IT" }
} else { Write-Ok ".env already exists (not overwritten)" }
# Validate keys so the user gets a CLEAR message instead of a cryptic runtime 401.
try {
  $envText = Get-Content $EnvPath -Raw -ErrorAction SilentlyContinue
  $provider = if ($envText -match "BLINKY_AI_PROVIDER\s*=\s*(\w+)") { $Matches[1] } else { "groq" }
  $hasGroq = $envText -match "GROQ_API_KEY\s*=\s*gsk_"
  $hasAssembly = $envText -match "ASSEMBLY_AI_API_KEY\s*=\s*\S+"
  if ($provider -eq "groq" -and -not $hasGroq) {
    Write-Warn "GROQ_API_KEY is empty but BLINKY_AI_PROVIDER=groq. The app WILL start but AI answers will 401."
    Write-Host "    Fix: https://console.groq.com -> API Keys -> Create -> paste 'GROQ_API_KEY=gsk_...' into .env" -ForegroundColor DarkGray
  } elseif ($hasGroq) { Write-Ok "GROQ_API_KEY looks set" }
  if (-not $hasAssembly) { Write-Warn "ASSEMBLY_AI_API_KEY is empty -- voice features will fail until set (https://assemblyai.com)." }
} catch { Write-Warn "Could not validate .env: $_" }

# -- 7. Mobile deps (one-click includes phone path) -----------------------
if (-not $SkipMobile) {
  $Global:CurrentStep = "Mobile deps (common/mobile)"
  Write-Step "Installing mobile companion deps (common/mobile)"
  $MobileDir = Join-Path $RepoRoot "common\mobile"
  if (-not (Test-Path "$MobileDir\package.json")) {
    Write-Warn "common/mobile/package.json not found -- skipping mobile deps."
  } else {
    try {
      $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
      $out = & $BunCmd install --cwd $MobileDir 2>&1 | Out-String; $code = $LASTEXITCODE
      $ErrorActionPreference = $oldEAP
      Write-Host $out
      if ($code -ne 0) { throw "mobile bun install exited with $code" }
      Write-Ok "Mobile deps installed. Run mobile QR setup: .\setup-mobile.ps1"
    } catch {
      $ErrorActionPreference = "Stop"
      Write-Warn "Mobile deps failed (non-blocking for desktop): $_"
      Write-Host "    Fix: cd common\mobile; bun install; then .\setup-mobile.ps1" -ForegroundColor DarkGray
    }
  }
} else { Write-Step "Skipping mobile deps (-SkipMobile)"; Write-Warn "Mobile skipped. Run later: .\setup-mobile.ps1" }

# -- 8. Typecheck (non-blocking sanity) -----------------------------------
$Global:CurrentStep = "typecheck"
Write-Step "Sanity check (typecheck, non-blocking)"
try {
  $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  $tc = & $BunCmd run typecheck 2>&1 | Out-String; $code = $LASTEXITCODE
  $ErrorActionPreference = $oldEAP
  if ($code -eq 0) { Write-Ok "Typecheck passed" } else { Write-Warn "Typecheck warnings (app will still run):`n$tc" }
} catch { $ErrorActionPreference = "Stop"; Write-Warn "Typecheck skipped: $_" }

# -- 9. Doctor summary ----------------------------------------------------
$Global:CurrentStep = "doctor"
Write-Step "Doctor -- what's ready, what's not"
$rows = @()
$rows += [pscustomobject]@{ Component = "Bun"; Status = if ($BunCmd) { "READY ($((& $BunCmd --version 2>&1 | Out-String).Trim())" } else { "MISSING" } }
$rows += [pscustomobject]@{ Component = "Rust/Cargo"; Status = if (Test-Cmd "cargo") { "READY" } else { "MISSING (bun run dev will fail)" } }
$rows += [pscustomobject]@{ Component = "Python venv"; Status = if (Test-Path $VenvPython) { "READY" } else { "MISSING" } }
$rows += [pscustomobject]@{ Component = ".env keys"; Status = "CHECK WARNINGS ABOVE (GROQ/AssemblyAI)" }
$rows += [pscustomobject]@{ Component = "Mobile deps"; Status = if ($SkipMobile) { "SKIPPED" } elseif (Test-Path "$RepoRoot\common\mobile\node_modules") { "READY" } else { "run .\setup-mobile.ps1" } }
$rows | Format-Table -AutoSize | Out-String | Write-Host

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "  Setup complete! One-click run:" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host @"

  RUN THE APP (pick one):
    .\run.ps1                  # one-click run (checks deps, picks docker/no-docker)
    bun run dev                # full (SearXNG + Tauri + Python)
    bun run dev:no-docker      # skip Docker/SearXNG (no web search)

  MOBILE (phone remote + QR):
    .\setup-mobile.ps1         # installs mobile deps, prints LAN IP + QR flow
    # Then in the Expo terminal: scan QR with Expo Go / dev build.
    # Phone + PC must be on the SAME Wi-Fi (or use USB: adb reverse, see script).

  CONFIGURE KEYS (.env -- required before AI works):
    GROQ_API_KEY=gsk_...       # https://console.groq.com -> API Keys
    ASSEMBLY_AI_API_KEY=...    # https://assemblyai.com (voice)
    BLINKY_AI_PROVIDER=groq    # or: custom / ollama

  HOTKEYS:  CTRL + SHIFT + SPACE  (fallback CTRL + SHIFT + ENTER)

  TROUBLESHOOTING (exact fixes):
    bun missing      -> powershell -c "irm bun.sh/install.ps1 | iex", restart terminal
    cargo missing    -> winget install Rustlang.Rustup  (restart terminal)
    python missing   -> winget install Python.Python.3.13  (tick Add-to-PATH)
    WebView2 missing -> https://developer.microsoft.com/microsoft-edge/webview2/
    MSVC missing     -> Visual Studio Build Tools + "Desktop development with C++"
    pip fail         -> .\.venv\Scripts\python.exe -m pip install -r windows\requirements.txt
    401 from Groq    -> .env GROQ_API_KEY empty or wrong; paste gsk_... key
    ports busy       -> .\run.ps1 clears dev ports automatically

  Docs: README.md -> Getting Started. Log: setup.log (idempotent -- safe to re-run).
"@ -ForegroundColor White

try { Stop-Transcript -ErrorAction SilentlyContinue | Out-Null } catch {}

if ($Run) {
  if ($Global:SetupFailed) { exit 1 }
  Write-Step "One-click run requested (-Run): launching Blinky"
  if (-not (Test-Cmd "cargo")) {
    Fail "Cannot -Run: Rust/Cargo still missing." "Install Rust first, otherwise Tauri cannot start." "winget install Rustlang.Rustup  # restart terminal, re-run .\setup.ps1 -Run"
  }
  $useNoDocker = $false
  try { docker info 2>&1 | Out-Null; if ($LASTEXITCODE -ne 0) { $useNoDocker = $true } } catch { $useNoDocker = $true }
  if ($useNoDocker) { Write-Warn "Docker daemon not running -- launching with --no-docker (no web search)."; & $BunCmd run dev:no-docker }
  else { & $BunCmd run dev }
}
