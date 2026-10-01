#!/usr/bin/env bash
# Blinky one-click run (Linux). Validates setup, then launches the app.
# Usage:
#   chmod +x run.sh && ./run.sh
#   ./run.sh --no-docker   # force skip Docker/SearXNG
#   ./run.sh --no-mobile   # skip USB-mobile autodetect
# Any failure prints [ERROR] + exact fix command.
set -u
set -o pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; MAGENTA='\033[0;35m'; NC='\033[0m'
NO_DOCKER=0; NO_MOBILE=0
EXTRA=()
for arg in "$@"; do
  case "$arg" in
    --no-docker) NO_DOCKER=1 ;;
    --no-mobile) NO_MOBILE=1; EXTRA+=(--no-mobile) ;;
    --help|-h) echo "Usage: ./run.sh [--no-docker] [--no-mobile]"; exit 0 ;;
    *) EXTRA+=("$arg") ;;
  esac
done

step() { echo -e "\n${CYAN}[STEP] $*${NC}"; }
ok()   { echo -e "  ${GREEN}+ $*${NC}"; }
warn() { echo -e "  ${YELLOW}! $*${NC}"; }
fail() {
  echo -e "\n${RED}[ERROR] $1${NC}"
  [ -n "${2:-}" ] && echo -e "  ${YELLOW}Why: $2${NC}"
  [ -n "${3:-}" ] && echo -e "  Fix and retry:\n    $3"
  echo -e "  ${RED}Run aborted. Fix above, then re-run: ./run.sh${NC}\n"
  exit 1
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"
echo -e "${MAGENTA}  Blinky - One-click Run (Linux)  |  Repo: $REPO_ROOT${NC}"

command -v bun >/dev/null 2>&1 || {
  [ -f "$HOME/.bun/bin/bun" ] && export PATH="$HOME/.bun/bin:$PATH"
}
command -v bun >/dev/null 2>&1 \
  || fail "Bun not found. Setup did not complete." "One-click setup installs Bun first." "./setup.sh  # then ./run.sh"

step "Pre-flight checks"
[ -f "$REPO_ROOT/package.json" ] \
  || fail "package.json missing in $REPO_ROOT." "Wrong folder." "cd <path-to-Blinky> then ./run.sh"
[ -d "$REPO_ROOT/node_modules" ] \
  || fail "node_modules missing. Dependencies were never installed." "Run setup once." "./setup.sh  # then ./run.sh"
ok "node_modules present"
[ -f "$REPO_ROOT/.venv/bin/python" ] \
  || fail "Python .venv missing." "Run setup once." "./setup.sh  # then ./run.sh"
ok ".venv present"
command -v cargo >/dev/null 2>&1 \
  || fail "Rust/Cargo not found. Tauri cannot start." "Setup warns about this; install Rust." "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh  # restart terminal, then ./run.sh"
ok "$(cargo --version)"
[ -f "$REPO_ROOT/.env" ] \
  || fail ".env missing. API keys/config were never created." "Run setup once." "./setup.sh  # then edit .env, then ./run.sh"
ok ".env present"
if grep -qE "^BLINKY_AI_PROVIDER=groq" "$REPO_ROOT/.env" 2>/dev/null && ! grep -qE "^GROQ_API_KEY=gsk_" "$REPO_ROOT/.env" 2>/dev/null; then
  warn "GROQ_API_KEY empty with provider=groq: app starts but AI answers 401. Fix: paste gsk_... key into .env (https://console.groq.com)."
fi

# Kill stale listeners on dev ports (common "port in use" confusion).
for p in 5173 9001 9002 8081; do
  pid=$(ss -tlnp 2>/dev/null | grep ":$p " | grep -oP 'pid=\K[0-9]+' | head -n1 || true)
  if [ -n "$pid" ]; then warn "Port $p busy (pid $pid) -- killing stale listener..."; kill -9 "$pid" 2>/dev/null || true; fi
done
ok "Dev ports checked"

USE_NO_DOCKER="$NO_DOCKER"
if [ "$USE_NO_DOCKER" = "0" ]; then
  if docker info >/dev/null 2>&1; then ok "Docker daemon running: SearXNG search enabled"
  else USE_NO_DOCKER=1; warn "Docker daemon not running: launching WITHOUT SearXNG web search. Start docker to enable search."; fi
fi

step "Launching Blinky (Ctrl+C to stop)"
echo "  Hotkeys: CTRL + SHIFT + SPACE  (fallback CTRL + SHIFT + ENTER)"
echo "  Mobile:  ./setup-mobile.sh  (QR + USB flow, phone remote)"
if [ "$USE_NO_DOCKER" = "1" ]; then
  bun run dev:no-docker -- "${EXTRA[@]}"
else
  bun run dev -- "${EXTRA[@]}"
fi
