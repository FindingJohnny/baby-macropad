#!/usr/bin/env bash
# Baby Basics Macropad - Raspberry Pi Setup Script
# Run on a fresh Raspberry Pi OS Bookworm (32-bit or 64-bit)
set -euo pipefail

INSTALL_DIR="/home/pi/baby-macropad"
VENV_DIR="/home/pi/macropad-venv"
SERVICE_NAME="baby-macropad"

echo "=== Baby Basics Macropad Installer ==="

# System packages
echo "Installing system dependencies..."
sudo apt update
sudo apt install -y python3-full python3-pip python3-venv \
    libhidapi-libusb0 libhidapi-dev git fonts-dejavu-core

# udev rules for StreamDock USB access
echo "Setting up udev rules..."
cat <<'EOF' | sudo tee /etc/udev/rules.d/99-streamdock.rules
SUBSYSTEM=="usb", ATTRS{idVendor}=="6603", MODE="0666", GROUP="plugdev"
KERNEL=="hidraw*", ATTRS{idVendor}=="6603", MODE="0660", GROUP="plugdev"
EOF
sudo udevadm control --reload-rules
sudo usermod -aG plugdev "$USER" || true

# Python venv
echo "Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -e "$INSTALL_DIR"
pip install streamdock  # Device SDK (optional, fails gracefully if no ARM binary)

# systemd service
echo "Installing systemd service..."
cat <<EOF | sudo tee /etc/systemd/system/${SERVICE_NAME}.service
[Unit]
Description=Baby Basics Macropad Controller
After=multi-user.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV_DIR/bin/python -m baby_macropad.main
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

echo ""
echo "=== Installation complete ==="
echo "1. Copy config/default.yaml to config/local.yaml and edit with your API token"
echo "2. Plug in your Stream Dock M18"
echo "3. Run: sudo systemctl start $SERVICE_NAME"
echo "4. Check logs: journalctl -u $SERVICE_NAME -f"
