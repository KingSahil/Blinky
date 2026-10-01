#!/usr/bin/env bash
# Blinky - One-click Linux Setup (installs everything, then you just run).
#
# Usage:
#   chmod +x setup.sh && ./setup.sh
#   ./setup.sh --run           # setup + immediately run the app (bun run dev)
#   ./setup.sh --yes           # non-interactive: auto-install without prompting
#   ./setup.sh --skip-mobile   # skip common/mobile deps (faster PC-only setup)
# One-click run (after setup):  ./run.sh
# Mobile QR setup:              ./setup-mobile.sh
#
# Every failure prints: [ERROR] + why + exact fix command. Idempotent: safe to re-run.
# Logs to setup.log. Does NOT inject API keys.
set -u
set -o pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; MAGENTA='\033[0;35m'; NC='\033[0m'
STEP="init"
RUN_APP=0; ASSUME_YES=0; SKIP_MOBILE=0
for arg in "$@"; do
  case "$arg" in
    --run) RUN_APP=1 ;;
    --yes|--non-interactive) ASSUME_YES=1 ;;
    --skip-mobile) SKIP_MOBILE=1 ;;
    --help|-h)
      echo "Usage: ./setup.sh [--run] [--yes] [--skip-mobile]"
      echo "  --run          setup + launch 'bun run dev' at the end"
      echo "  --yes          auto-install missing tools without prompting"
      echo "  --skip-mobile  skip common/mobile deps"
      exit 0 ;;
    *) echo -e "${YELLOW}! Unknown flag: $arg (try --help)${NC}" ;;
  esac
done

step()    { echo -e "\n${CYAN}[STEP] $*${NC}"; STEP="$*"; }
ok()      { echo -e "  ${GREEN}+ $*${NC}"; }
warn()    { echo -e "  ${YELLOW}! $*${NC}"; }
fail() {
  echo -e "\n${RED}================================ ERROR ================================${NC}"
  echo -e "${RED}[ERROR] Step '$STEP' failed:${NC}"
  echo -e "${RED}        $1${NC}"
  if [ -n "${2:-}" ]; then echo -e "\n  ${YELLOW}Why: $2${NC}"; fi
  if [ -n "${3:-}" ]; then echo -e "  Fix and retry:\n    $3"; fi
  echo -e "\n  ${RED}Setup aborted. Fix above, then re-run: ./setup.sh${NC}"
  echo -e "  ${YELLOW}Idempotent -- safe to re-run. Full log: setup.log${NC}\n"
  exit 1
}
confirm_install() { # $1 = label -> returns 0 if yes
  if [ "$ASSUME_YES" = "1" ]; then return 0; fi
  if [ ! -t 0 ]; then return 1; fi
  printf "  '%s' is missing. Auto-install now? [Y/n] " "$1"
  read -r ans || return 1
  case "$ans" in ""|[Yy]*) return 0 ;; *) return 1 ;; esac
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"
exec > >(tee -a setup.log) 2>&1
echo -e "${MAGENTA}============================================================${NC}"
echo -e "${MAGENTA}  Blinky - One-click Linux Setup${NC}"
echo -e "${MAGENTA}  Repo: $REPO_ROOT  Flags: run=$RUN_APP yes=$ASSUME_YES skip_mobile=$SKIP_MOBILE${NC}"
echo -e "${MAGENTA}============================================================${NC}"

# -- 1. Bun (auto-install) ------------------------------------------------
step "Checking Bun 1.3+ (required)"
if ! command -v bun >/dev/null 2>&1; then
  if [ -f "$HOME/.bun/bin/bun" ]; then
    export PATH="$HOME/.bun/bin:$PATH"
    ok "Bun found at ~/.bun/bin/bun ($(bun --version))"
  elif confirm_install "Bun"; then
    echo "  Installing Bun from https://bun.sh..."
    curl -fsSL https://bun.sh/install | bash \
      || fail "Bun installer failed." "No network or curl blocked." "curl -fsSL https://bun.sh/install | bash   # then: export PATH=\"\$HOME/.bun/bin:\$PATH\" and re-run ./setup.sh"
    export PATH="$HOME/.bun/bin:$PATH"
    command -v bun >/dev/null 2>&1 \
      || fail "Bun installed but not on PATH." "Shell hasn't picked up ~/.bun/bin." "export PATH=\"\$HOME/.bun/bin:\$PATH\"   then re-run ./setup.sh (or restart terminal)"
    ok "Bun $(bun --version) (just installed)"
  else
    fail "Bun is required but was not found." "Bun runs the desktop app, dev script, and mobile bundler." "curl -fsSL https://bun.sh/install | bash   then restart terminal and re-run ./setup.sh (https://bun.sh)"
  fi
