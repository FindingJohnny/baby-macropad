"""Diagnostic: test if using hidapi directly (no MiraboxSpace SDK) prevents USB disconnect.

The hypothesis: the SDK's libtransport.so C library causes the ~60s USB disconnect.
This script bypasses it entirely and uses python-hidapi (cython-hidapi) for all HID I/O.

Protocol from Bitfocus Companion (streamdock.ts):
  - CRT prefix: [0x43, 0x52, 0x54, 0x00, 0x00]
  - Commands are: prefix + payload, zero-padded to packetSize, with 0x00 report ID prepended
  - CONNECT heartbeat: [0x43, 0x4F, 0x4E, 0x4E, 0x45, 0x43, 0x54]
  - Wake screen (DIS): [0x44, 0x49, 0x53]
  - Refresh (STP): [0x53, 0x54, 0x50]
  - Brightness (LIG): [0x4C, 0x49, 0x47, 0, 0, brightness]
"""

import hid
import time
import sys
import struct

VID = 0x5548
PID = 0x1000
PACKET_SIZE = 1024  # M18/N1 default

CRT_PREFIX = bytes([0x43, 0x52, 0x54, 0x00, 0x00])


def build_cmd(payload: bytes) -> bytes:
    """Build a CRT command packet: [0x00 report_id] + CRT_prefix + payload, padded to PACKET_SIZE+1."""
    data = b'\x00' + CRT_PREFIX + payload
    return data.ljust(PACKET_SIZE + 1, b'\x00')


def send_heartbeat(device):
    """Send CRT+CONNECT heartbeat."""
    cmd = build_cmd(bytes([0x43, 0x4F, 0x4E, 0x4E, 0x45, 0x43, 0x54]))
    device.write(cmd)
    print(f"  [{time.strftime('%H:%M:%S')}] Heartbeat CONNECT sent")


def send_wake(device):
    """Send CRT+DIS wake screen command."""
    cmd = build_cmd(bytes([0x44, 0x49, 0x53]))
    device.write(cmd)
    print(f"  [{time.strftime('%H:%M:%S')}] Wake screen (DIS) sent")


def send_refresh(device):
    """Send CRT+STP refresh command."""
    cmd = build_cmd(bytes([0x53, 0x54, 0x50]))
    device.write(cmd)
    print(f"  [{time.strftime('%H:%M:%S')}] Refresh (STP) sent")


def send_brightness(device, level: int):
    """Send CRT+LIG brightness command."""
    cmd = build_cmd(bytes([0x4C, 0x49, 0x47, 0x00, 0x00, level]))
    device.write(cmd)
    print(f"  [{time.strftime('%H:%M:%S')}] Brightness set to {level}")


def main():
    print(f"=== hidapi direct test (bypassing MiraboxSpace SDK) ===")
    print(f"VID=0x{VID:04x} PID=0x{PID:04x} PACKET_SIZE={PACKET_SIZE}")
    print()

    # Enumerate
    devices = hid.enumerate(VID, PID)
    if not devices:
        print("ERROR: No devices found!")
        sys.exit(1)

    # Use interface 0
    target = None
    for d in devices:
        if d["interface_number"] == 0:
            target = d
            break
    if not target:
        target = devices[0]

    print(f"Opening: {target['path']}")

    # Open device
    device = hid.device()
    device.open_path(target["path"])
    device.set_nonblocking(0)  # Blocking reads with timeout
    print(f"  [{time.strftime('%H:%M:%S')}] Device opened")

    # Send init sequence (matching Companion's init)
    send_wake(device)
    send_brightness(device, 80)
    send_heartbeat(device)
    print()

    # Main loop: read events + send heartbeat every 10s
    start = time.time()
    last_heartbeat = time.time()
    heartbeat_interval = 10  # More frequent for testing

    print(f"Monitoring... (heartbeat every {heartbeat_interval}s)")
    print(f"PASS if no disconnect for >90s")
    print()

    try:
        while True:
            elapsed = time.time() - start

            # Read with 100ms timeout (matches SDK's transport_read timeout)
            data = device.read(1024, timeout_ms=100)
            if data:
                if len(data) >= 11:
                    key_code = data[9]
                    state = data[10]
                    action = "PRESS" if state == 0x01 else "RELEASE"
                    print(f"  [{time.strftime('%H:%M:%S')}] Button event: key={key_code} {action} (elapsed={elapsed:.0f}s)")

            # Periodic heartbeat
            if time.time() - last_heartbeat >= heartbeat_interval:
                try:
                    send_heartbeat(device)
                    last_heartbeat = time.time()
                except Exception as e:
                    print(f"  [{time.strftime('%H:%M:%S')}] HEARTBEAT FAILED: {e} (elapsed={elapsed:.0f}s)")
                    print(f"\n  DISCONNECT detected at {elapsed:.0f}s")
                    break

            # Status update
            if int(elapsed) % 30 == 0 and int(elapsed) > 0:
                print(f"  [{time.strftime('%H:%M:%S')}] Still connected at {elapsed:.0f}s...")

    except KeyboardInterrupt:
        print(f"\n  Stopped after {time.time() - start:.0f}s")
    except Exception as e:
        print(f"\n  ERROR at {time.time() - start:.0f}s: {e}")
    finally:
        try:
            device.close()
        except Exception:
            pass
        print("  Device closed.")


if __name__ == "__main__":
    main()
