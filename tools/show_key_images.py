"""Display key diagnostic images on the M18, auto-advancing.

Usage (on Pi):
  sudo systemctl stop baby-macropad
  cd ~/baby-macropad
  ~/macropad-venv/bin/python tools/show_key_images.py

Each image shows for 10 seconds. Just watch the screen.
Press Ctrl+C to exit.
"""

import sys
import time

from StreamDock.Devices.StreamDockM18 import StreamDockM18
from StreamDock.Transport.LibUSBHIDAPI import LibUSBHIDAPI

VID = 0x5548
PID = 0x1000

# Only the most useful diagnostic images
IMAGES = [
    ("tools/test_images/01_numbered_cells.jpg", "NUMBERED CELLS - Are numbers centered in each button?"),
    ("tools/test_images/03_edge_markers.jpg",   "EDGE MARKERS - Can you see all 4 colors (R=top B=bottom G=left Y=right)?"),
    ("tools/test_images/02_crosshair_grid.jpg", "CROSSHAIRS - Are crosshairs centered in each button?"),
    ("tools/test_images/04_uniform_cells.jpg",  "UNIFORM GRID (naive) - Compare to image 1. Better or worse?"),
    ("tools/test_images/05c_all_up_2.jpg",      "ALL ROWS UP 2px - Better or worse than image 1?"),
    ("tools/test_images/05c_all_up_4.jpg",      "ALL ROWS UP 4px - Better or worse?"),
    ("tools/test_images/05b_all_down_2.jpg",    "ALL ROWS DOWN 2px - Better or worse than image 1?"),
    ("tools/test_images/05b_all_down_4.jpg",    "ALL ROWS DOWN 4px - Better or worse?"),
]

HOLD_SECONDS = 10

# Open device
enum_transport = LibUSBHIDAPI()
found = enum_transport.enumerate_devices(VID, PID)
if not found:
    print("No device found!", flush=True)
    sys.exit(1)

device_dict = found[0]
device_info = LibUSBHIDAPI.create_device_info_from_dict(device_dict)
transport = LibUSBHIDAPI(device_info)
device = StreamDockM18(transport, device_dict)
device.open()
device.init()
device.set_led_color(0, 0, 0)
device.set_led_brightness(0)

print(f"Device opened. Showing {len(IMAGES)} images, {HOLD_SECONDS}s each.\n", flush=True)

try:
    for i, (path, desc) in enumerate(IMAGES):
        print(f"[{i+1}/{len(IMAGES)}] {desc}", flush=True)
        with open(path, "rb") as f:
            transport.set_background_image_stream(f.read())
        time.sleep(HOLD_SECONDS)
    print("\nDone! All images shown.", flush=True)
except KeyboardInterrupt:
    print("\nStopped early.", flush=True)

try:
    device.set_key_callback(None)
    time.sleep(0.1)
    device.close()
except Exception:
    pass