else
  ok "Bun $(bun --version) ($(command -v bun))"
fi

# -- 2. Rust/Cargo (auto-install attempt) ---------------------------------
step "Checking Rust/Cargo (required for Tauri)"
if command -v cargo >/dev/null 2>&1; then
  ok "$(cargo --version)"
else
  warn "Cargo/Rust not found."
  if confirm_install "Rust via rustup"; then
    echo "  Installing Rust via rustup.rs (stable toolchain)..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
      || warn "rustup install failed -- see output above."
    # shellcheck disable=SC1091
    [ -f "$HOME/.cargo/env" ] && source "$HOME/.cargo/env"
    export PATH="$HOME/.cargo/bin:$PATH"
  fi
  if command -v cargo >/dev/null 2>&1; then
    ok "$(cargo --version) (just installed -- if 'bun run dev' still says cargo missing, restart terminal)"
  else
    echo -e "  ${RED}[ERR] Rust is REQUIRED to run/build the Tauri app.${NC}"
    echo -e "  ${YELLOW}Hint: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh  (or: sudo pacman -S rust / sudo apt install cargo)${NC}"
    echo -e "  ${YELLOW}Continuing setup so JS/Python still install, but 'bun run dev' WILL fail until Rust exists.${NC}"
  fi
fi

# -- 2b. Tauri Linux system libs (clear errors, non-blocking) -------------
step "Checking Tauri Linux system libraries"
MISSING_SYS=""
for lib in webkit2gtk-4.1 libayatana-appindicator pkg-config libssl; do :; done
if command -v pkg-config >/dev/null 2>&1; then ok "pkg-config present"; else warn "pkg-config missing. Ubuntu: sudo apt install pkg-config build-essential libssl-dev libgtk-3-dev libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev"; MISSING_SYS="$MISSING_SYS pkg-config"; fi
if pkg-config --exists webkit2gtk-4.1 2>/dev/null || pkg-config --exists webkit2gtk-4.0 2>/dev/null; then ok "webkit2gtk present"; else warn "webkit2gtk missing (Tauri needs it). Ubuntu: sudo apt install libwebkit2gtk-4.1-dev | Arch: sudo pacman -S webkit2gtk-4.1"; fi
if [ -n "$MISSING_SYS" ]; then warn "Install the packages above before 'bun run dev', or the Rust build will fail with 'library not found'."; fi

# -- 3. Python 3.11+ ------------------------------------------------------
step "Checking Python 3.11+ (required)"
PYTHON_BIN=""
for cand in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" -c "import sys; exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
      PYTHON_BIN="$cand"; break
    fi
  fi
done
if [ -z "$PYTHON_BIN" ]; then
  fail "Python 3.11+ is required but was not found." "The Python daemon (OCR, AI routing, automation) cannot run without it." "Ubuntu: sudo apt install python3.11 python3-venv python3-pip   Arch: sudo pacman -S python   (https://python.org) then re-run ./setup.sh"
fi
ok "Found $($PYTHON_BIN --version) via $PYTHON_BIN"
"$PYTHON_BIN" -m venv --help >/dev/null 2>&1 \
  || fail "python venv module missing." "Debian/Ubuntu splits it into a separate package." "sudo apt install python3-venv   (Arch: already in python) then re-run ./setup.sh"

# Optional tools (never block).
step "Checking optional tools"
if command -v docker >/dev/null 2>&1; then ok "$(docker --version) -- enables local SearXNG search"; else warn "Docker not found (optional). Without it web search is disabled; use --no-docker. Install: https://docs.docker.com/engine/install/"; fi
if command -v ollama >/dev/null 2>&1; then ok "$(ollama --version 2>&1 | head -n1) -- needed only if BLINKY_AI_PROVIDER=ollama (https://ollama.com)"; else warn "Ollama not found (optional). Only needed for BLINKY_AI_PROVIDER=ollama."; fi
if command -v tesseract >/dev/null 2>&1; then ok "Tesseract $(tesseract --version 2>&1 | head -n1)"; else warn "Tesseract missing -- OCR fallback may fail. sudo apt install tesseract-ocr / sudo pacman -S tesseract  (or local tessdata, see below)"; fi
if gst-inspect-1.0 --version >/dev/null 2>&1; then ok "GStreamer $(gst-inspect-1.0 --version 2>&1 | head -n1)"; else warn "GStreamer missing -- audio may fail. Arch: sudo pacman -S gst-plugins-good | Ubuntu: sudo apt install gstreamer1.0-plugins-good"; fi
if command -v node >/dev/null 2>&1; then ok "Node $(node --version) (optional, helps Expo/mobile)"; else warn "Node not found (optional). Bun covers most flows; install Node LTS if Expo/mobile acts up: https://nodejs.org"; fi

