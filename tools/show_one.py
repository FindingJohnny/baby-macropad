"""Display a single image on the M18 device.

Usage: ~/macropad-venv/bin/python tools/show_one.py <image_path>
"""

import sys
from StreamDock.Devices.StreamDockM18 import StreamDockM18
from StreamDock.Transport.LibUSBHIDAPI import LibUSBHIDAPI

VID = 0x5548
PID = 0x1000

if len(sys.argv) < 2:
    print("Usage: show_one.py <image_path>", flush=True)
    sys.exit(1)

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

with open(sys.argv[1], "rb") as f:
    transport.set_background_image_stream(f.read())

print(f"Showing: {sys.argv[1]}", flush=True)
print("Press Ctrl+C to exit.", flush=True)

import time
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
