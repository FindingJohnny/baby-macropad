"""Stream Dock M18 device wrapper — raw hidraw driver.

Bypasses the MiraboxSpace SDK's C library (libtransport.so) for all HID I/O
except image transmission. The C library's reader thread causes firmware USB
disconnects after ~60s. Using raw hidraw directly keeps the device stable
indefinitely (verified 70+ minutes with zero disconnects).

Protocol from Bitfocus Companion (streamdock.ts):
  - All writes: [0x00 report_id] + CRT_prefix + payload, padded to PACKET_SIZE+1
  - CRT prefix: [0x43, 0x52, 0x54, 0x00, 0x00]
  - Button events: data[9]=key_code, data[10]=state (0x01=press, 0x02=release)

Hardware: VSD Inside / HOTSPOTEKUSB Stream Dock (VID=0x5548, PID=0x1000)
  - PID 0x1000 = StreamDock N1EN per official SDK ProductIDs.py
  - 15 screen keys (one 480x272 LCD panel), 3 physical buttons, 24 RGB LEDs
"""

from __future__ import annotations

import glob
import logging
import os
import select
import threading
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

KeyCallback = Callable[[int, bool], None]  # (key_number, is_pressed)

# HOTSPOTEKUSB Stream Dock
DEFAULT_VID = 0x5548
DEFAULT_PID = 0x1000

# CRT protocol constants (from Bitfocus Companion streamdock.ts)
_PACKET_SIZE = 1024
_CRT_PREFIX = bytes([0x43, 0x52, 0x54, 0x00, 0x00])
_CMD_CONNECT = bytes([0x43, 0x4F, 0x4E, 0x4E, 0x45, 0x43, 0x54])  # "CONNECT"
_CMD_WAKE = bytes([0x44, 0x49, 0x53])  # "DIS"
_CMD_REFRESH = bytes([0x53, 0x54, 0x50])  # "STP"


def _build_cmd(payload: bytes) -> bytes:
    """Build a CRT command packet for hidraw write.

    Format: [0x00 report_id] + CRT_prefix + payload, zero-padded to PACKET_SIZE+1.
    Linux hidraw strips the first byte as HID report ID — the 0x00 prefix is mandatory.
    """
    return (b'\x00' + _CRT_PREFIX + payload).ljust(_PACKET_SIZE + 1, b'\x00')


# Pre-built packets for performance
_HEARTBEAT_PACKET = _build_cmd(_CMD_CONNECT)
_WAKE_PACKET = _build_cmd(_CMD_WAKE)
_REFRESH_PACKET = _build_cmd(_CMD_REFRESH)


def _find_hidraw(vid: int, pid: int) -> str | None:
    """Find the hidraw device path for the CONTROL interface (input0).

    The device has two HID interfaces:
      - input0 (interface 0): control + button events (usage_page=0xFF60)
      - input1 (interface 1): standard keyboard HID (usage_page=1)

    We must use input0 for the CRT protocol and button events.
    """
    vid_hex = f"{vid:08X}"
    pid_hex = f"{pid:08X}"
    target_id = f"0003:{vid_hex}:{pid_hex}"

    matches = []
    for hidraw_dir in sorted(glob.glob("/sys/class/hidraw/hidraw*/device")):
        uevent_path = os.path.join(hidraw_dir, "uevent")
        try:
            with open(uevent_path) as f:
                uevent = f.read()
            if target_id not in uevent.upper():
                continue
            devname = os.path.basename(os.path.dirname(hidraw_dir))
            devpath = f"/dev/{devname}"
            # Prefer input0 (control interface) over input1 (keyboard)
            is_input0 = "input0" in uevent
            matches.append((devpath, is_input0))
        except OSError:
            continue

    # Return input0 if found, otherwise first match
    for path, is_input0 in matches:
        if is_input0:
            return path
    return matches[0][0] if matches else None


class DeviceError(Exception):
    pass


