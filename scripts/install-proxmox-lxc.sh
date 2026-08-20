#!/usr/bin/env bash
# Install the KnockBlock controller inside a Debian/Ubuntu Proxmox LXC.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer as root inside the LXC." >&2
  exit 1
fi

REPO_URL="${KNOCKBLOCK_REPO_URL:-https://github.com/ahein624/KnockBlock.git}"
REPO_REF="${KNOCKBLOCK_REPO_REF:-main}"
APP_DIR="/opt/knockblock"
STATE_DIR="/var/lib/knockblock"
SERVICE_USER="knockblock"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  avahi-daemon ca-certificates curl fonts-dejavu-core fonts-noto-color-emoji \
  git python3 python3-pip python3-venv

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --home-dir "${STATE_DIR}" --create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi
install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${APP_DIR}" "${STATE_DIR}"

if [[ -d "${APP_DIR}/.git" ]]; then
  runuser -u "${SERVICE_USER}" -- git -C "${APP_DIR}" fetch --prune origin
  runuser -u "${SERVICE_USER}" -- git -C "${APP_DIR}" checkout -f "${REPO_REF}"
  runuser -u "${SERVICE_USER}" -- git -C "${APP_DIR}" reset --hard "origin/${REPO_REF}"
else
  if [[ -n "$(find "${APP_DIR}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "${APP_DIR} is not empty and is not a Git checkout; refusing to overwrite it." >&2
    exit 1
  fi
  runuser -u "${SERVICE_USER}" -- git clone --branch "${REPO_REF}" --depth 1 "${REPO_URL}" "${APP_DIR}"
fi

runuser -u "${SERVICE_USER}" -- python3 -m venv "${APP_DIR}/venv"
runuser -u "${SERVICE_USER}" -- "${APP_DIR}/venv/bin/pip" install --upgrade pip
runuser -u "${SERVICE_USER}" -- "${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

cat >/etc/systemd/system/knockblock.service <<EOF
[Unit]
Description=KnockBlock controller for ESP32 display clients
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=KNOCKBLOCK_STATE_DIR=${STATE_DIR}
ExecStart=${APP_DIR}/venv/bin/python3 ${APP_DIR}/deploy/lxc_server.py
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=full
ReadWritePaths=${APP_DIR} ${STATE_DIR}

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/avahi/services/knockblock.service <<'EOF'
<?xml version="1.0" standalone="no"?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">KnockBlock on %h</name>
  <service>
    <type>_knockblock._tcp</type>
    <port>5000</port>
  </service>
</service-group>
EOF

systemctl daemon-reload
systemctl enable --now avahi-daemon knockblock

for _attempt in {1..20}; do
  if curl --fail --silent --output /dev/null http://127.0.0.1:5000/; then
    break
  fi
  sleep 1
done
if ! curl --fail --silent --output /dev/null http://127.0.0.1:5000/; then
  systemctl status --no-pager knockblock || true
  exit 1
fi

LXC_IP="$(hostname -I | awk '{print $1}')"
echo
echo "KnockBlock is running: http://${LXC_IP}:5000"
echo "Open that address from your phone to claim and configure the sign."
