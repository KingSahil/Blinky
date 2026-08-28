#Requires -Version 5.1
<#
.SYNOPSIS
  One-click setup for Blinky on Windows.
.DESCRIPTION
  Installs JS deps (bun), Python venv, Playwright chromium, prepares .env,
  checks Rust/Docker/Ollama, and prints next steps. Does NOT inject API keys.
.NOTES
  Run: powershell -ExecutionPolicy Bypass -File setup.ps1
  Or:  .\setup.ps1   (if execution policy allows)
#>
$ErrorActionPreference = "Stop"

# -- helpers ---------------------------------------------------------------
function Write-Step($msg)  { Write-Host "`n[STEP] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg)   { Write-Host "  [ERR] $msg" -ForegroundColor Red }
function Fail($msg, $hint) {
  Write-Host "`n[ERROR] $msg" -ForegroundColor Red
  if ($hint) { Write-Host "  Hint: $hint" -ForegroundColor Yellow }
  Write-Host "  Setup aborted. Fix the error above and re-run: powershell -ExecutionPolicy Bypass -File setup.ps1`n" -ForegroundColor Red
  exit 1
}

$RepoRoot = $PSScriptRoot
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location $RepoRoot
Write-Host "`n============================================================" -ForegroundColor Magenta
Write-Host "  Blinky - One-click Windows Setup" -ForegroundColor Magenta
Write-Host "  Repo: $RepoRoot" -ForegroundColor DarkGray
Write-Host "============================================================" -ForegroundColor Magenta

# ── 1. Prerequisites ─────────────────────────────────────────────────────
Write-Step "Checking prerequisites"

# Bun
$bunCmd = $null
$possibleBun = @(
  "C:\Users\$env:USERNAME\.bun\bin\bun.exe",
  "$env:USERPROFILE\.bun\bin\bun.exe",
  "C:\Program Files\bun\bun.exe"
)
$bunInPath = $false
try { $null = Get-Command bun -ErrorAction Stop; $bunInPath = $true; $bunCmd = "bun" } catch {}
if (-not $bunInPath) {
  foreach ($p in $possibleBun) {
    if (Test-Path $p) { $bunCmd = $p; $bunInPath = $true; break }
  }
}
if (-not $bunInPath) {
  Fail "Bun not found." "Install Bun: powershell -c `"irm bun.sh/install.ps1 | iex`" then restart terminal. See https://bun.sh"
}
try { $bunVer = & $bunCmd --version 2>&1 | Out-String; $bunVer = $bunVer.Trim(); Write-Ok "Bun $bunVer ($bunCmd)" } catch { Fail "Bun found but failed to run: $_" }

# Rust / Cargo
try { $cargoVer = cargo --version 2>&1 | Out-String; if ($LASTEXITCODE -eq 0) { Write-Ok "$($cargoVer.Trim())" } else { throw } } catch {
  Write-Warn "Cargo/Rust not found. Required for Tauri."
  Write-Host "    Install: https://rustup.rs -> `winget install Rustlang.Rustup` or https://win.rustup.rs" -ForegroundColor DarkGray
  Write-Host "    Continuing anyway (bun install will still work, but 'bun run dev' will fail without Rust)." -ForegroundColor DarkGray
}

# Python 3.11+
Write-Step "Detecting Python 3.11+"
$pyCandidates = @(
  @{ cmd = "py"; args = @("-3.13") },
  @{ cmd = "py"; args = @("-3.12") },
  @{ cmd = "py"; args = @("-3.11") },
  @{ cmd = "python"; args = @() },
  @{ cmd = "python3"; args = @() }
)
$PythonExe = $null
$PythonVersion = $null
foreach ($c in $pyCandidates) {
  try {
    $out = & $c.cmd @($c.args) --version 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0 -and $out -match "Python\s+3\.(\d+)\.(\d+)") {
      $minor = [int]$Matches[1]
      if ($minor -ge 11) {
        # Verify it actually works by resolving full path
        $verOut = & $c.cmd @($c.args) -c "import sys; print(sys.executable)" 2>&1 | Out-String
        if ($verOut) {
          $PythonExe = "$($c.cmd) $($c.args -join ' ')".Trim()
          $PythonVersion = $out.Trim()
          # For `py -3.x` we keep the launcher form; for direct exe we resolve
          if ($c.cmd -in @("python","python3")) {
            $PythonExe = (Get-Command $c.cmd -ErrorAction SilentlyContinue).Source
          }
          break
        }
      }
    }
  } catch {}
}
if (-not $PythonExe) {
  Fail "Python 3.11+ not found." "Install Python 3.11+ from https://python.org (check 'Add to PATH' + 'py launcher'). Then re-run."
}
Write-Ok "Found $PythonVersion via '$PythonExe'"

# Docker (optional)
try {
  $dockerVer = docker --version 2>&1 | Out-String
  if ($LASTEXITCODE -eq 0) { Write-Ok "$($dockerVer.Trim()) (optional, for SearXNG)" }
  else { throw }
} catch { Write-Warn "Docker not found (optional). SearXNG web search will be disabled. Install Docker Desktop: https://docker.com" }

# Ollama (optional)
try {
  $ollamaVer = ollama --version 2>&1 | Out-String
  if ($LASTEXITCODE -eq 0) { Write-Ok "$($ollamaVer.Trim()) (optional, for local inference)" }
  else { throw }
} catch { Write-Warn "Ollama not found (optional). Only needed if BLINKY_AI_PROVIDER=ollama. Install: https://ollama.com" }

# -- 2. bun install ------------------------------------------------------
Write-Step "Installing JS dependencies (bun install)"
if (-not (Test-Path "$RepoRoot\package.json")) { Fail "package.json not found in $RepoRoot" "Run this script from the repo root." }
try {
  $oldEAP = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $bunInstall = & $bunCmd install 2>&1 | Out-String
  $bunExit = $LASTEXITCODE
  $ErrorActionPreference = $oldEAP
  Write-Host $bunInstall
  if ($bunExit -ne 0) { throw "bun install exited with $bunExit" }
  Write-Ok "JS dependencies installed (bun install)"
} catch {
  $ErrorActionPreference = "Stop"
  Fail "bun install failed: $_" "Check your network, delete bun.lock + node_modules and retry. Ensure Bun 1.3+."
}

# ── 3. Python venv (.venv) ──────────────────────────────────────────────
Write-Step "Setting up Python virtual environment (.venv)"
$VenvPath = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
$RequirementsPath = Join-Path $RepoRoot "windows\requirements.txt"
if (-not (Test-Path $RequirementsPath)) { Fail "windows/requirements.txt not found at $RequirementsPath" }

if (-not (Test-Path $VenvPython)) {
  Write-Host "  Creating .venv with '$PythonExe'..." -ForegroundColor DarkGray
  try {
    $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    if ($PythonExe -like "py *") {
      $parts = $PythonExe -split " "
      & $parts[0] @($parts[1..($parts.Length-1)]) -m venv $VenvPath 2>&1 | Out-String | Write-Host
    } else {
      & $PythonExe -m venv $VenvPath 2>&1 | Out-String | Write-Host
    }
    $venExit = $LASTEXITCODE; $ErrorActionPreference = $oldEAP
    if ((-not (Test-Path $VenvPython)) -or ($venExit -ne 0)) { throw ".venv creation did not produce $VenvPython (exit $venExit)" }
    Write-Ok ".venv created at $VenvPath"
  } catch {
    $ErrorActionPreference = "Stop"
    Fail "Failed to create .venv: $_" "Try manually: $PythonExe -m venv .venv  and ensure venv module is installed (py -m ensurepip)."
  }
} else {
  Write-Ok ".venv already exists at $VenvPath"
}

# -- 4. pip + requirements + playwright ----------------------------------
Write-Step "Installing Python dependencies"
try {
  $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  & $VenvPython -m pip install --upgrade pip 2>&1 | Out-String | Write-Host
  $pipExit = $LASTEXITCODE; $ErrorActionPreference = $oldEAP
  if ($pipExit -ne 0) { throw "pip upgrade failed (exit $pipExit)" }
  Write-Ok "pip upgraded"
} catch { $ErrorActionPreference = "Stop"; Fail "pip upgrade failed: $_" "Check internet, or run: .\.venv\Scripts\python.exe -m pip install --upgrade pip" }

try {
  Write-Host "  Installing windows/requirements.txt (this may take 2-5 min)..." -ForegroundColor DarkGray
  $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  & $VenvPython -m pip install -r $RequirementsPath 2>&1 | Out-String | Write-Host
  $pipExit = $LASTEXITCODE; $ErrorActionPreference = $oldEAP
  if ($pipExit -ne 0) { throw "pip install -r failed with $pipExit" }
  Write-Ok "Python packages installed"
} catch { $ErrorActionPreference = "Stop"; Fail "pip install failed: $_" "Check windows/requirements.txt and your Python version (3.11+ required, 3.13 works). See error above." }

Write-Step "Installing Playwright Chromium"
try {
  $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  & $VenvPython -m playwright install chromium 2>&1 | Out-String | Write-Host
  $pwExit = $LASTEXITCODE; $ErrorActionPreference = $oldEAP
  if ($pwExit -ne 0) { throw "playwright install failed (exit $pwExit)" }
  Write-Ok "Playwright chromium installed"
} catch { $ErrorActionPreference = "Stop"; Fail "Playwright install failed: $_" "Try: .\.venv\Scripts\python.exe -m playwright install chromium" }

# ── 5. .env ──────────────────────────────────────────────────────────────
Write-Step "Preparing .env"
$EnvPath = Join-Path $RepoRoot ".env"
$EnvExample = Join-Path $RepoRoot ".env_example"
if (-not (Test-Path $EnvPath)) {
  if (Test-Path $EnvExample) {
    Copy-Item $EnvExample $EnvPath
    Write-Ok ".env created from .env_example"
  } elseif (Test-Path "$RepoRoot\common\.envexample") {
    Copy-Item "$RepoRoot\common\.envexample" $EnvPath
    Write-Ok ".env created from common/.envexample"
  } else {
    Set-Content -Path $EnvPath -Value "BLINKY_AI_PROVIDER=groq`nGROQ_API_KEY=`nSARVAM_API_KEY=`nBLINKY_SHORTCUT=Space`n"
    Write-Ok ".env created (minimal)"
  }
} else {
  Write-Ok ".env already exists (not overwritten)"
}

# -- 6. Typecheck (optional sanity) --------------------------------------
Write-Step "Sanity check (typecheck)"
try {
  $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  $tc = & $bunCmd run typecheck 2>&1 | Out-String
  $tcExit = $LASTEXITCODE; $ErrorActionPreference = $oldEAP
  if ($tcExit -eq 0) { Write-Ok "Typecheck passed" } else { Write-Warn "Typecheck warnings (non-blocking):`n$tc" }
} catch { $ErrorActionPreference = "Stop"; Write-Warn "Typecheck skipped: $_" }

# ── 7. Summary ───────────────────────────────────────────────────────────
Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host @"

Next steps (required):

  1) Configure API keys in .env (not auto-filled):
     - For Groq (recommended): set GROQ_API_KEY=gsk_... in .env
       Get key: https://console.groq.com -> API Keys -> Create
       Keep BLINKY_AI_PROVIDER=groq
     - For Gemini (via OpenAI compat):
       BLINKY_AI_PROVIDER=custom
       BLINKY_CUSTOM_URL=https://generativelanguage.googleapis.com/v1beta/openai/
       CUSTOM_API_KEY=your_gemini_key
       BLINKY_CUSTOM_MODEL=gemini-2.0-flash
     - For local Ollama:
       BLINKY_AI_PROVIDER=ollama
       Then: ollama pull gemma4:e4b

  2) (Optional) Start local web search (SearXNG):
     docker compose -f common/docker-compose.yml up -d
     -> http://localhost:8888
     Or skip: bun run dev:no-docker

  3) Run Blinky:
     bun run dev              # full (SearXNG + Tauri + Python)
     # Ensure Bun is in PATH: C:\Users\$env:USERNAME\.bun\bin\bun.exe
     # If 'bun' not recognized, restart terminal or run:
     #   `$env:PATH="C:\Users\$env:USERNAME\.bun\bin;`$env:PATH"

  4) Open Blinky:
     Hotkey: CTRL + SHIFT + SPACE (fallback CTRL + SHIFT + ENTER)

Troubleshooting:
  - bun not found      -> restart terminal, or irm bun.sh/install.ps1 | iex
  - cargo not found    -> install Rust: https://rustup.rs
  - Python 3.11+ missing -> https://python.org (check 'py launcher')
  - pip/playwright fail -> check internet, rerun setup.ps1 (idempotent)
  - Groq 429/TPM limit  -> wait 30s or switch to ollama/custom
  - Ollama not running -> ollama serve

Docs: README.md -> How to Run the Project
"@ -ForegroundColor White
Write-Host "  Setup log: rerun this script anytime (idempotent).`n" -ForegroundColor DarkGray
