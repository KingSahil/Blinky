#!/usr/bin/env bash
# Blinky - One-click Linux Setup
# Usage: chmod +x setup.sh && ./setup.sh
# Does NOT inject API keys; prints next steps at end.
set -e

# ── helpers ──────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; MAGENTA='\033[0;35m'; NC='\033[0m'
step()    { echo -e "\n${CYAN}[STEP] $*${NC}"; }
ok()      { echo -e "  ${GREEN}✓ $*${NC}"; }
warn()    { echo -e "  ${YELLOW}! $*${NC}"; }
fail() {
  echo -e "\n${RED}[ERROR] $1${NC}"
  if [ -n "$2" ]; then echo -e "  ${YELLOW}Hint: $2${NC}"; fi
  echo -e "  ${RED}Setup aborted. Fix above and re-run: ./setup.sh${NC}\n"
  exit 1
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"
echo -e "${MAGENTA}============================================================${NC}"
echo -e "${MAGENTA}  Blinky - One-click Linux Setup${NC}"
echo -e "${MAGENTA}  Repo: $REPO_ROOT${NC}"
echo -e "${MAGENTA}============================================================${NC}"

# ── 1. Prerequisites ───────────────────────────────────────────────────
step "Checking prerequisites"

# Bun
if ! command -v bun >/dev/null 2>&1; then
  if [ -f "$HOME/.bun/bin/bun" ]; then
    export PATH="$HOME/.bun/bin:$PATH"
    ok "Bun found at ~/.bun/bin/bun"
  else
    fail "Bun not found." "Install: curl -fsSL https://bun.sh/install | bash  then restart terminal. See https://bun.sh"
  fi
else
  ok "Bun $(bun --version) ($(command -v bun))"
fi

# Rust / Cargo
if command -v cargo >/dev/null 2>&1; then
  ok "$(cargo --version)"
else
  warn "Cargo/Rust not found. Required for Tauri."
  echo "    Install: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
  echo "    Or: sudo pacman -S rust  /  sudo apt install cargo"
  echo "    Continuing anyway (bun install will work, but 'bun run dev' needs Rust)."
fi

# Python 3.11+
PYTHON_BIN=""
for cand in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    ver=$("$cand" --version 2>&1 || true)
    if echo "$ver" | grep -qE "Python 3\.1[1-9]\."; then
      # also handle 3.20+ if ever
      PYTHON_BIN="$cand"
      break
    fi
    # fallback: check major.minor >= 3.11 via python -c
    if "$cand" -c "import sys; exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
      PYTHON_BIN="$cand"
      break
    fi
  fi
done
if [ -z "$PYTHON_BIN" ]; then
  fail "Python 3.11+ not found." "Install: sudo apt install python3.11 python3-venv  /  sudo pacman -S python"
fi
ok "Found $($PYTHON_BIN --version) via $PYTHON_BIN"

# Ensure venv module exists
if ! "$PYTHON_BIN" -m venv --help >/dev/null 2>&1; then
  fail "python venv module missing." "Install: sudo apt install python3-venv  /  sudo pacman -S python"
fi

# Docker (optional)
if command -v docker >/dev/null 2>&1; then
  ok "$(docker --version) (optional, for SearXNG)"
else
  warn "Docker not found (optional). SearXNG web search will be disabled. Install Docker: https://docs.docker.com/engine/install/"
fi

# Ollama (optional)
if command -v ollama >/dev/null 2>&1; then
  ok "$(ollama --version 2>&1 | head -n1) (optional, for local inference)"
else
  warn "Ollama not found (optional). Only needed if BLINKY_AI_PROVIDER=ollama. Install: https://ollama.com"
fi

# Tesseract (optional but recommended for OCR fallback)
if command -v tesseract >/dev/null 2>&1; then
  ok "Tesseract $(tesseract --version 2>&1 | head -n1)"
else
  warn "Tesseract not found. OCR fallback may fail."
  echo "    Install: sudo apt install tesseract-ocr  /  sudo pacman -S tesseract"
  echo "    Or local install (no sudo):"
  echo "      mkdir -p common/tessdata && curl -L -o common/tessdata/eng.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata"
  echo "      then add to .env: TESSDATA_PREFIX=$REPO_ROOT/common/tessdata/"
fi

# GStreamer (audio)
if gst-inspect-1.0 --version >/dev/null 2>&1; then
  ok "GStreamer $(gst-inspect-1.0 --version 2>&1 | head -n1)"
else
  warn "GStreamer not found. Audio may fail."
  echo "    Arch:   sudo pacman -S gst-plugins-good"
  echo "    Ubuntu: sudo apt install gstreamer1.0-plugins-good"
fi

# ── 2. bun install ─────────────────────────────────────────────────────
step "Installing JS dependencies (bun install)"
if [ ! -f "$REPO_ROOT/package.json" ]; then
  fail "package.json not found in $REPO_ROOT" "Run this script from the repo root."
fi
if ! bun install; then
  fail "bun install failed." "Check network, or delete bun.lock + node_modules and retry. Ensure Bun 1.3+."
fi
ok "JS dependencies installed"

# ── 3. Python venv (.venv) ────────────────────────────────────────────
step "Setting up Python virtual environment (.venv)"
VENV_PATH="$REPO_ROOT/.venv"
VENV_PYTHON="$VENV_PATH/bin/python"
REQUIREMENTS="$REPO_ROOT/linux/requirements.txt"
if [ ! -f "$REQUIREMENTS" ]; then
  fail "linux/requirements.txt not found at $REQUIREMENTS"
fi

if [ ! -f "$VENV_PYTHON" ]; then
  echo "  Creating .venv with $PYTHON_BIN..."
  if ! "$PYTHON_BIN" -m venv "$VENV_PATH"; then
    fail "Failed to create .venv" "Try manually: $PYTHON_BIN -m venv .venv"
  fi
  ok ".venv created at $VENV_PATH"
else
  ok ".venv already exists at $VENV_PATH"
fi

# ── 4. pip + requirements + playwright ─────────────────────────────────
step "Installing Python dependencies"
if ! "$VENV_PYTHON" -m pip install --upgrade pip; then
  fail "pip upgrade failed." "Try: .venv/bin/python -m pip install --upgrade pip"
fi
ok "pip upgraded"

echo "  Installing linux/requirements.txt (may take 2-5 min)..."
if ! "$VENV_PYTHON" -m pip install -r "$REQUIREMENTS"; then
  fail "pip install failed." "Check $REQUIREMENTS and your Python version (3.11+). See error above."
fi
ok "Python packages installed"

step "Installing Playwright Chromium"
if ! "$VENV_PYTHON" -m playwright install chromium; then
  fail "Playwright install failed." "Try: .venv/bin/python -m playwright install chromium"
fi
ok "Playwright chromium installed"
# Also install system deps for playwright on Linux (may need sudo)
if command -v npx >/dev/null 2>&1; then
  echo "  Installing Playwright system deps (may need sudo, non-blocking)..."
  "$VENV_PYTHON" -m playwright install-deps chromium 2>&1 | tail -n 20 || warn "playwright install-deps had warnings (often okay without sudo)"
fi

# ── 5. .env ────────────────────────────────────────────────────────────
step "Preparing .env"
ENV_PATH="$REPO_ROOT/.env"
ENV_EXAMPLE="$REPO_ROOT/.env_example"
if [ ! -f "$ENV_PATH" ]; then
  if [ -f "$ENV_EXAMPLE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_PATH"
    ok ".env created from .env_example"
  elif [ -f "$REPO_ROOT/common/.envexample" ]; then
    cp "$REPO_ROOT/common/.envexample" "$ENV_PATH"
    ok ".env created from common/.envexample"
  else
    cat > "$ENV_PATH" <<'EOF'
BLINKY_AI_PROVIDER=groq
GROQ_API_KEY=
SARVAM_API_KEY=
BLINKY_SHORTCUT=Space
EOF
    ok ".env created (minimal)"
  fi
else
  ok ".env already exists (not overwritten)"
fi

# ── 6. Tesseract local fallback helper ─────────────────────────────────
if [ ! -f "common/tessdata/eng.traineddata" ] && ! command -v tesseract >/dev/null 2>&1; then
  warn "No tesseract data found. If you lack sudo, run:"
  echo "    mkdir -p common/tessdata && curl -L -o common/tessdata/eng.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata"
  echo "    then add to .env: TESSDATA_PREFIX=$REPO_ROOT/common/tessdata/"
fi

# ── 7. Typecheck (non-blocking) ────────────────────────────────────────
step "Sanity check (typecheck)"
if bun run typecheck 2>&1; then
  ok "Typecheck passed"
else
  warn "Typecheck had warnings (non-blocking)"
fi

# ── 8. Summary ─────────────────────────────────────────────────────────
echo -e "\n${GREEN}============================================================${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${GREEN}============================================================${NC}"
cat <<EOF

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
       Then: ollama pull gemma4:e4b  &&  ollama serve

  2) (Optional) Start local web search (SearXNG):
     docker compose -f common/docker-compose.yml up -d
     -> http://localhost:8888
     Or skip: bun run dev:no-docker

  3) Run Blinky:
     bun run dev              # full (SearXNG + Tauri + Python)
     # If Bun not in PATH after install: export PATH="\$HOME/.bun/bin:\$PATH"

  4) Open Blinky:
     Hotkey: CTRL + SHIFT + SPACE (fallback CTRL + SHIFT + ENTER)

Troubleshooting:
  - bun not found      -> export PATH="\$HOME/.bun/bin:\$PATH" or restart terminal
  - cargo not found    -> curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
  - Python 3.11+ miss  -> sudo apt install python3.11 python3-venv
  - pip/playwright fail-> check internet, rerun ./setup.sh (idempotent)
  - Groq 429/TPM limit -> wait 30s or switch to ollama/custom
  - Tesseract missing  -> see warnings above
  - Ollama not running -> ollama serve

Docs: README.md -> How to Run the Project / linux/quick_start.md

EOF
echo -e "${YELLOW}  Setup log: rerun ./setup.sh anytime (idempotent).${NC}\n"
