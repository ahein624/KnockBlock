#!/usr/bin/env bash
# KnockBlock one-command install for a fresh Raspberry Pi.
#
#   curl -sSL https://raw.githubusercontent.com/ahein624/KnockBlock/main/install.sh | bash
#
# or, from inside a clone:  ./install.sh
#
# Idempotent: re-running updates the code and rebuilds only what's missing.
# Never touches auth.json / state.json / media, so it's also a safe upgrade
# path. Pass --dry-run to print the commands without executing anything.
set -euo pipefail

REPO_URL="${KNOCKBLOCK_REPO:-https://github.com/ahein624/KnockBlock.git}"
DRIVER_URL="https://github.com/hzeller/rpi-rgb-led-matrix.git"
INSTALL_DIR="${KNOCKBLOCK_DIR:-$HOME/KnockBlock}"
DRIVER_DIR="$HOME/rpi-rgb-led-matrix"
SERVICE_PATH="/etc/systemd/system/knockblock.service"

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
run() {
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '   [dry-run] %s\n' "$*"
  else
    "$@"
  fi
}

if [[ $(id -u) -eq 0 ]]; then
  echo "Run this as your normal login user (it uses sudo where needed)." >&2
  exit 1
fi

# When run from inside a checkout, install in place instead of cloning.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-.}")" && pwd)"
if [[ -f "$SCRIPT_DIR/app.py" && -f "$SCRIPT_DIR/matrix.py" ]]; then
  INSTALL_DIR="$SCRIPT_DIR"
fi

say "System packages"
run sudo apt-get update -qq
run sudo apt-get install -y -qq git python3-dev python3-pip python3-venv cython3 curl

say "KnockBlock code → $INSTALL_DIR"
if [[ -d "$INSTALL_DIR/.git" ]]; then
  run git -C "$INSTALL_DIR" pull --ff-only
elif [[ -e "$INSTALL_DIR" ]]; then
  echo "   $INSTALL_DIR exists but isn't a git clone — leaving it alone."
else
  run git clone "$REPO_URL" "$INSTALL_DIR"
fi

say "Panel driver (hzeller/rpi-rgb-led-matrix)"
if [[ ! -d "$DRIVER_DIR" ]]; then
  run git clone "$DRIVER_URL" "$DRIVER_DIR"
fi

say "Python environment"
if [[ ! -x "$INSTALL_DIR/venv/bin/python3" ]]; then
  run python3 -m venv "$INSTALL_DIR/venv"
fi
PIP="$INSTALL_DIR/venv/bin/pip"
PY="$INSTALL_DIR/venv/bin/python3"
run "$PIP" install -q --upgrade pip
run "$PIP" install -q -r "$INSTALL_DIR/requirements.txt"

if ! "$PY" -c "import rgbmatrix" 2>/dev/null; then
  say "Building the rgbmatrix Python bindings"
  # The driver's build needs Pillow's internal Imaging.h headers, which
  # aren't vendored — fetch the set matching the installed Pillow.
  PILLOW_VERSION="$("$PY" -c "import PIL; print(PIL.__version__)" 2>/dev/null || echo "<pillow-version>")"
  SHIMS="$DRIVER_DIR/bindings/python/rgbmatrix/shims"
  run mkdir -p "$SHIMS"
  for f in Imaging.h ImPlatform.h Mode.h Arrow.h ImagingUtils.h; do
    run curl -sSL -o "$SHIMS/$f" \
      "https://raw.githubusercontent.com/python-pillow/Pillow/$PILLOW_VERSION/src/libImaging/$f"
  done
  run "$PIP" install -q "$DRIVER_DIR"
  if [[ $DRY_RUN -eq 0 ]]; then
    "$PY" -c "import rgbmatrix" || {
      echo "rgbmatrix failed to build — see README.md 'Manual setup' for troubleshooting." >&2
      exit 1
    }
  fi
fi

say "Onboard audio (conflicts with the panel's PWM timing)"
BOOT_CONFIG="/boot/firmware/config.txt"
[[ -f $BOOT_CONFIG ]] || BOOT_CONFIG="/boot/config.txt"
NEED_REBOOT=0
if [[ -f $BOOT_CONFIG ]] && grep -Eq '^\s*dtparam=audio=on' "$BOOT_CONFIG"; then
  run sudo sed -i 's/^\s*dtparam=audio=on/# dtparam=audio=on  # disabled for KnockBlock/' "$BOOT_CONFIG"
  NEED_REBOOT=1
  echo "   Onboard audio disabled — a reboot is needed before the panel will run cleanly."
else
  echo "   Already disabled."
fi

# The service and updater run as root while the clone belongs to the login
# user; without this, root's git refuses the repo ("dubious ownership").
run sudo git config --system --add safe.directory "$INSTALL_DIR"

say "systemd service"
if [[ $DRY_RUN -eq 1 ]]; then
  echo "   [dry-run] render deploy/knockblock.service.in -> $SERVICE_PATH (WORKDIR=$INSTALL_DIR)"
else
  sed "s|@WORKDIR@|$INSTALL_DIR|g" "$INSTALL_DIR/deploy/knockblock.service.in" \
    | sudo tee "$SERVICE_PATH" >/dev/null
  sudo systemctl daemon-reload
  sudo systemctl enable knockblock >/dev/null
fi

if [[ $NEED_REBOOT -eq 1 ]]; then
  say "Almost there"
  echo "Reboot to finish (sudo reboot). The sign starts automatically afterwards."
else
  run sudo systemctl restart knockblock
  say "Done"
fi
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Claim your sign: open http://${IP:-<pi-ip>}:5000 from a phone on this WiFi."
echo "Panel dark or garbled? Run: sudo $PY $INSTALL_DIR/hello_matrix.py"
echo "and see the hardware troubleshooting table in README.md."