# -- 4. bun install (desktop) ---------------------------------------------
step "Installing desktop JS dependencies (bun install)"
[ -f "$REPO_ROOT/package.json" ] \
  || fail "package.json not found in $REPO_ROOT." "You are not in the Blinky repo root." "cd <path-to-Blinky> then re-run ./setup.sh"
bun install \
  || fail "bun install failed." "Usually network, locked files, or old Bun." "bun --version  # need 1.3+ // rm -rf node_modules bun.lockb  # nuclear retry, then re-run ./setup.sh"
ok "Desktop JS dependencies installed"

# -- 5. Python venv + deps + Playwright ------------------------------------
step "Setting up Python virtual environment (.venv)"
VENV_PATH="$REPO_ROOT/.venv"; VENV_PYTHON="$VENV_PATH/bin/python"
REQUIREMENTS="$REPO_ROOT/linux/requirements.txt"
[ -f "$REQUIREMENTS" ] || fail "linux/requirements.txt not found." "Repo checkout incomplete." "git pull then re-run ./setup.sh"
if [ ! -f "$VENV_PYTHON" ]; then
  echo "  Creating .venv with $PYTHON_BIN..."
  "$PYTHON_BIN" -m venv "$VENV_PATH" \
    || fail "Failed to create .venv." "Broken Python or missing venv module." "$PYTHON_BIN -m venv .venv --clear  # manual retry, then re-run ./setup.sh"
  ok ".venv created at $VENV_PATH"
else
  ok ".venv already exists at $VENV_PATH"
fi

step "Installing Python dependencies (may take 2-5 min)"
"$VENV_PYTHON" -m pip install --upgrade pip \
  || fail "pip upgrade failed." "No internet or broken venv." ".venv/bin/python -m pip install --upgrade pip  # manual retry"
ok "pip upgraded"
"$VENV_PYTHON" -m pip install -r "$REQUIREMENTS" \
  || fail "pip install failed." "Check $REQUIREMENTS vs Python version (3.11+)." ".venv/bin/python -m pip install -r linux/requirements.txt  # manual retry, see error above"
ok "Python packages installed"

step "Installing Playwright Chromium"
"$VENV_PYTHON" -m playwright install chromium \
  || fail "Playwright install failed." "Browser automation needs this." ".venv/bin/python -m playwright install chromium  # manual retry"
ok "Playwright Chromium installed"
if command -v npx >/dev/null 2>&1; then
  echo "  Installing Playwright system deps (may need sudo, non-blocking)..."
  "$VENV_PYTHON" -m playwright install-deps chromium 2>&1 | tail -n 20 || warn "playwright install-deps had warnings (often fine without sudo)"
fi

# -- 6. .env (never auto-fill keys, but validate) --------------------------
step "Preparing .env (API keys are NEVER auto-filled)"
ENV_PATH="$REPO_ROOT/.env"; ENV_EXAMPLE="$REPO_ROOT/.env_example"
if [ ! -f "$ENV_PATH" ]; then
  if [ -f "$ENV_EXAMPLE" ]; then cp "$ENV_EXAMPLE" "$ENV_PATH"; ok ".env created from .env_example -- EDIT IT to add keys"
  elif [ -f "$REPO_ROOT/common/.envexample" ]; then cp "$REPO_ROOT/common/.envexample" "$ENV_PATH"; ok ".env created from common/.envexample -- EDIT IT"
  else
    cat > "$ENV_PATH" <<'EOF'
BLINKY_AI_PROVIDER=groq
GROQ_API_KEY=
SARVAM_API_KEY=
BLINKY_SHORTCUT=Space
EOF
    ok ".env created (minimal) -- EDIT IT"
  fi
else
  ok ".env already exists (not overwritten)"
fi
PROVIDER=$(grep -E "^BLINKY_AI_PROVIDER=" "$ENV_PATH" 2>/dev/null | cut -d= -f2 | tr -d ' \r' || echo groq)
if [ "$PROVIDER" = "groq" ] && ! grep -qE "^GROQ_API_KEY=gsk_" "$ENV_PATH" 2>/dev/null; then
  warn "GROQ_API_KEY is empty but BLINKY_AI_PROVIDER=groq. App WILL start but AI answers will 401."
  echo "    Fix: https://console.groq.com -> API Keys -> Create -> paste 'GROQ_API_KEY=gsk_...' into .env"
else
  ok ".env provider/key check done (provider=$PROVIDER)"
fi
grep -qE "^ASSEMBLY_AI_API_KEY=.+" "$ENV_PATH" 2>/dev/null || warn "ASSEMBLY_AI_API_KEY is empty -- voice features will fail until set (https://assemblyai.com)."

