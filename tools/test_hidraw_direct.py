"""Diagnostic: test if using hidraw directly (no MiraboxSpace SDK) prevents USB disconnect.

Instead of the pip hidapi package (which uses libusb backend and conflicts with
the kernel HID driver), we use /dev/hidraw directly via os.open/read/write.

Protocol from Bitfocus Companion (streamdock.ts):
  - All writes: [0x00 report_id] + [0x43,0x52,0x54,0x00,0x00 CRT_prefix] + payload
  - Zero-padded to PACKET_SIZE+1 bytes
  - CONNECT heartbeat: CRT + [0x43,0x4F,0x4E,0x4E,0x45,0x43,0x54]
  - Wake screen (DIS): CRT + [0x44,0x49,0x53]
  - Refresh (STP): CRT + [0x53,0x54,0x50]
  - Brightness (LIG): CRT + [0x4C,0x49,0x47,0,0,level]
  - Button events: data[9]=key_code, data[10]=state (0x01=press, 0x02=release)
"""

import os
import select
import time
import sys
import glob

VID = 0x5548
PID = 0x1000
PACKET_SIZE = 1024

CRT_PREFIX = bytes([0x43, 0x52, 0x54, 0x00, 0x00])


def find_hidraw_path():
    """Find the hidraw device for our VID/PID via sysfs."""
    for hidraw in sorted(glob.glob("/sys/class/hidraw/hidraw*/device")):
        uevent_path = os.path.join(hidraw, "uevent")
        try:
            with open(uevent_path) as f:
                uevent = f.read()
            # Look for HID_ID line: HID_ID=0003:00005548:00001000
            for line in uevent.split("\n"):
                if line.startswith("HID_ID="):
                    parts = line.split("=")[1].split(":")
                    if len(parts) >= 3:
                        vid = int(parts[1], 16)
                        pid = int(parts[2], 16)
                        if vid == VID and pid == PID:
                            devname = os.path.basename(os.path.dirname(hidraw))
                            return f"/dev/{devname}"
        except (OSError, ValueError):
            continue
    return None


def build_cmd(payload: bytes) -> bytes:
    """Build a CRT command: report_id(0x00) + CRT_prefix + payload, padded to PACKET_SIZE+1."""
    data = b'\x00' + CRT_PREFIX + payload
    return data.ljust(PACKET_SIZE + 1, b'\x00')


def main():
    print("=== hidraw direct test (NO MiraboxSpace SDK, NO hidapi) ===")
    print(f"VID=0x{VID:04x} PID=0x{PID:04x}")
    print()

    # Find device
    path = find_hidraw_path()
    if not path:
        print("ERROR: No hidraw device found for VID/PID!")
        sys.exit(1)
    print(f"Found device: {path}")

    # Open for read+write
    fd = os.open(path, os.O_RDWR)
    print(f"  [{time.strftime('%H:%M:%S')}] Device opened (fd={fd})")

    # Send init sequence
    os.write(fd, build_cmd(bytes([0x44, 0x49, 0x53])))  # Wake (DIS)
    print(f"  [{time.strftime('%H:%M:%S')}] Wake screen sent")

    os.write(fd, build_cmd(bytes([0x4C, 0x49, 0x47, 0x00, 0x00, 80])))  # Brightness 80
    print(f"  [{time.strftime('%H:%M:%S')}] Brightness set to 80")

    os.write(fd, build_cmd(bytes([0x43, 0x4F, 0x4E, 0x4E, 0x45, 0x43, 0x54])))  # CONNECT
    print(f"  [{time.strftime('%H:%M:%S')}] Initial CONNECT heartbeat sent")
    print()

    # Main loop: poll for reads + periodic heartbeat
    start = time.time()
    last_heartbeat = time.time()
    last_status = 0
    heartbeat_interval = 10
    read_timeout = 0.1  # 100ms poll

    print(f"Monitoring... (heartbeat every {heartbeat_interval}s)")
    print(f"GOAL: stay connected for >120s (previous limit: ~60s)")
    print()

    try:
        while True:
            elapsed = time.time() - start

            # Poll for readable data with timeout
            readable, _, _ = select.select([fd], [], [], read_timeout)
            if readable:
                try:
                    data = os.read(fd, 1024)
                    if len(data) >= 11:
                        key_code = data[9]
                        state = data[10]
                        action = "PRESS" if state == 0x01 else "RELEASE"
                        print(f"  [{time.strftime('%H:%M:%S')}] Button: key=0x{key_code:02x} {action} (at {elapsed:.0f}s)")
                    elif len(data) > 0:
                        print(f"  [{time.strftime('%H:%M:%S')}] Data ({len(data)} bytes): {data[:16].hex()}")
                except OSError as e:
                    print(f"  [{time.strftime('%H:%M:%S')}] READ FAILED: {e} (at {elapsed:.0f}s)")
                    print(f"\n  DISCONNECT detected at {elapsed:.0f}s!")
                    break

            # Periodic heartbeat
            if time.time() - last_heartbeat >= heartbeat_interval:
                try:
                    os.write(fd, build_cmd(bytes([0x43, 0x4F, 0x4E, 0x4E, 0x45, 0x43, 0x54])))
                    print(f"  [{time.strftime('%H:%M:%S')}] Heartbeat CONNECT (at {elapsed:.0f}s)")
                    last_heartbeat = time.time()
                except OSError as e:
                    print(f"  [{time.strftime('%H:%M:%S')}] WRITE FAILED: {e} (at {elapsed:.0f}s)")
                    print(f"\n  DISCONNECT detected at {elapsed:.0f}s!")
                    break

            # Status every 30s
            if int(elapsed) // 30 > last_status:
                last_status = int(elapsed) // 30
                print(f"  [{time.strftime('%H:%M:%S')}] === STILL CONNECTED at {elapsed:.0f}s ===")

    except KeyboardInterrupt:
        total = time.time() - start
        print(f"\n  Stopped after {total:.0f}s")
        if total > 90:
            print("  RESULT: PASS — stayed connected past 90s!")
        else:
            print("  RESULT: Interrupted before 90s threshold")
    except Exception as e:
        print(f"\n  UNEXPECTED ERROR at {time.time() - start:.0f}s: {e}")
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        print("  Device closed.")


if __name__ == "__main__":
    main()