class StreamDockDevice:
    """Stream Dock driver using raw hidraw for HID I/O.

    Uses the SDK transport only for image sending (complex chunked protocol).
    All other I/O (heartbeat, button reads, brightness, LED) goes through
    raw hidraw to avoid the SDK's C library reader thread which causes
    firmware USB disconnects.
    """

    def __init__(self, vid: int = DEFAULT_VID, pid: int = DEFAULT_PID) -> None:
        self._vid = vid
        self._pid = pid
        self._transport: Any = None  # SDK transport (for images only)
        self._key_callback: KeyCallback | None = None
        self._connected = False
        self._hidraw_path: str | None = None
        self._hidraw_fd: int | None = None  # Read+write fd for all raw HID I/O
        self._reader_thread: threading.Thread | None = None
        self._reader_stop = threading.Event()

    @property
    def connected(self) -> bool:
        return self._connected

    def open(self) -> bool:
        """Discover and open the device.

        Order matters:
        1. Set up SDK transport for image sending FIRST (needs exclusive access)
        2. Find and open hidraw for read+write (heartbeat, buttons, commands)
        3. Send init sequence (wake, heartbeat)

        Returns True if a device was found and opened.
        """
        # Step 1: Set up SDK transport for image sending (must happen before
        # we open hidraw, as the SDK's enumerate_devices needs access)
        self._setup_image_transport()

        # Step 2: Find device via sysfs
        self._hidraw_path = _find_hidraw(self._vid, self._pid)
        if not self._hidraw_path:
            logger.warning(
                "No StreamDock device found (VID=%04x PID=%04x)", self._vid, self._pid
            )
            return False

        try:
            # Open hidraw for read+write
            self._hidraw_fd = os.open(self._hidraw_path, os.O_RDWR)
            logger.info("Opened %s (fd=%d)", self._hidraw_path, self._hidraw_fd)

            # Send init sequence via raw hidraw
            self._raw_write(_WAKE_PACKET)
            logger.info("Wake screen sent")

            self._raw_write(_HEARTBEAT_PACKET)
            logger.info("Initial CONNECT heartbeat sent")

            self._connected = True
            logger.info("StreamDock opened on %s", self._hidraw_path)
            return True
        except Exception:
            logger.exception("Failed to open StreamDock device")
            self._cleanup_fd()
            return False

    def _setup_image_transport(self) -> None:
        """Set up the SDK transport for image sending only.

        We create the transport and open it, but do NOT create a StreamDockM18
        device object (which would start the problematic C library reader thread).
        """
        try:
            from StreamDock.Transport.LibUSBHIDAPI import LibUSBHIDAPI
        except ImportError:
            logger.info("StreamDock SDK not installed — image sending unavailable")
            return

        try:
            # Enumerate to get device info needed for transport
            enum_transport = LibUSBHIDAPI()
            found = enum_transport.enumerate_devices(self._vid, self._pid)
            if not found:
                logger.warning("SDK enumeration found no devices (image transport unavailable)")
                return

            device_dict = found[0]
            device_info = LibUSBHIDAPI.create_device_info_from_dict(device_dict)
            transport = LibUSBHIDAPI(device_info)

            # Open the transport (for image writes)
            transport.open(bytes(device_dict["path"], "utf-8"))
            # Set M18/N1 report sizes
            transport.set_report_size(513, 1025, 0)

            self._transport = transport
            logger.info("SDK image transport ready")
        except Exception:
            logger.warning("Failed to set up SDK image transport (images will be unavailable)")
            self._transport = None

    def _raw_write(self, data: bytes) -> None:
        """Write raw data to hidraw."""
        if self._hidraw_fd is not None:
            os.write(self._hidraw_fd, data)

    def _cleanup_fd(self) -> None:
        """Close the hidraw file descriptor."""
        if self._hidraw_fd is not None:
            try:
                os.close(self._hidraw_fd)
            except OSError:
                pass
            self._hidraw_fd = None

    def close(self) -> None:
        """Clean shutdown."""
        # Stop reader thread
        self._reader_stop.set()
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=2.0)

        # Close SDK transport (for images)
        if self._transport:
            try:
                self._transport.close()
            except Exception:
                pass
            self._transport = None

        # Close hidraw fd
        self._cleanup_fd()

        self._connected = False
        logger.info("StreamDock device released")

    def set_brightness(self, level: int) -> None:
        """Set screen brightness (0-100) via CRT+LIG command."""
        clamped = max(0, min(100, level))
        # Apply gamma curve (matches Companion's setBrightness)
        y = pow(clamped / 100, 0.75)
        brightness = round(y * 100)
        try:
            self._raw_write(_build_cmd(bytes([0x4C, 0x49, 0x47, 0x00, 0x00, brightness])))
        except OSError as e:
            logger.warning("Failed to set brightness: %s", e)

    def set_screen_image(self, jpeg_data: bytes) -> None:
        """Send a full 480x272 JPEG image to the LCD panel.

        Uses the SDK transport's set_background_image_stream (complex chunked
        protocol handled by the C library). Falls back gracefully if the
        transport isn't available.
        """
        if not self._transport:
            logger.debug("No image transport — skipping screen image")
            return
        try:
            self._transport.set_background_image_stream(jpeg_data)
            logger.debug("Screen image sent (%d bytes)", len(jpeg_data))
        except Exception:
            logger.exception("Failed to send screen image")

    def set_screen_image_file(self, image_path: str | Path) -> None:
        """Send a 480x272 JPEG file to the LCD panel."""
        try:
            with open(str(image_path), "rb") as f:
                self.set_screen_image(f.read())
        except Exception:
            logger.exception("Failed to send screen image from %s", image_path)

    def set_led_color(self, r: int, g: int, b: int) -> None:
        """Set the LED ring color via SDK transport."""
        if self._transport:
            try:
                self._transport.set_led_color(24, r, g, b)
            except Exception:
                pass

    def set_led_brightness(self, level: int) -> None:
        """Set LED ring brightness via SDK transport."""
        if self._transport:
            try:
                self._transport.set_led_brightness(level)
            except Exception:
                pass

    def turn_off_leds(self) -> None:
        """Turn off the LED ring.

        Set brightness to 0 and color to black. Do NOT call reset_led_effect()
        which restores the firmware's default color cycling animation.
        """
        self.set_led_brightness(0)
        self.set_led_color(0, 0, 0)
        logger.info("LED ring turned off")

    def send_heartbeat(self) -> bool:
        """Send CRT+CONNECT heartbeat to prevent firmware idle timeout.

        The firmware reverts to demo mode without periodic CONNECT commands.
        Written directly to hidraw (bypasses SDK C library).
        """
        if self._hidraw_fd is None:
            return False
        try:
            os.write(self._hidraw_fd, _HEARTBEAT_PACKET)
            logger.debug("Heartbeat CONNECT sent")
            return True
        except OSError as e:
            logger.warning("Heartbeat write failed: %s", e)
            return False

    def set_key_callback(self, callback: KeyCallback) -> None:
        """Register a callback for key press/release events."""
        self._key_callback = callback

    def start_listening(self) -> None:
        """Start reading button events from hidraw in a background thread.

        Reads HID reports directly from /dev/hidraw (no SDK C library).
        Button events are at data[9]=key_code, data[10]=state.
        """
        if self._hidraw_fd is None:
            return

        self._reader_stop.clear()
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            daemon=True,
            name="hidraw-reader",
        )
        self._reader_thread.start()
        logger.info("Key event listener started (raw hidraw mode)")

    def _reader_loop(self) -> None:
        """Background thread: read button events from hidraw."""
        while not self._reader_stop.is_set():
            try:
                # Poll with 100ms timeout to check stop flag
                readable, _, _ = select.select([self._hidraw_fd], [], [], 0.1)
                if not readable:
                    continue

                data = os.read(self._hidraw_fd, 1024)
                if len(data) >= 11 and self._key_callback:
                    key_code = data[9]
                    state = data[10]
                    if key_code != 0xFF:  # 0xFF = write confirmation, skip
                        is_pressed = state == 0x01
                        self._key_callback(key_code, is_pressed)
            except OSError as e:
                if not self._reader_stop.is_set():
                    logger.warning("hidraw read error: %s", e)
                break
            except Exception:
                if not self._reader_stop.is_set():
                    logger.exception("Error in hidraw reader")


