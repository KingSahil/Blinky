#!/usr/bin/env bash
# Blinky mobile one-click setup (Linux) -- installs deps, prints LAN IP, starts Expo QR.
# Usage:
#   chmod +x setup-mobile.sh && ./setup-mobile.sh
#   ./setup-mobile.sh --tunnel   # ngrok tunnel when phone+PC are on different networks
#   ./setup-mobile.sh --usb      # USB mode: adb reverse + localhost (no Wi-Fi needed)
#   ./setup-mobile.sh --clear    # start Metro with cache cleared (expo start -c)
# Flow: 1) run desktop first (./run.sh)  2) run this script  3) scan QR  4) enter PC IP, tap Establish Link.
set -u
set -o pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; MAGENTA='\033[0;35m'; NC='\033[0m'
TUNNEL=0; USB=0; CLEAR=0
for arg in "$@"; do
  case "$arg" in
    --tunnel) TUNNEL=1 ;;
    --usb) USB=1 ;;
    --clear|-c) CLEAR=1 ;;
    --help|-h) echo "Usage: ./setup-mobile.sh [--tunnel] [--usb] [--clear]"; exit 0 ;;
    *) echo -e "${YELLOW}! Unknown flag: $arg${NC}" ;;
  esac
done

step() { echo -e "\n${CYAN}[STEP] $*${NC}"; }
ok()   { echo -e "  ${GREEN}+ $*${NC}"; }
warn() { echo -e "  ${YELLOW}! $*${NC}"; }
fail() {
  echo -e "\n${RED}[ERROR] $1${NC}"
  [ -n "${2:-}" ] && echo -e "  ${YELLOW}Why: $2${NC}"
  [ -n "${3:-}" ] && echo -e "  Fix and retry:\n    $3"
  echo -e "  ${RED}Mobile setup aborted. Fix above, then re-run: ./setup-mobile.sh${NC}\n"
  exit 1
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"
MOBILE_DIR="$REPO_ROOT/common/mobile"
echo -e "${MAGENTA}============================================================${NC}"
echo -e "${MAGENTA}  Blinky - Mobile One-click Setup (Linux)${NC}"
echo -e "${MAGENTA}  Mobile dir: $MOBILE_DIR${NC}"
echo -e "${MAGENTA}============================================================${NC}"

[ -f "$MOBILE_DIR/package.json" ] \
  || fail "common/mobile/package.json not found." "Run from the Blinky repo root." "cd <path-to-Blinky> then ./setup-mobile.sh"

command -v bun >/dev/null 2>&1 || { [ -f "$HOME/.bun/bin/bun" ] && export PATH="$HOME/.bun/bin:$PATH"; }
command -v bun >/dev/null 2>&1 \
  || fail "Bun not found." "Mobile bundler runs on Bun/Expo." "./setup.sh  # then ./setup-mobile.sh"

step "Installing mobile dependencies (common/mobile)"
(cd "$MOBILE_DIR" && bun install) \
  || fail "Mobile bun install failed." "Usually network or old Bun." "cd common/mobile && bun install  # manual retry"
ok "Mobile deps installed"

step "Checking Expo CLI"
if bun x expo --version >/dev/null 2>&1; then ok "Expo $(bun x expo --version 2>/dev/null | head -n1)"
else warn "Expo CLI check failed (non-blocking; 'bun run start' will fetch it). If Metro fails: cd common/mobile && bun install && bunx expo --version"; fi

step "Checking desktop backend (port 9001)"
if (command -v nc >/dev/null 2>&1 && nc -z -w2 127.0.0.1 9001) || (exec 3<>/dev/tcp/127.0.0.1/9001) 2>/dev/null; then
  exec 3<&- 3>&- 2>/dev/null || true
  ok "Desktop backend reachable on 127.0.0.1:9001"
else
  warn "Desktop backend NOT reachable on port 9001."
  echo "    The phone remote-controls the PC via the DESKTOP pipeline (same CommandBar executor)."
  echo "    Start it first in another terminal:  ./run.sh  (or: bun run dev)"
  echo "    Continuing anyway so you can still scan the QR and prepare the phone."
fi

step "Your PC IP (type this in the phone app, then Establish Link)"
LAN_IP=""
if command -v ip >/dev/null 2>&1; then
  LAN_IP=$(ip route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}' || true)
fi
if [ -n "$LAN_IP" ]; then echo -e "  ${GREEN}PC IP: $LAN_IP :9001${NC}"
else
  warn "Could not auto-detect LAN IP."
  echo "    Find it with: ip route get 1.1.1.1 | awk '{print \$7}'   or: hostname -I"
fi
if command -v tailscale >/dev/null 2>&1; then
  TS_IP=$(tailscale ip -4 2>/dev/null | head -n1 || true)
  [ -n "$TS_IP" ] && echo -e "  ${GREEN}Tailscale IP: $TS_IP :9001 (use off-LAN)${NC}"
fi

if [ "$USB" = "1" ]; then
  step "USB mode: adb reverse tcp:9001/9002/9004/8081"
  command -v adb >/dev/null 2>&1 \
    || fail "adb not found (needed for --usb)." "Install platform tools and enable USB debugging." "sudo pacman -S android-tools / sudo apt install adb  (https://developer.android.com/tools/adb), then ./setup-mobile.sh --usb"
  adb reverse tcp:9001 tcp:9001 || fail "adb reverse 9001 failed." "Phone not connected / USB debugging off / RSA prompt not accepted." "1) enable USB debugging  2) accept prompt  3) adb devices  4) re-run ./setup-mobile.sh --usb"
  adb reverse tcp:9002 tcp:9002
  adb reverse tcp:9004 tcp:9004
  adb reverse tcp:8081 tcp:8081 || true
  ok "USB reverse routing done. In the phone app use IP: localhost"
fi

step "Firewall note (phone must reach PC :9001)"
echo "  If the phone cannot connect on Wi-Fi, allow TCP 9001 inbound:"
echo "    sudo ufw allow 9001/tcp    # Ubuntu (ufw)"
echo "    sudo firewall-cmd --add-port=9001/tcp --permanent && sudo firewall-cmd --reload    # Fedora"

step "Starting Expo (QR prints below -- scan it)"
ARGS=(run start -- --host lan)
[ "$TUNNEL" = "1" ] && ARGS=(run start -- --tunnel) && warn "Tunnel mode: uses ngrok (slower, needs @expo/ngrok + internet). Same-Wi-Fi LAN is faster."
[ "$CLEAR" = "1" ] && ARGS+=( -c ) && echo "  Cache clear requested (--clear)."
echo ""
echo -e "  ${GREEN}================= PHONE TEST FLOW (what the devs implemented) =================${NC}"
echo "  1) Scan the QR below with Expo Go (or open it in your Blinky dev build)."
echo -e "     ${YELLOW}NOTE: full app needs the custom dev build (native modules). If you see"
echo "     'Cannot find native module ExponentImagePicker', you are in Expo Go or an"
echo "     old build: rebuild via EAS (see common/mobile/README.md) and reopen."
echo "  2) Phone + PC must be on the SAME Wi-Fi (or --usb mode with IP 'localhost')."
echo "  3) In the app: QR tab (default) - scan the pairing code from the PC app"
echo "     (PC app header -> QR icon). Or Manual tab: enter PC IP (printed above),"
echo "     tap 'Establish Link'."
echo "  4) Test: Power (Sleep/Restart/Shutdown), remote AI query over WS :9001,"
echo "     file transfer to a PC folder, camera-roll sync. Mobile just transmits;"
echo "     execution uses the SAME PC CommandBar pipeline/coordinates."
echo "  Metro keys: r = reload, m = dev menu, a = open app, Ctrl+C = stop."
echo -e "  ${GREEN}=============================================================================${NC}"
echo ""
(cd "$MOBILE_DIR" && bun "${ARGS[@]}") \
  || fail "Expo failed to start." "See error above (common: port 8081 busy, or native-module mismatch)." "cd common/mobile && bun run start:clear  # manual retry. If 8081 busy: kill old Metro first."
