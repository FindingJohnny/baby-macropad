"""Stream Dock M18 device wrapper — pure raw hidraw driver.

100% raw hidraw I/O with zero MiraboxSpace SDK dependency. The SDK's C library
(libtransport.so) causes firmware USB disconnects after ~60s due to its internal
reader thread. Raw hidraw keeps the device stable indefinitely (verified 70+ min).

Protocol reverse-engineered from Bitfocus Companion + strace of C library:
  - All commands: [0x00 report_id] + CRT_prefix + payload, padded to PACKET_SIZE+1
  - CRT prefix: [0x43, 0x52, 0x54, 0x00, 0x00]
  - Heartbeat: CRT + CONNECT [0x43,0x4F,0x4E,0x4E,0x45,0x43,0x54]
  - Wake: CRT + DIS [0x44,0x49,0x53]
  - Brightness: CRT + LIG [0x4C,0x49,0x47,0,0,level]
  - Background image: CRT + LOG [0x4C,0x4F,0x47,size_be32,0x01] + JPEG chunks
  - LED color: CRT + SETLB [0x53,0x45,0x54,0x4C,0x42] + [R,G,B]*24
  - LED reset: CRT + DELED [0x44,0x45,0x4C,0x45,0x44]
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
import time
from pathlib import Path
from typing import Callable

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
_CMD_SETLB = bytes([0x53, 0x45, 0x54, 0x4C, 0x42])  # "SETLB" — LED ring color
_CMD_DELED = bytes([0x44, 0x45, 0x4C, 0x45, 0x44])  # "DELED" — LED ring reset
_LED_COUNT = 24  # Number of RGB LEDs around the dial


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
    """Stream Dock driver using 100% raw hidraw — no SDK dependency.

    All I/O (heartbeat, images, button reads, brightness) goes through
    raw /dev/hidraw to avoid the SDK's C library reader thread which
    causes firmware USB disconnects after ~60s.

    Includes USB reconnection logic: if the device disconnects (cable bump,
    power glitch), the driver detects the I/O error, closes the fd, waits
    for the device to re-enumerate, re-opens it, re-initializes, and
    re-sends the cached screen image.
    """

    _MAX_RECONNECT_ATTEMPTS = 5
    _RECONNECT_DELAY_SECONDS = 3.0

    def __init__(self, vid: int = DEFAULT_VID, pid: int = DEFAULT_PID) -> None:
        self._vid = vid
        self._pid = pid
        self._key_callback: KeyCallback | None = None
        self._connected = False
        self._hidraw_path: str | None = None
        self._hidraw_fd: int | None = None
        self._reader_thread: threading.Thread | None = None
        self._reader_stop = threading.Event()
        self._write_lock = threading.Lock()
        # Cached state for reconnection
        self._screen_jpeg: bytes | None = None
        self._brightness: int = 80
        # Reconnection state
        self._reconnecting = threading.Event()  # set = reconnect in progress

    @property
    def connected(self) -> bool:
        return self._connected

    def open(self) -> bool:
        """Discover and open the device via raw hidraw.

        Returns True if a device was found and opened.
        """
        self._hidraw_path = _find_hidraw(self._vid, self._pid)
        if not self._hidraw_path:
            logger.warning(
                "No StreamDock device found (VID=%04x PID=%04x)", self._vid, self._pid
            )
            return False

        try:
            self._hidraw_fd = os.open(self._hidraw_path, os.O_RDWR)
            logger.info("Opened %s (fd=%d)", self._hidraw_path, self._hidraw_fd)

            # Init sequence must be: wake → brightness → heartbeat
            # (verified stable for 70+ minutes in test_hidraw_direct.py)
            self._raw_write(_WAKE_PACKET)
            logger.info("Wake screen sent")

            self._raw_write(_build_cmd(bytes([0x4C, 0x49, 0x47, 0x00, 0x00, 80])))
            logger.info("Init brightness 80 sent")

            self._raw_write(_HEARTBEAT_PACKET)
            logger.info("Initial CONNECT heartbeat sent")

            self._connected = True
            logger.info("StreamDock opened on %s", self._hidraw_path)
            return True
        except Exception:
            logger.exception("Failed to open StreamDock device")
            self._cleanup_fd()
            return False

    def _raw_write(self, data: bytes) -> None:
        """Write raw data to hidraw (thread-safe).

        Raises OSError if the write fails (callers decide whether to reconnect).
        """
        if self._hidraw_fd is None or self._reconnecting.is_set():
            return
        with self._write_lock:
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
        self._reader_stop.set()  # Also prevents reconnect loop from continuing
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=2.0)

        self._cleanup_fd()
        self._connected = False
        logger.info("StreamDock device released")

    def set_brightness(self, level: int) -> None:
        """Set screen brightness (0-100) via CRT+LIG command."""
        self._brightness = max(0, min(100, level))
        # Apply gamma curve (matches Companion's setBrightness)
        y = pow(self._brightness / 100, 0.75)
        brightness = round(y * 100)
        try:
            self._raw_write(_build_cmd(bytes([0x4C, 0x49, 0x47, 0x00, 0x00, brightness])))
        except OSError as e:
            logger.warning("Failed to set brightness: %s", e)

    def set_screen_image(self, jpeg_data: bytes) -> None:
        """Send a full 480x272 JPEG to the LCD via CRT+LOG protocol.

        Protocol (captured via strace of the C library):
          1. LOG header: CRT + [L,O,G, size_be32, layer=0x01]
          2. JPEG data in 1024-byte chunks: [0x00] + chunk, padded to 1025
          3. STP refresh: CRT + [S,T,P] to commit the image to display
        """
        self._screen_jpeg = jpeg_data  # Cache for reconnection
        if self._hidraw_fd is None:
            return
        # Hold lock for entire sequence (header + chunks + STP) to prevent
        # heartbeat/LED writes from interleaving and corrupting the transfer.
        with self._write_lock:
            try:
                size = len(jpeg_data)
                # LOG header command
                header = bytes([
                    0x4C, 0x4F, 0x47,  # "LOG"
                    (size >> 24) & 0xFF,
                    (size >> 16) & 0xFF,
                    (size >> 8) & 0xFF,
                    size & 0xFF,
                    0x01,  # layer
                ])
                os.write(self._hidraw_fd, _build_cmd(header))

                # Send JPEG data in chunks (no CRT prefix, just report ID + data)
                for offset in range(0, size, _PACKET_SIZE):
                    chunk = jpeg_data[offset:offset + _PACKET_SIZE]
                    packet = (b'\x00' + chunk).ljust(_PACKET_SIZE + 1, b'\x00')
                    os.write(self._hidraw_fd, packet)

                # STP refresh — commits the image to the display
                os.write(self._hidraw_fd, _REFRESH_PACKET)

                logger.debug("Screen image sent (%d bytes, %d chunks)",
                             size, (size + _PACKET_SIZE - 1) // _PACKET_SIZE)
            except OSError as e:
                logger.warning("Failed to send screen image: %s", e)

    def set_screen_image_file(self, image_path: str | Path) -> None:
        """Send a 480x272 JPEG file to the LCD panel."""
        try:
            with open(str(image_path), "rb") as f:
                self.set_screen_image(f.read())
        except Exception:
            logger.exception("Failed to send screen image from %s", image_path)

    def set_led_color(self, r: int, g: int, b: int) -> None:
        """Set all 24 LED ring LEDs to the same color via CRT+SETLB command.

        Protocol (captured via strace of libtransport.so):
          CRT + SETLB + [R, G, B] * 24
        Each LED gets an individual RGB triplet; we repeat the same color 24 times.
        """
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        rgb_data = bytes([r, g, b]) * _LED_COUNT
        try:
            self._raw_write(_build_cmd(_CMD_SETLB + rgb_data))
        except OSError as e:
            logger.warning("Failed to set LED color: %s", e)

    def reset_led_color(self) -> None:
        """Reset LED ring to firmware default via CRT+DELED command."""
        try:
            self._raw_write(_build_cmd(_CMD_DELED))
        except OSError as e:
            logger.warning("Failed to reset LED color: %s", e)

    def set_led_brightness(self, level: int) -> None:
        """Set LED ring brightness via CRT+LBLIG command."""
        try:
            self._raw_write(_build_cmd(bytes([
                0x4C, 0x42, 0x4C, 0x49, 0x47,  # "LBLIG"
                0x00, 0x00, level,
            ])))
        except OSError:
            pass

    def turn_off_leds(self) -> None:
        """Turn off the LED ring."""
        self.set_led_brightness(0)
        logger.info("LED ring turned off")

    def send_heartbeat(self) -> bool:
        """Send CRT+CONNECT heartbeat to prevent firmware idle timeout.

        The firmware reverts to demo mode without periodic CONNECT commands.
        Triggers USB reconnection on write failure.
        """
        if self._hidraw_fd is None:
            return False
        try:
            with self._write_lock:
                os.write(self._hidraw_fd, _HEARTBEAT_PACKET)
            logger.debug("Heartbeat CONNECT sent")
            return True
        except OSError as e:
            logger.warning("Heartbeat write failed: %s", e)
            self._trigger_reconnect()
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
                    self._trigger_reconnect()
                break
            except Exception:
                if not self._reader_stop.is_set():
                    logger.exception("Error in hidraw reader")

    def _trigger_reconnect(self) -> None:
        """Initiate USB reconnection in a background thread.

        Only one reconnect attempt runs at a time (guarded by _reconnecting event).
        """
        if self._reconnecting.is_set():
            return  # Already reconnecting
        self._reconnecting.set()
        threading.Thread(
            target=self._reconnect_loop,
            daemon=True,
            name="usb-reconnect",
        ).start()

    def _reconnect_loop(self) -> None:
        """Attempt to reconnect to the device after USB disconnect."""
        try:
            logger.info("USB reconnect: starting (max %d attempts)", self._MAX_RECONNECT_ATTEMPTS)
            self._connected = False

            # Close the stale fd
            self._cleanup_fd()

            for attempt in range(1, self._MAX_RECONNECT_ATTEMPTS + 1):
                if self._reader_stop.is_set():
                    logger.info("USB reconnect: aborted (shutdown requested)")
                    return

                logger.info("USB reconnect: attempt %d/%d (waiting %.0fs)",
                            attempt, self._MAX_RECONNECT_ATTEMPTS,
                            self._RECONNECT_DELAY_SECONDS)
                time.sleep(self._RECONNECT_DELAY_SECONDS)

                # Try to find and open the device
                path = _find_hidraw(self._vid, self._pid)
                if not path:
                    logger.info("USB reconnect: device not found yet")
                    continue

                try:
                    fd = os.open(path, os.O_RDWR)
                except OSError as e:
                    logger.info("USB reconnect: failed to open %s: %s", path, e)
                    continue

                # Device found and opened — reinitialize
                self._hidraw_fd = fd
                self._hidraw_path = path
                logger.info("USB reconnect: opened %s (fd=%d)", path, fd)

                try:
                    # Re-run init sequence: wake → brightness → heartbeat
                    # Write directly to fd (bypass _raw_write which checks _reconnecting)
                    with self._write_lock:
                        os.write(fd, _WAKE_PACKET)
                        os.write(fd, _build_cmd(bytes([
                            0x4C, 0x49, 0x47, 0x00, 0x00, self._brightness,
                        ])))
                        os.write(fd, _HEARTBEAT_PACKET)

                    # Clear reconnecting flag BEFORE re-sending image
                    # (set_screen_image uses _raw_write which checks the flag)
                    self._reconnecting.clear()
                    self._connected = True

                    # Re-send cached screen image
                    if self._screen_jpeg:
                        self.set_screen_image(self._screen_jpeg)
                        logger.info("USB reconnect: screen image restored")

                    # Restart the reader thread
                    self._reader_stop.clear()
                    self._reader_thread = threading.Thread(
                        target=self._reader_loop,
                        daemon=True,
                        name="hidraw-reader",
                    )
                    self._reader_thread.start()

                    logger.info("USB reconnect: successful on attempt %d", attempt)
                    return
                except OSError as e:
                    logger.warning("USB reconnect: init failed on %s: %s", path, e)
                    self._cleanup_fd()
                    continue

            logger.error("USB reconnect: all %d attempts failed — device offline",
                         self._MAX_RECONNECT_ATTEMPTS)
        finally:
            self._reconnecting.clear()


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

    def reset_led_color(self) -> None:
        logger.debug("Stub: LED color reset (no-op)")

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
