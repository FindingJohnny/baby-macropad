"""Display test images on the M18 device one at a time.

Usage (on Pi):
  sudo systemctl stop baby-macropad
  cd ~/baby-macropad
  ~/macropad-venv/bin/python tools/show_test_images.py

Press any button on the device to advance to the next image.
Press Ctrl+C to exit.
"""

import glob
import sys
import time

from StreamDock.Devices.StreamDockM18 import StreamDockM18
from StreamDock.InputTypes import EventType
from StreamDock.Transport.LibUSBHIDAPI import LibUSBHIDAPI

VID = 0x5548
PID = 0x1000

# Find images
image_dir = "tools/test_images"
images = sorted(glob.glob(f"{image_dir}/*.jpg"))
if not images:
    print(f"No images found in {image_dir}/", flush=True)
    sys.exit(1)

print(f"Found {len(images)} test images", flush=True)

# Enumerate
enum_transport = LibUSBHIDAPI()
found = enum_transport.enumerate_devices(VID, PID)
if not found:
    print("No device found!", flush=True)
    sys.exit(1)

device_dict = found[0]
print(f"Device: {device_dict['path']}", flush=True)

# Create dedicated transport with full device info (official pattern)
device_info = LibUSBHIDAPI.create_device_info_from_dict(device_dict)
transport = LibUSBHIDAPI(device_info)
device = StreamDockM18(transport, device_dict)
device.open()
device.init()

# Turn off LEDs
device.set_led_color(0, 0, 0)
device.set_led_brightness(0)

# Track button presses
advance = [False]
last_key = [0]

def on_event(dev, event):
    if event.event_type == EventType.BUTTON and event.state == 1:
        key_num = int(event.key)
        print(f"  Button pressed: KEY_{key_num}", flush=True)
        last_key[0] = key_num
        advance[0] = True

device.set_key_callback(on_event)

# Show each image
idx = 0
while idx < len(images):
    img_path = images[idx]
    name = img_path.split("/")[-1]
    print(f"\n[{idx+1}/{len(images)}] Showing: {name}", flush=True)
    print("  Press any button to advance (or Ctrl+C to quit)", flush=True)

    with open(img_path, "rb") as f:
        jpeg_data = f.read()
    transport.set_background_image_stream(jpeg_data)

    advance[0] = False
    try:
        while not advance[0]:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nExiting...", flush=True)
        break
    idx += 1

# Cleanup
print("\nDone. Cleaning up...", flush=True)
try:
    device.set_key_callback(None)
    time.sleep(0.1)
    device.clearAllIcon()
    device.close()
except Exception:
    pass
time.sleep(0.2)
print("Bye!", flush=True)
