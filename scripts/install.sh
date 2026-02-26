#!/usr/bin/env bash
# Baby Basics Macropad - Raspberry Pi Setup Script
# Tested on Pi 4 with Debian Trixie (aarch64) and Bookworm
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
VENV_DIR="${VENV_DIR:-/home/$USER/macropad-venv}"
SERVICE_NAME="baby-macropad"

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

# udev rules for StreamDock USB access (both known vendor IDs)
echo ""
echo "Setting up udev rules..."
cat <<'EOF' | sudo tee /etc/udev/rules.d/99-streamdock.rules
# VSD Inside / HOTSPOTEKUSB Stream Dock M18
SUBSYSTEM=="usb", ATTRS{idVendor}=="5548", MODE="0666", GROUP="plugdev"
KERNEL=="hidraw*", ATTRS{idVendor}=="5548", MODE="0660", GROUP="plugdev"
# StreamDock (alternate vendor ID)
SUBSYSTEM=="usb", ATTRS{idVendor}=="6603", MODE="0666", GROUP="plugdev"
KERNEL=="hidraw*", ATTRS{idVendor}=="6603", MODE="0660", GROUP="plugdev"
# StreamDock (SDK default vendor ID)
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
pip install -e "$INSTALL_DIR"
pip install streamdock

# Patch StreamDock SDK for ARM64 + M18 device
echo ""
echo "Patching StreamDock SDK for ARM64 and M18 device..."
SITE_PACKAGES="$VENV_DIR/lib/python$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')/site-packages"
SDK_DIR="$SITE_PACKAGES/StreamDock"

if [ -d "$SDK_DIR" ]; then
    # Fix ARM64 library selection bug: SDK checks platform.system() for 'arm'
    # but it returns 'Linux' on ARM Linux. Copy the arm64 lib over the default.
    if [ "$(uname -m)" = "aarch64" ] && [ -f "$SDK_DIR/Transport/libtransport_arm64.so" ]; then
        cp "$SDK_DIR/Transport/libtransport_arm64.so" "$SDK_DIR/Transport/libtransport.so"
        echo "  Patched: ARM64 transport library"
    fi

    # Add M18 device (VID=0x5548 PID=0x1000) to ProductIDs
    cat > "$SDK_DIR/ProductIDs.py" << 'PYEOF'
class USBVendorIDs:
    USB_VID = 0x5500
    USB_VID_HOTSPOTEKUSB = 0x5548

class USBProductIDs:
    USB_PID_STREAMDOCK_ORIGINAL = 0x0060
    USB_PID_STREAMDOCK_ORIGINAL_V2 = 0x006d
    USB_PID_STREAMDOCK_MINI = 0x0063
    USB_PID_STREAMDOCK_XL = 0x006c
    USB_PID_STREAMDOCK_XL_V2 = 0x008f
    USB_PID_STREAMDOCK_MK2 = 0x0080
    USB_PID_STREAMDOCK_PEDAL = 0x0086
    USB_PID_STREAMDOCK_MINI_MK2 = 0x0090
    USB_PID_STREAMDOCK_PLUS = 0x0084
    USB_PID_STREAMDOCK_293 = 0x1001
    USB_PID_STREAMDOCK_M18 = 0x1000
PYEOF
    echo "  Patched: ProductIDs with M18 device"

    # Update DeviceManager to enumerate M18 devices
    cat > "$SDK_DIR/DeviceManager.py" << 'PYEOF'
from .Devices.StreamDock293 import StreamDock293
from .ProductIDs import USBVendorIDs, USBProductIDs
from .Transport.LibUSBHIDAPI import LibUSBHIDAPI

class DeviceManager:
    streamdocks = list()

    @staticmethod
    def _get_transport(transport):
        return LibUSBHIDAPI()

    def __init__(self, transport=None):
        self.transport = self._get_transport(transport)

    def enumerate(self):
        products = [
            (USBVendorIDs.USB_VID, USBProductIDs.USB_PID_STREAMDOCK_293, StreamDock293),
            (USBVendorIDs.USB_VID_HOTSPOTEKUSB, USBProductIDs.USB_PID_STREAMDOCK_M18, StreamDock293),
        ]
        for vid, pid, class_type in products:
            found_devices = self.transport.enumerate(vid=vid, pid=pid)
            self.streamdocks.extend([class_type(self.transport, d) for d in found_devices])
        return self.streamdocks
PYEOF
    echo "  Patched: DeviceManager with M18 enumeration"
    echo "StreamDock SDK patching complete."
else
    echo "  Warning: StreamDock SDK not found at $SDK_DIR — device may not work"
fi

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
