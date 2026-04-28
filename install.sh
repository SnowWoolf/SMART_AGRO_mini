#!/usr/bin/env bash
set -e

echo "=== SMART AGRO INSTALL ==="

APP_DIR="/home/agro"
REPO_URL="https://github.com/SnowWoolf/SMART_AGRO_mini.git"
VENV_DIR="$APP_DIR/venv"

echo "== apt update =="
apt-get update

echo "== install system packages =="
apt-get install -y \
    git \
    python3.8 \
    python3.8-venv \
    python3-pip \
    python3-opencv \
    python3-numpy

# создаём пользователя agro если нет
if ! id "agro" &>/dev/null; then
    echo "== creating user agro =="
    useradd -m -s /bin/bash agro
fi

echo "== clone or update repo =="

if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR"
    git pull
else
    rm -rf "$APP_DIR"
    git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"

echo "== create venv =="
rm -rf "$VENV_DIR"
python3.8 -m venv "$VENV_DIR" --system-site-packages

echo "== check cv2 =="
"$VENV_DIR/bin/python3" -c "import cv2; print('cv2 OK:', cv2.__version__)"

echo "== upgrade pip =="
"$VENV_DIR/bin/python3" -m pip install --upgrade pip

echo "== install requirements =="
"$VENV_DIR/bin/python3" -m pip install -r requirements.txt

echo "== create systemd service: web =="

cat >/etc/systemd/system/agrosmart_web.service <<EOF
[Unit]
Description=agro Web
After=network.target

[Service]
User=root
WorkingDirectory=$APP_DIR
Environment=PATH=$VENV_DIR/bin:\$PATH
ExecStart=$VENV_DIR/bin/waitress-serve --listen=0.0.0.0:5555 app_instance:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "== create systemd service: sync =="

cat >/etc/systemd/system/agrosmart_sync.service <<EOF
[Unit]
Description=agro Sync Module
After=network.target

[Service]
User=root
WorkingDirectory=$APP_DIR
Environment=PATH=$VENV_DIR/bin:\$PATH
ExecStart=$VENV_DIR/bin/python3 $APP_DIR/sync_module.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "== systemd reload =="
systemctl daemon-reload

echo "== enable services =="
systemctl enable agrosmart_web
systemctl enable agrosmart_sync

echo "== restart services =="
systemctl restart agrosmart_web
systemctl restart agrosmart_sync

echo
echo "=== INSTALL COMPLETE ==="
echo "WEB: http://$(hostname -I | awk '{print $1}'):5555"
echo
systemctl status agrosmart_web --no-pager
