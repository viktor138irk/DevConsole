#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="devconsole"
APP_USER="devconsole"
APP_DIR="/opt/devconsole"
DATA_DIR="/var/lib/devconsole"
LOG_DIR="/var/log/devconsole"
USB_DIR="/mnt/devconsole-usb"
SERVICE_FILE="/etc/systemd/system/devconsole.service"
REPO_URL="${DEVCONSOLE_REPO_URL:-https://github.com/viktor138irk/DevConsole.git}"
BRANCH="${DEVCONSOLE_BRANCH:-main}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${DEVCONSOLE_HOST:-0.0.0.0}"
PORT="${DEVCONSOLE_PORT:-8077}"

info() { echo -e "\033[1;34m[DevConsole]\033[0m $*"; }
warn() { echo -e "\033[1;33m[DevConsole]\033[0m $*"; }
err() { echo -e "\033[1;31m[DevConsole]\033[0m $*"; }

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    err "Запусти установщик от root: sudo bash scripts/install_ubuntu.sh"
    exit 1
  fi
}

setup_git_safe_directory() {
  info "Настраиваю Git safe.directory"
  git config --global --add safe.directory "${APP_DIR}" || true
  if id -u "${APP_USER}" >/dev/null 2>&1; then
    sudo -u "${APP_USER}" git config --global --add safe.directory "${APP_DIR}" || true
  fi
}

install_docker() {
  info "Устанавливаю Docker"

  if command -v docker >/dev/null 2>&1; then
    warn "Docker уже установлен"
  else
    apt-get install -y ca-certificates curl gnupg lsb-release
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    UBUNTU_CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME:-jammy}")"
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME} stable" > /etc/apt/sources.list.d/docker.list

    if apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin; then
      info "Docker установлен из официального репозитория"
    else
      warn "Официальный репозиторий Docker не сработал, ставлю docker.io из Ubuntu repo"
      rm -f /etc/apt/sources.list.d/docker.list
      apt-get update
      DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io
    fi
  fi

  if ! docker compose version >/dev/null 2>&1; then
    warn "Docker Compose plugin недоступен, ставлю standalone docker-compose"
    COMPOSE_VERSION="v2.27.0"
    mkdir -p /usr/local/lib/docker/cli-plugins
    curl -fsSL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-$(uname -m)" -o /usr/local/lib/docker/cli-plugins/docker-compose
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
    ln -sf /usr/local/lib/docker/cli-plugins/docker-compose /usr/local/bin/docker-compose
  fi

  systemctl enable docker || true
  systemctl restart docker || true
}

install_packages() {
  info "Устанавливаю системные пакеты"
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates curl git unzip zip rsync jq lsof gnupg lsb-release \
    build-essential pkg-config \
    python3 python3-venv python3-pip \
    sqlite3 \
    adb fastboot \
    openjdk-17-jdk \
    udev

  install_docker
}

create_user_and_dirs() {
  info "Готовлю пользователя и каталоги"
  if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    useradd --system --create-home --shell /bin/bash "${APP_USER}"
  fi

  mkdir -p "${APP_DIR}" "${DATA_DIR}" "${LOG_DIR}" "${USB_DIR}"
  mkdir -p "${DATA_DIR}/projects" "${DATA_DIR}/snapshots" "${DATA_DIR}/artifacts" "${DATA_DIR}/apk" "${DATA_DIR}/tmp" "${DATA_DIR}/usb"
  chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}" "${DATA_DIR}" "${LOG_DIR}"
  chmod 755 "${APP_DIR}"
}

clone_or_update_repo() {
  info "Загружаю DevConsole из GitHub"
  setup_git_safe_directory

  if [[ -d "${APP_DIR}/.git" ]]; then
    git -C "${APP_DIR}" fetch origin "${BRANCH}"
    git -C "${APP_DIR}" reset --hard "origin/${BRANCH}"
    git -C "${APP_DIR}" clean -fd
  else
    rm -rf "${APP_DIR:?}/"*
    git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
  fi
  chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
  setup_git_safe_directory
}

