#!/usr/bin/env bash

# deploy.sh - simple deploy helper for the sacco FastAPI app
# Usage: sudo ./deploy.sh
# Environment variables:
#   REPO_URL (default: https://github.com/Ivo2022/sacco.git)
#   APP_DIR  (default: /var/www/sacco)
#   BRANCH   (default: main)

set -euo pipefail

: ${REPO_URL:=https://github.com/Ivo2022/sacco.git}
: ${APP_DIR:=/var/www/sacco}
: ${BRANCH:=main}

echo "Deploying $REPO_URL (branch=$BRANCH) to $APP_DIR"

# Ensure necessary system packages are present on common Linux distros
install_prereqs() {
  if [ -f /etc/debian_version ]; then
    apt update -qq
    apt install -y python3 python3-venv python3-pip git || true
  elif [ -f /etc/centos-release ] || [ -f /etc/redhat-release ]; then
    yum install -y python3 python3-pip git || true
  else
    echo "Warning: unsupported distro autodetect. Make sure python3, pip and git are installed."
  fi
}

install_prereqs

# Clone or update the repo
if [ ! -d "$APP_DIR" ]; then
  mkdir -p "$(dirname "$APP_DIR")"
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
else
  echo "Updating existing repo in $APP_DIR"
  cd "$APP_DIR"
  # try to fetch and reset to remote branch
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git fetch origin "$BRANCH" || true
    git checkout "$BRANCH" || true
    git pull --ff-only origin "$BRANCH" || true
  else
    echo "Directory exists but is not a git repository, skipping git update"
  fi
fi

cd "$APP_DIR"

# Create or update virtualenv
if [ ! -d "venv" ]; then
  echo "Creating virtualenv at $APP_DIR/venv"
  python3 -m venv venv
fi

echo "Activating virtualenv and installing Python dependencies"
# shellcheck source=/dev/null
. "$APP_DIR/venv/bin/activate"
pip install --upgrade pip
if [ -f requirements.txt ]; then
  pip install -r requirements.txt
else
  echo "No requirements.txt found in $APP_DIR"
fi

# Ensure start.sh is executable
if [ -f "$APP_DIR/start.sh" ]; then
  chmod +x "$APP_DIR/start.sh"
fi

# Install a systemd service unit to manage the app (if systemd is available)
SERVICE_NAME="sacco"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
if command -v systemctl >/dev/null 2>&1; then
  echo "Registering systemd service $SERVICE_NAME"
  cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=Sacco FastAPI service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/start.sh
Restart=on-failure
Environment=APP_MODULE=backend.main:app

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable --now "$SERVICE_NAME" || true
  systemctl restart "$SERVICE_NAME" || true
  echo "Service ${SERVICE_NAME} installed and started (check 'systemctl status ${SERVICE_NAME}')"
else
  echo "systemd not detected — skipping service install. You can run the app with:"
  echo "  $APP_DIR/start.sh"
fi

echo "✅ Deployment finished."