class StubDevice:
    """Stub device for testing without hardware."""

    def __init__(self) -> None:
        self._key_callback: KeyCallback | None = None
        self._brightness = 80
        self._led_color = (0, 0, 0)

    @property
    def connected(self) -> bool:
        return True

    def open(self) -> bool:
        logger.info("Stub device opened")
        return True

    def close(self) -> None:
        logger.info("Stub device closed")

    def set_brightness(self, level: int) -> None:
        self._brightness = level

    def set_screen_image(self, jpeg_data: bytes) -> None:
        logger.debug("Stub: screen image set (%d bytes)", len(jpeg_data))

    def set_screen_image_file(self, image_path: str | Path) -> None:
        logger.debug("Stub: screen image from %s", image_path)

    def set_led_color(self, r: int, g: int, b: int) -> None:
        self._led_color = (r, g, b)
        logger.debug("Stub: LED color set to (%d, %d, %d)", r, g, b)

    def set_led_brightness(self, level: int) -> None:
        logger.debug("Stub: LED brightness set to %d", level)

    def set_key_callback(self, callback: KeyCallback) -> None:
        self._key_callback = callback

    def turn_off_leds(self) -> None:
        logger.debug("Stub: LEDs turned off (no-op)")

    def send_heartbeat(self) -> bool:
        logger.debug("Stub: heartbeat (no-op)")
        return True

    def start_listening(self) -> None:
        logger.info("Stub: key listener started (no-op)")

    def simulate_key_press(self, key: int) -> None:
        """For testing: simulate a key press event."""
        if self._key_callback:
            self._key_callback(key, True)