setup_python() {
  info "Создаю Python venv"
  sudo -u "${APP_USER}" "${PYTHON_BIN}" -m venv "${APP_DIR}/venv"
  sudo -u "${APP_USER}" "${APP_DIR}/venv/bin/pip" install --upgrade pip wheel setuptools
  sudo -u "${APP_USER}" "${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"
}

setup_env() {
  info "Создаю .env при необходимости"
  if [[ ! -f "${APP_DIR}/.env" ]]; then
    cat > "${APP_DIR}/.env" <<EOF
# DevConsole runtime
DEVCONSOLE_HOST=${HOST}
DEVCONSOLE_PORT=${PORT}
DEVCONSOLE_DATA_DIR=${DATA_DIR}
DEVCONSOLE_LOG_DIR=${LOG_DIR}
DEVCONSOLE_USB_DIR=${USB_DIR}
DEVCONSOLE_DATABASE_URL=sqlite+aiosqlite:///${DATA_DIR}/devconsole.db

# OpenAI API key can be added later from web panel
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5

# Security
DEVCONSOLE_ALLOW_SHELL=1
DEVCONSOLE_ALLOW_DOCKER=1
DEVCONSOLE_ALLOW_ANDROID=1
EOF
    chown "${APP_USER}:${APP_USER}" "${APP_DIR}/.env"
    chmod 600 "${APP_DIR}/.env"
  fi
}

setup_usb_debug() {
  info "Готовлю USB debug-зону"
  cat > "${APP_DIR}/scripts/usb_debug_prepare.sh" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
USB_DIR="${DEVCONSOLE_USB_DIR:-/mnt/devconsole-usb}"
DATA_USB_DIR="${DEVCONSOLE_DATA_USB_DIR:-/var/lib/devconsole/usb}"
mkdir -p "${USB_DIR}" "${DATA_USB_DIR}"
echo "USB debug path: ${USB_DIR}"
echo "Data USB mirror: ${DATA_USB_DIR}"
lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINTS
EOF
  chmod +x "${APP_DIR}/scripts/usb_debug_prepare.sh"
  chown "${APP_USER}:${APP_USER}" "${APP_DIR}/scripts/usb_debug_prepare.sh"

  cat > "/etc/udev/rules.d/99-devconsole-android.rules" <<'EOF'
# Android/ADB debug access for DevConsole host.
SUBSYSTEM=="usb", MODE="0666", GROUP="plugdev"
EOF
  udevadm control --reload-rules || true
  udevadm trigger || true
}

setup_systemd() {
  info "Создаю systemd service"
  cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=DevConsole AI Development Orchestrator
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/uvicorn backend.main:app --host ${HOST} --port ${PORT}
Restart=always
RestartSec=3
StandardOutput=append:${LOG_DIR}/devconsole.log
StandardError=append:${LOG_DIR}/devconsole.err.log

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable devconsole
  systemctl restart devconsole
}

setup_docker_permissions() {
  info "Добавляю пользователя в docker/plugdev, если группы есть"
  getent group docker >/dev/null && usermod -aG docker "${APP_USER}" || true
  getent group plugdev >/dev/null && usermod -aG plugdev "${APP_USER}" || true
  systemctl enable docker || true
  systemctl restart docker || true
}

print_result() {
  info "Установка завершена"
  echo ""
  echo "DevConsole: http://$(hostname -I | awk '{print $1}'):${PORT}"
  echo "Local:      http://127.0.0.1:${PORT}"
  echo "Service:    systemctl status devconsole"
  echo "Logs:       journalctl -u devconsole -f"
  echo "App dir:    ${APP_DIR}"
  echo "Data dir:   ${DATA_DIR}"
  echo "USB dir:    ${USB_DIR}"
  echo ""
  warn "OpenAI API key можно добавить позже через web panel: http://SERVER_IP:${PORT}"
}

main() {
  require_root
  install_packages
  create_user_and_dirs
  clone_or_update_repo
  setup_python
  setup_env
  setup_usb_debug
  setup_docker_permissions
  setup_git_safe_directory
  setup_systemd
  print_result
}

main "$@"
