"""Stream Dock M18 device wrapper.

Abstracts the StreamDock SDK so the rest of the app doesn't depend on it.
Falls back to a stub when the SDK is not installed (development/testing).

Hardware notes (VSD Inside / HOTSPOTEKUSB Stream Dock M18):
- USB VID=0x5548, PID=0x1000 (HOTSPOTEKUSB variant)
- Official SDK expects VID=0x6603, PID=0x1009 — we enumerate manually
- Two HID interfaces: interface 0 = device control, interface 1 = keyboard
- Only use interface 0 (first enumerated path)
- M18 uses StreamDockM18 class (NOT StreamDock293!)
- M18 transport: setKeyImgDualDevice / setBackgroundImgDualDevice
- M18 key images: 64x64 JPEG, no rotation
- M18 touchscreen: 480x272 JPEG, no rotation
- M18 report sizes: input=513, output=1025, feature=0
- ARM64 lib selection bug in SDK: copies libtransport_arm64.so over libtransport.so
"""

from __future__ import annotations

import logging
import os
import random
import tempfile
from pathlib import Path
from typing import Any, Callable

from PIL import Image

logger = logging.getLogger(__name__)

KeyCallback = Callable[[int, bool], None]  # (key_number, is_pressed)

# HOTSPOTEKUSB Stream Dock M18
DEFAULT_VID = 0x5548
DEFAULT_PID = 0x1000


class DeviceError(Exception):
    pass


class StreamDockDevice:
    """Wrapper around the StreamDock SDK device.

    Uses StreamDockM18 class with direct transport enumeration.
    Bypasses DeviceManager to avoid dual-interface enumeration bugs.
    """

    def __init__(self, vid: int = DEFAULT_VID, pid: int = DEFAULT_PID) -> None:
        self._vid = vid
        self._pid = pid
        self._device: Any = None
        self._transport: Any = None
        self._key_callback: KeyCallback | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def open(self) -> bool:
        """Discover and open the first StreamDock M18 device.

        Uses direct transport enumeration (not DeviceManager) to avoid
        the dual-interface bug where both HID interfaces create separate
        device objects sharing one transport.

        Returns True if a device was found and opened.
        """
        try:
            from StreamDock.Devices.StreamDockM18 import StreamDockM18
            from StreamDock.Transport.LibUSBHIDAPI import LibUSBHIDAPI
        except ImportError:
            logger.warning("StreamDock SDK not installed — running in stub mode")
            return False

        try:
            transport = LibUSBHIDAPI()
            found = transport.enumerate(self._vid, self._pid)
            if not found:
                logger.warning(
                    "No StreamDock devices found (VID=%04x PID=%04x)",
                    self._vid, self._pid,
                )
                return False

            # Use only the first interface (interface 0 = device control)
            logger.info(
                "Found %d HID interface(s), using %s",
                len(found), found[0]["path"],
            )
            self._transport = transport
            self._device = StreamDockM18(transport, found[0])
            self._device.open()

            # init() calls set_device() which sets report sizes (513, 1025, 0),
            # then wakeScreen, set_brightness(100), clearAllIcon, refresh
            self._device.init()

            self._connected = True
            logger.info("StreamDock M18 opened on %s", found[0]["path"])
            return True
        except Exception:
            logger.exception("Failed to open StreamDock device")
            return False

    def close(self) -> None:
        """Close the device connection.

        Uses the SDK's close() which stops the reader thread and
        sends disconnect. If that segfaults, the OS cleans up on exit.
        """
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

    def set_brightness(self, level: int) -> None:
        if self._device:
            self._device.set_brightness(level)

    def set_key_image(self, key: int, image_path: str | Path) -> None:
        """Set the icon on a specific key (1-15).

        M18 uses setKeyImgDualDevice via the native transport lib.
        The SDK's set_key_image handles image conversion (64x64 JPEG)
        and the hardware key mapping internally.
        """
        if not self._device:
            return
        try:
            path = str(image_path)
            result = self._device.set_key_image(key, path)
            logger.info("Set key %d image from %s, result=%s", key, path, result)
        except Exception:
            logger.exception("Failed to set key %d image from %s", key, image_path)

    def set_touchscreen_image(self, image_path: str | Path) -> None:
        """Set the full touchscreen background image (480x272)."""
        if not self._device:
            return
        try:
            path = str(image_path)
            result = self._device.set_touchscreen_image(path)
            logger.info("Set touchscreen image from %s, result=%s", path, result)
        except Exception:
            logger.exception("Failed to set touchscreen image")

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

    def set_key_callback(self, callback: KeyCallback) -> None:
        """Register a callback for key press/release events."""
        self._key_callback = callback

    def start_listening(self) -> None:
        """Register the key callback with the SDK.

        The new SDK uses InputEvent-based callbacks. We bridge to our
        simpler (key_number, is_pressed) callback format.
        """
        if not self._device:
            return

        def _key_handler(device: Any, event: Any) -> None:
            """Bridge SDK InputEvent to our KeyCallback format."""
            try:
                from StreamDock.InputTypes import EventType
                if event.event_type == EventType.BUTTON:
                    key_num = int(event.key)  # ButtonKey IntEnum → int
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

    def set_key_image(self, key: int, image_path: str | Path) -> None:
        logger.debug("Stub: set key %d image to %s", key, image_path)

    def set_touchscreen_image(self, image_path: str | Path) -> None:
        logger.debug("Stub: set touchscreen to %s", image_path)

    def set_led_color(self, r: int, g: int, b: int) -> None:
        self._led_color = (r, g, b)
        logger.debug("Stub: LED color set to (%d, %d, %d)", r, g, b)

    def set_led_brightness(self, level: int) -> None:
        logger.debug("Stub: LED brightness set to %d", level)

    def set_key_callback(self, callback: KeyCallback) -> None:
        self._key_callback = callback

    def start_listening(self) -> None:
        logger.info("Stub: key listener started (no-op)")

    def simulate_key_press(self, key: int) -> None:
        """For testing: simulate a key press event."""
        if self._key_callback:
            self._key_callback(key, True)
