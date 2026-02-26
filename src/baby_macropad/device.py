"""Stream Dock M18 device wrapper.

Abstracts the StreamDock SDK so the rest of the app doesn't depend on it.
Falls back to a stub when the SDK is not installed (development/testing).

Hardware notes (VSD Inside / HOTSPOTEKUSB Stream Dock M18):
- USB VID=0x5548, PID=0x1000 (HOTSPOTEKUSB variant)
- 15 screen keys are one 480x272 LCD panel (5 cols x 3 rows)
- Individual set_key_image_stream doesn't work on this variant
- Must compose all keys into one 480x272 image and send via
  set_background_image_stream (the only working image method)
- 3 additional physical (non-display) buttons in row 4
- M18 report sizes: input=513, output=1025, feature=0
- ARM64 lib selection bug in SDK: copy libtransport_arm64.so over libtransport.so
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

KeyCallback = Callable[[int, bool], None]  # (key_number, is_pressed)

# HOTSPOTEKUSB Stream Dock M18
DEFAULT_VID = 0x5548
DEFAULT_PID = 0x1000

# Raw HID heartbeat command from Bitfocus Companion protocol analysis.
# CRT prefix + "CONNECT" payload, written via hidraw.
#
# IMPORTANT: Linux hidraw strips the first byte as the HID report ID.
# For devices without numbered reports, the first byte MUST be 0x00.
# Without it, the CRT prefix gets garbled (0x43 stripped as "report #67").
#
# Companion builds: [0x00] + CRT_prefix + command, padded to packetSize+1.
# Our VID 0x5548 (N1EN per official SDK ProductIDs.py) — try 512-byte
# packet size first (matches HSV-293S-2 with same VID in Companion).
_HID_REPORT_ID = b'\x00'
_CRT_PREFIX = bytes([0x43, 0x52, 0x54, 0x00, 0x00])
_CONNECT_PAYLOAD = bytes([0x43, 0x4F, 0x4E, 0x4E, 0x45, 0x43, 0x54])  # "CONNECT"
_PACKET_SIZE_512 = 512  # VID 0x5548 devices in Companion use 512
_PACKET_SIZE_1024 = 1024  # M18V3 default
# Try 512 first (matches our VID), fall back to 1024 if needed
_HEARTBEAT_PACKET = (_HID_REPORT_ID + _CRT_PREFIX + _CONNECT_PAYLOAD).ljust(
    _PACKET_SIZE_1024 + 1, b'\x00'
)


class DeviceError(Exception):
    pass


class StreamDockDevice:
    """Wrapper around the StreamDock SDK device.

    Uses StreamDockM18 class with direct transport enumeration.
    All display updates go through set_screen_image() which sends
    a full 480x272 composite to the LCD panel.
    """

    def __init__(self, vid: int = DEFAULT_VID, pid: int = DEFAULT_PID) -> None:
        self._vid = vid
        self._pid = pid
        self._device: Any = None
        self._transport: Any = None
        self._key_callback: KeyCallback | None = None
        self._connected = False
        self._hidraw_path: str | None = None  # For raw heartbeat writes
        self._hidraw_fd: int | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    def open(self) -> bool:
        """Discover and open the first StreamDock M18 device.

        Uses the official DeviceManager pattern: enumerate with a bare
        transport, then create a dedicated LibUSBHIDAPI(device_info) per
        device so the C library gets full HID metadata (VID, PID,
        usage_page, etc.) when creating the transport handle.

        Returns True if a device was found and opened.
        """
        try:
            from StreamDock.Devices.StreamDockM18 import StreamDockM18
            from StreamDock.Transport.LibUSBHIDAPI import LibUSBHIDAPI
        except ImportError:
            logger.warning("StreamDock SDK not installed — running in stub mode")
            return False

        try:
            # Enumerate with a bare transport (same as DeviceManager)
            enum_transport = LibUSBHIDAPI()
            found = enum_transport.enumerate_devices(self._vid, self._pid)
            if not found:
                logger.warning(
                    "No StreamDock devices found (VID=%04x PID=%04x)",
                    self._vid, self._pid,
                )
                return False

            device_dict = found[0]
            logger.info(
                "Found %d HID interface(s), using %s",
                len(found), device_dict["path"],
            )

            # Create a dedicated transport with full device info
            # (matches DeviceManager.enumerate() pattern exactly)
            device_info = LibUSBHIDAPI.create_device_info_from_dict(device_dict)
            device_transport = LibUSBHIDAPI(device_info)

            self._transport = device_transport
            self._device = StreamDockM18(device_transport, device_dict)
            self._device.open()
            self._device.init()

            self._connected = True
            self._hidraw_path = device_dict["path"]

            # Open a separate fd for raw heartbeat writes (bypasses C library)
            try:
                self._hidraw_fd = os.open(self._hidraw_path, os.O_WRONLY)
                logger.info("Heartbeat fd opened on %s", self._hidraw_path)
            except OSError:
                logger.warning("Could not open hidraw for heartbeat: %s", self._hidraw_path)
                self._hidraw_fd = None

            logger.info("StreamDock M18 opened on %s", self._hidraw_path)
            return True
        except Exception:
            logger.exception("Failed to open StreamDock device")
            return False

    def close(self) -> None:
        """Close the device connection."""
        if self._hidraw_fd is not None:
            try:
                os.close(self._hidraw_fd)
            except OSError:
                pass
            self._hidraw_fd = None
        if self._device:
            try:
                self._device.clearAllIcon()
            except Exception:
                pass
            try:
                self._device.close()
            except Exception:
                logger.debug("Native close() failed (expected on ARM64), ignoring")
            self._device = None
            self._transport = None
            self._connected = False
            logger.info("StreamDock device released")

    def turn_off_leds(self) -> None:
        """Turn off the LED ring completely.

        NOTE: Do NOT call reset_led_effect() — it restores the firmware's
        default color cycling animation. Instead, set brightness to 0 and
        color to black to suppress the LEDs.
        """
        if self._device:
            try:
                self._device.set_led_brightness(0)
                self._device.set_led_color(0, 0, 0)
                logger.info("LED ring turned off")
            except Exception:
                pass

    def set_brightness(self, level: int) -> None:
        if self._device:
            self._device.set_brightness(level)

    def set_screen_image(self, jpeg_data: bytes) -> None:
        """Send a full 480x272 JPEG image to the LCD panel.

        This is the only working image method on the HOTSPOTEKUSB M18
        variant. The entire 15-key grid is one LCD, so we send one
        composite image containing all key icons.
        """
        if not self._transport:
            return
        try:
            self._transport.set_background_image_stream(jpeg_data)
            logger.debug("Screen image sent (%d bytes)", len(jpeg_data))
        except Exception:
            logger.exception("Failed to send screen image")

    def set_screen_image_file(self, image_path: str | Path) -> None:
        """Send a 480x272 JPEG file to the LCD panel."""
        if not self._transport:
            return
        try:
            with open(str(image_path), "rb") as f:
                jpeg_data = f.read()
            self.set_screen_image(jpeg_data)
        except Exception:
            logger.exception("Failed to send screen image from %s", image_path)

    def set_led_color(self, r: int, g: int, b: int) -> None:
        """Set the LED ring color (M18 has 24 RGB LEDs)."""
        if self._device:
            try:
                self._device.set_led_color(r, g, b)
            except (AttributeError, Exception):
                pass

    def set_led_brightness(self, level: int) -> None:
        if self._device:
            try:
                self._device.set_led_brightness(level)
            except (AttributeError, Exception):
                pass

    def send_heartbeat(self) -> bool:
        """Send the raw CONNECT heartbeat to prevent firmware idle timeout.

        The firmware expects a periodic CRT+"CONNECT" HID report to stay
        in active mode. Without it, it reverts to demo mode after ~100s.

        We write directly to the hidraw device node, bypassing the SDK's
        C library which doesn't recognize our VID/PID (0x5548:0x1000).
        This is the same heartbeat Bitfocus Companion sends.
        """
        if self._hidraw_fd is None:
            return False
        try:
            os.write(self._hidraw_fd, _HEARTBEAT_PACKET)
            logger.info("Heartbeat CONNECT sent via hidraw")
            return True
        except OSError as e:
            logger.warning("Heartbeat write failed: %s", e)
            return False

    def set_key_callback(self, callback: KeyCallback) -> None:
        """Register a callback for key press/release events."""
        self._key_callback = callback

    def start_listening(self) -> None:
        """Register the key callback with the SDK.

        The SDK uses InputEvent-based callbacks. We bridge to our
        simpler (key_number, is_pressed) callback format.
        """
        if not self._device:
            return

        def _key_handler(device: Any, event: Any) -> None:
            """Bridge SDK InputEvent to our KeyCallback format."""
            try:
                from StreamDock.InputTypes import EventType
                if event.event_type == EventType.BUTTON:
                    key_num = int(event.key)  # ButtonKey IntEnum -> int
                    is_pressed = event.state == 1
                    if self._key_callback:
                        self._key_callback(key_num, is_pressed)
            except Exception:
                logger.exception("Error in key event handler")

        self._device.set_key_callback(_key_handler)
        logger.info("Key event listener registered (M18 InputEvent mode)")


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
