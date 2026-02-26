#!/usr/bin/env bash
# Baby Basics Macropad - Raspberry Pi Setup Script
# Tested on Pi 4 with Debian Trixie (aarch64) and Bookworm
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
VENV_DIR="${VENV_DIR:-/home/$USER/macropad-venv}"
SERVICE_NAME="baby-macropad"
SDK_REPO="https://github.com/MiraboxSpace/StreamDock-Device-SDK.git"
SDK_CLONE_DIR="/tmp/StreamDock-Device-SDK"

echo "=== Baby Basics Macropad Installer ==="
echo "Install dir: $INSTALL_DIR"
echo "Venv dir:    $VENV_DIR"
echo "User:        $USER"

# System packages
echo ""
echo "Installing system dependencies..."
sudo apt update -qq
sudo apt install -y python3-full python3-pip python3-venv \
    libhidapi-libusb0 libhidapi-dev git fonts-dejavu-core usbutils

# udev rules for StreamDock USB access (all known vendor IDs)
echo ""
echo "Setting up udev rules..."
cat <<'EOF' | sudo tee /etc/udev/rules.d/99-streamdock.rules
# VSD Inside / HOTSPOTEKUSB Stream Dock M18 (our hardware)
SUBSYSTEM=="usb", ATTRS{idVendor}=="5548", MODE="0666", GROUP="plugdev"
KERNEL=="hidraw*", ATTRS{idVendor}=="5548", MODE="0660", GROUP="plugdev"
# Mirabox StreamDock (official vendor ID)
SUBSYSTEM=="usb", ATTRS{idVendor}=="6603", MODE="0666", GROUP="plugdev"
KERNEL=="hidraw*", ATTRS{idVendor}=="6603", MODE="0660", GROUP="plugdev"
# StreamDock (legacy vendor ID)
SUBSYSTEM=="usb", ATTRS{idVendor}=="5500", MODE="0666", GROUP="plugdev"
KERNEL=="hidraw*", ATTRS{idVendor}=="5500", MODE="0660", GROUP="plugdev"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger
sudo usermod -aG plugdev "$USER" || true

# Python venv
echo ""
echo "Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q

# Install baby-macropad package (editable)
pip install -e "$INSTALL_DIR"

# Clone official StreamDock SDK from GitHub (pip package is outdated, missing M18)
echo ""
echo "Installing StreamDock SDK from GitHub (official, with M18 support)..."
rm -rf "$SDK_CLONE_DIR"
git clone --depth 1 "$SDK_REPO" "$SDK_CLONE_DIR"

# Install the Python SDK
PYTHON_SDK_DIR="$SDK_CLONE_DIR/Python-SDK"
if [ -d "$PYTHON_SDK_DIR" ]; then
    pip install "$PYTHON_SDK_DIR"
    echo "  Installed StreamDock SDK from GitHub"
else
    echo "  ERROR: Python-SDK directory not found in cloned repo!"
    exit 1
fi

# Patch StreamDock SDK for ARM64
echo ""
echo "Patching StreamDock SDK for ARM64..."
SITE_PACKAGES="$VENV_DIR/lib/python$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')/site-packages"
SDK_DIR="$SITE_PACKAGES/StreamDock"

if [ -d "$SDK_DIR" ]; then
    # Fix ARM64 library selection bug: SDK checks platform.system() for 'arm'
    # but it returns 'Linux' on ARM Linux. Copy the arm64 lib over the default.
    TRANSPORT_DLL_DIR="$SDK_DIR/Transport/TransportDLL"
    if [ "$(uname -m)" = "aarch64" ]; then
        # Look for ARM64 .so in TransportDLL
        if [ -f "$TRANSPORT_DLL_DIR/libtransport_arm64.so" ]; then
            cp "$TRANSPORT_DLL_DIR/libtransport_arm64.so" "$TRANSPORT_DLL_DIR/libtransport.so"
            echo "  Patched: ARM64 transport library (TransportDLL/)"
        elif [ -f "$SDK_DIR/Transport/libtransport_arm64.so" ]; then
            cp "$SDK_DIR/Transport/libtransport_arm64.so" "$SDK_DIR/Transport/libtransport.so"
            echo "  Patched: ARM64 transport library (Transport/)"
        else
            echo "  Warning: No ARM64 transport library found to patch"
        fi
    fi

    # Add our HOTSPOTEKUSB VID/PID (0x5548:0x1000) to ProductIDs
    # The official SDK only has 0x6603:0x1009 for M18
    PRODUCT_IDS_FILE="$SDK_DIR/ProductIDs.py"
    if [ -f "$PRODUCT_IDS_FILE" ]; then
        if ! grep -q "0x5548" "$PRODUCT_IDS_FILE"; then
            echo ""
            echo "  Note: Our device VID 0x5548 not in ProductIDs.py"
            echo "  We enumerate manually in device.py, so this is OK."
        fi
    fi

    echo "StreamDock SDK patching complete."
else
    echo "  Warning: StreamDock SDK not found at $SDK_DIR — device may not work"
fi

# Clean up SDK clone
rm -rf "$SDK_CLONE_DIR"

# systemd service
echo ""
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