# Tesseract local fallback (no sudo path).
if [ ! -f "common/tessdata/eng.traineddata" ] && ! command -v tesseract >/dev/null 2>&1; then
  warn "No tesseract data found. If you lack sudo, run:"
  echo "    mkdir -p common/tessdata && curl -L -o common/tessdata/eng.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata"
  echo "    then add to .env: TESSDATA_PREFIX=$REPO_ROOT/common/tessdata/"
fi

# -- 7. Mobile deps -------------------------------------------------------
if [ "$SKIP_MOBILE" = "1" ]; then
  step "Skipping mobile deps (--skip-mobile)"
  warn "Mobile skipped. Run later: ./setup-mobile.sh"
else
  step "Installing mobile companion deps (common/mobile)"
  if [ ! -f "$REPO_ROOT/common/mobile/package.json" ]; then
    warn "common/mobile/package.json not found -- skipping mobile deps."
  else
    (cd "$REPO_ROOT/common/mobile" && bun install) \
      || warn "Mobile deps failed (non-blocking for desktop). Fix: cd common/mobile && bun install; then ./setup-mobile.sh"
    ok "Mobile deps installed. Run mobile QR setup: ./setup-mobile.sh"
  fi
fi

# -- 8. Typecheck (non-blocking) ------------------------------------------
step "Sanity check (typecheck, non-blocking)"
if bun run typecheck 2>&1; then ok "Typecheck passed"; else warn "Typecheck had warnings (app will still run)"; fi

# -- 9. Doctor summary ----------------------------------------------------
step "Doctor -- what's ready, what's not"
echo "  Bun:    $(command -v bun || echo MISSING) ($(bun --version 2>/dev/null || echo '?'))"
echo "  Cargo:  $(command -v cargo || echo 'MISSING (bun run dev will fail)')"
echo "  Venv:   $([ -f .venv/bin/python ] && echo READY || echo MISSING)"
echo "  .env:   check warnings above (GROQ/AssemblyAI keys)"
echo "  Mobile: $([ -d common/mobile/node_modules ] && echo READY || echo 'run ./setup-mobile.sh')"

echo -e "\n${GREEN}============================================================${NC}"
echo -e "${GREEN}  Setup complete! One-click run:${NC}"
echo -e "${GREEN}============================================================${NC}"
cat <<'EOF'

  RUN THE APP (pick one):
    ./run.sh                 # one-click run (checks deps, picks docker/no-docker)
    bun run dev              # full (SearXNG + Tauri + Python)
    bun run dev:no-docker    # skip Docker/SearXNG (no web search)

  MOBILE (phone remote + QR):
    ./setup-mobile.sh        # installs mobile deps, prints LAN IP + QR flow
    # Then in the Expo terminal: scan QR with Expo Go / dev build.
    # Phone + PC must be on the SAME Wi-Fi (or USB: adb reverse, see script).

  CONFIGURE KEYS (.env -- required before AI works):
    GROQ_API_KEY=gsk_...     # https://console.groq.com -> API Keys
    ASSEMBLY_AI_API_KEY=...  # https://assemblyai.com (voice)
    BLINKY_AI_PROVIDER=groq  # or: custom / ollama

  HOTKEYS:  CTRL + SHIFT + SPACE  (fallback CTRL + SHIFT + ENTER)

  TROUBLESHOOTING (exact fixes):
    bun missing      -> curl -fsSL https://bun.sh/install | bash; export PATH="$HOME/.bun/bin:$PATH"
    cargo missing    -> curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
    python missing   -> sudo apt install python3.11 python3-venv python3-pip
    webkit missing   -> sudo apt install libwebkit2gtk-4.1-dev (Ubuntu) / sudo pacman -S webkit2gtk-4.1 (Arch)
    pip fail         -> .venv/bin/python -m pip install -r linux/requirements.txt
    401 from Groq    -> .env GROQ_API_KEY empty or wrong; paste gsk_... key
    ports busy       -> ./run.sh handles conflicts automatically

  Docs: README.md -> Getting Started. Log: setup.log (idempotent -- safe to re-run).

EOF

if [ "$RUN_APP" = "1" ]; then
  step "One-click run requested (--run): launching Blinky"
  command -v cargo >/dev/null 2>&1 \
    || fail "Cannot --run: Rust/Cargo still missing." "Tauri cannot start without it." "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh  # restart terminal, re-run ./setup.sh --run"
  if docker info >/dev/null 2>&1; then bun run dev; else warn "Docker daemon not running -- launching with --no-docker (no web search)."; bun run dev:no-docker; fi
fi
